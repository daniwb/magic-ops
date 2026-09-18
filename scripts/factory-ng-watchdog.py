#!/usr/bin/env python3
"""Poll Factory NG health every ten minutes and recover a stale controller.

The tmux launcher already restarts a controller after exit.  This watchdog is
the independent half of that supervision: it verifies durable state movement,
worker PIDs, queue pressure, and controller freshness.  If the controller has
stopped updating past policy, it terminates that exact controller process so
the existing launcher recreates it.  Every poll is retained as machine-readable
state plus an append-only operator log.
"""
import argparse
import json
import os
import calendar
import signal
import subprocess
import time
from collections import Counter
from pathlib import Path
from factory_ng_safety import source_problem
from factory_ng_quiet import compilation_status
from factory_ng_queue_tracking import record as record_queue_trend
import urllib.request


OPS = Path(__file__).resolve().parents[1]
RUNTIME = OPS / "state/factory-ng-runtime.json"
JOBS = OPS / "state/factory-ng-jobs.json"
POLICY = OPS / "config/factory-ng-policy.json"
WORKERS = OPS / "config/factory-ng-workers.json"
SOURCE = Path(os.environ.get('FACTORY_NG_SOURCE', '/opt/development/test/openmagic'))
STATE = OPS / "state/factory-ng-watchdog.json"
LOG = OPS / "state/factory-ng-watchdog.log"


def load_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_time(value):
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return 0


def alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        if Path("/proc/%d/stat" % pid).read_text().split()[2] == "Z":
            return False
        os.kill(pid, 0)
        return True
    except (OSError, IndexError):
        return False


def controller_pids():
    result = subprocess.run(["pgrep", "-f", "factory-ng-controller.py"],
                            capture_output=True, text=True)
    found = []
    for item in result.stdout.split():
        if not item.isdigit() or int(item) == os.getpid():
            continue
        pid = int(item)
        try:
            argv = Path("/proc/%d/cmdline" % pid).read_bytes().split(b"\0")
        except OSError:
            continue
        if any(arg.endswith(b"python3") for arg in argv[:1]) and any(
                arg in (b"scripts/factory-ng-controller.py", os.fsencode(OPS / "scripts/factory-ng-controller.py"))
                for arg in argv[1:]):
            found.append(pid)
    return found


def latest_mtime(directory, pattern):
    return max((path.stat().st_mtime for path in directory.glob(pattern)), default=0)


def productive_signature(jobs):
    """Track durable accepted/integrated outcomes, not ticket failure churn."""
    accepted = 0
    integrated = 0
    latest_productive = 0
    latest_integrated = 0
    for path in (OPS / "docs/factory-ng/runs").glob("*.json"):
        value = load_json(path, {}) or {}
        schema = value.get("schema")
        outcome = str(value.get("outcome", ""))
        productive = schema == "factory.observation-receipt/v1" and outcome.startswith("accepted")
        if schema == "factory.integration-receipt/v1" and (
                "gate_green" in outcome or outcome.startswith("committed_locally_fully_gated")):
            integrated += 1
            productive = True
            latest_integrated = max(latest_integrated, path.stat().st_mtime)
        elif productive:
            accepted += 1
        if productive:
            latest_productive = max(latest_productive, path.stat().st_mtime)
    completed = sum(job.get("state") == "completed" for job in jobs.values())
    return {"accepted_receipts": accepted, "completed_jobs": completed,
            "integrations": integrated, "latest_productive_epoch": int(latest_productive),
            'latest_integrated_epoch': int(latest_integrated)}


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def runtime_producer_errors(runtime):
    errors = [item for item in runtime.get("results", [])
              if item.get("producer") and (item.get("status") == "producer_error" or item.get('candidate_errors'))]
    if runtime.get("phase") == "producer_error" and not errors:
        errors.append({"producer": "controller-sweep"})
    return errors


def card_progress(now_epoch):
    path = OPS / 'state/factory-ng-card-history.jsonl'
    try:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except (OSError, ValueError):
        return {'available': False}
    if not rows:
        return {'available': False}
    latest = rows[-1]
    baseline = min(rows, key=lambda row: abs(row['ts'] - (now_epoch - 86400)))
    return {'available': True, 'auto': latest['auto'],
            'delta_24h': latest['auto'] - baseline['auto'],
            'sample_age_seconds': int(now_epoch - latest['ts']),
            'window_seconds': latest['ts'] - baseline['ts']}


def poll(restart=True):
    runtime = load_json(RUNTIME, {}) or {}
    jobs = {key: job for key, job in (load_json(JOBS, {}) or {}).get('jobs', {}).items()
            if not job.get('superseded_by')}
    settings = load_json(POLICY, {}) or {}
    stale_after = max(60, int(settings.get("queue", {}).get("stalled_after_seconds", 900)))
    now_epoch = time.time()
    runtime_age = int(now_epoch - parse_time(runtime.get("updated_at")))
    pids = controller_pids()
    states = Counter(job.get("state", "unknown") for job in jobs.values())
    active_jobs = [job for job in jobs.values() if job.get("state") in ("working", "integrating")]
    dead_active = [job.get("ticket_id") for job in active_jobs if not alive(job.get("pid"))]
    latest_ticket = latest_mtime(OPS / "docs/factory-ng/tickets", "*.json")
    latest_receipt = latest_mtime(OPS / "docs/factory-ng/runs", "*.json")
    activity_signature = {
        "job_states": dict(sorted(states.items())),
        "latest_ticket_epoch": int(latest_ticket),
        "latest_receipt_epoch": int(latest_receipt),
    }
    production = productive_signature(jobs)
    previous = load_json(STATE, {}) or {}
    activity_changed = activity_signature != previous.get("activity_signature", previous.get("signature"))
    productive_changed = production != previous.get("productive_signature", production)
    previous_age = now_epoch - parse_time(previous.get("checked_at"))
    problems = []
    schedule = compilation_status(settings)
    # Factory NG records an all-worker provider pace hold separately from the
    # compilation switch. Treat both as intentional pauses for liveness and
    # supply diagnostics; otherwise a healthy idle factory is reported as
    # stalled every watchdog interval.
    scheduled_pause = (not schedule["allowed"] or
                       bool(runtime.get("pace_paused", False)))
    operator_paused = (OPS / 'state/factory-ng-paused').exists()
    git_problem = source_problem(SOURCE)
    if git_problem:
        # Integration is the only permitted owner of a transient source change.
        if not any(job.get('state') == 'integrating' and alive(job.get('pid')) for job in jobs.values()):
            problems.append(git_problem)
    try:
        with urllib.request.urlopen('http://127.0.0.1:4103/health', timeout=5) as response:
            if response.status != 200:
                problems.append('card-knowledge service is unavailable')
    except (OSError, ValueError):
        problems.append('card-knowledge service is unavailable')
    if not pids and not operator_paused:
        problems.append("controller process is absent")
    if runtime_age > stale_after and not operator_paused:
        problems.append("controller state is stale by %d seconds" % runtime_age)
    if dead_active:
        problems.append("active job PIDs are dead: " + ", ".join(dead_active))
    producer_errors = runtime_producer_errors(runtime)
    if producer_errors:
        problems.append("producer errors: " + ", ".join(item["producer"] for item in producer_errors))
    queue_status = runtime.get("queue", {}) if isinstance(runtime.get("queue"), dict) else {}
    runnable = int(queue_status.get("runnable", 0))
    deferred = int(queue_status.get("deferred", max(0, states.get('queued', 0) - runnable)))
    if states.get('queued', 0) and not queue_status:
        problems.append('queue availability is unknown; producer snapshot omitted inventory')
    stalled_queue = (not activity_changed and previous_age >= 540 and not active_jobs and runnable > 0)
    stalled_queue = stalled_queue and not scheduled_pause
    if stalled_queue:
        problems.append("runnable work made no durable activity across a ten-minute poll")
    if deferred and not runnable and not active_jobs and not scheduled_pause:
        problems.append("all %d queued tickets are deferred; no runnable reserve exists" % deferred)
    workers = (load_json(WORKERS, {}) or {}).get('workers', [])
    supply_empty = (not active_jobs and not runnable and not deferred
                    and not operator_paused and not scheduled_pause
                    and any(w.get('enabled') for w in workers))
    supply_empty_since = (previous.get('supply_empty_since_epoch') or now_epoch) if supply_empty else None
    if supply_empty_since and now_epoch - supply_empty_since >= 600:
        problems.append('ticket supply exhausted: enabled workers have had no work for ten minutes')
    no_productive_progress = (not productive_changed and previous_age >= 540 and
                              bool(active_jobs or runnable or deferred))
    if no_productive_progress and not scheduled_pause:
        problems.append("no accepted or integrated progress across a ten-minute poll")
    stranded = [job for job in jobs.values() if job.get('state') == 'integration_failed']
    if stranded:
        problems.append('%d unresolved integration failure(s)' % len(stranded))
    last_landing = production.get('latest_integrated_epoch', 0)
    landing_pending = any(job.get('state') in ('integrating', 'awaiting_integration') for job in jobs.values())
    if landing_pending and last_landing and now_epoch - last_landing > 7200 and not scheduled_pause:
        problems.append('accepted patches are waiting, but no successful integration in two hours')
    # The cards endpoint owns history sampling. Poll it without a browser so
    # unattended operation still has a fresh, measured 24-hour output clock.
    try:
        with urllib.request.urlopen('http://127.0.0.1:9999/factory-ng/cards', timeout=15) as response:
            response.read()
            if response.status != 200:
                problems.append('enabled-card measurement endpoint is unavailable')
    except (OSError, ValueError):
        problems.append('enabled-card measurement endpoint is unavailable')
    cards = card_progress(time.time())
    if cards.get('available') and cards.get('window_seconds', 0) >= 23 * 3600 and cards['delta_24h'] <= 0:
        problems.append('no enabled-card increase over the last 24 hours')
    if cards.get('available') and cards['sample_age_seconds'] > 3600:
        problems.append('enabled-card measurement is stale')

    recovery = []
    if restart and not operator_paused and (not pids or runtime_age > stale_after or stalled_queue):
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                recovery.append("terminated stale controller pid %d for supervised restart" % pid)
            except OSError as exc:
                recovery.append("could not terminate controller pid %d: %s" % (pid, exc))
        if not pids:
            try:
                restarted = subprocess.run(['tmux', 'new-window', '-d', '-t', 'dispatcher',
                                            '-n', 'factory-ng', 'exec bash ' + str(OPS / 'launchers/launch-factory-ng.sh')],
                                           capture_output=True, text=True, timeout=30)
                recovery.append('requested missing supervisor recovery' if restarted.returncode == 0 else
                                'supervisor recovery failed: ' + restarted.stderr[-300:])
            except (OSError, subprocess.TimeoutExpired) as exc:
                recovery.append('supervisor recovery failed: ' + str(exc))

    queue_settings = settings.get("queue", {})
    workers = (load_json(WORKERS, {}) or {}).get("workers", [])
    configured_workers = sum(bool(worker.get("enabled")) for worker in workers)
    configured_target = max(1, int(queue_settings.get("target_ready", 1)),
                            int(queue_settings.get("ready_per_worker", 0)) * configured_workers)
    value = {
        "schema": "factory.ng-watchdog/v1",
        "checked_at": iso_now(),
        "interval_seconds": 600,
        "healthy": not problems,
        'operator_paused': operator_paused,
        'compilation': schedule,
        "moving": productive_changed,
        "active": activity_changed or bool(active_jobs and not dead_active),
        "controller": {"pids": pids, "runtime_age_seconds": runtime_age,
                       "updated_at": runtime.get("updated_at")},
        "queue": {"states": dict(sorted(states.items())),
                  "target_ready": queue_status.get("target_ready", configured_target),
                  "runnable": runnable, "deferred": deferred},
        "signature": activity_signature,
        "activity_signature": activity_signature,
        "productive_signature": production,
        "supply_empty_since_epoch": supply_empty_since,
        "cards": cards,
        "problems": problems,
        "recovery": recovery,
    }
    # Queue flow remains distinct from controller activity and failure churn.
    try:
        trend = record_queue_trend(jobs=(load_json(JOBS, {}) or {}).get('jobs', {}), root=OPS)
        value['queue_trend'] = {key: trend.get(key) for key in
            ('checked_at', 'waiting', 'running', 'total_unfinished',
             'completed_since_baseline', 'cohort_states', 'repair_wait', 'window')}
        if trend.get('window', {}).get('growth_alert') and schedule.get('allowed') and not operator_paused:
            problems.append('test backlog grew by %d across %d minutes despite testing being enabled' %
                            (trend['window']['unfinished_change'], trend['window']['window_seconds'] // 60))
            value['healthy'] = False
    except (OSError, ValueError) as exc:
        value['queue_trend'] = {'error': str(exc)}
    atomic_write(STATE, value)
    with LOG.open("a") as stream:
        stream.write("[%s] healthy=%s moving=%s states=%s problems=%s recovery=%s\n" %
                     (value["checked_at"], value["healthy"], value["moving"],
                      json.dumps(value["queue"]["states"], sort_keys=True),
                      "; ".join(problems) or "none", "; ".join(recovery) or "none"))
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=600)
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()
    if args.interval < 60:
        parser.error("--interval must be at least 60 seconds")
    while True:
        print(json.dumps(poll(restart=not args.no_restart), sort_keys=True), flush=True)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
