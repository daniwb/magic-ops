#!/usr/bin/env python3
"""Small supervised Factory NG controller.

This is deliberately a small supervised controller, not a hidden generic
agent loop. It runs registered deterministic producers, dispatches compatible
workers under weekly usage pacing, retries bounded infrastructure failures,
and sends accepted durable patches through the configured full integration
gate. Models never receive integration, push, or deploy authority.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
FACTORY = OPS / "docs" / "factory-ng"
TICKETS = FACTORY / "tickets"
STATE = OPS / "state" / "factory-ng-runtime.json"
LOG = OPS / "state" / "factory-ng-controller.log"
WORKERS = OPS / "config" / "factory-ng-workers.json"
POLICY = OPS / "config" / "factory-ng-policy.json"
PRODUCER_CONFIG = OPS / "config" / "factory-ng-producers.json"
RUNS = FACTORY / "runs"
JOBS = OPS / "state" / "factory-ng-jobs.json"
JOB_OUTPUTS = OPS / "state" / "factory-ng-job-output"


def producers():
    """Load only explicitly registered bounded ground-truth producers."""
    value = load_json(PRODUCER_CONFIG) or {}
    if value.get("schema") != "factory-ng-producers/v1":
        raise ValueError("invalid Factory NG producer manifest")
    result = []
    for item in value.get("producers", []):
        if not item.get("enabled", False):
            continue
        command = item.get("command")
        if not item.get("id") or not isinstance(command, list) or not command:
            raise ValueError("invalid Factory NG producer entry")
        result.append((item["id"], command))
    return result


def write_status(**status):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    os.replace(temp, STATE)


def log(message):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), message))


def ticket_path(ticket):
    ticket_id = ticket["id"]
    stem = ticket_id.removeprefix("ticket:").replace(".", "-").replace("/", "-")
    return TICKETS / (stem + ".json")


def persist_ready(payload):
    ticket = payload["ticket"]
    destination = ticket_path(ticket)
    if destination.exists():
        return "duplicate_ticket", ticket["id"]
    measurement = payload.get("measurement")
    if measurement:
        evidence_paths = [item.get("path") for item in ticket.get("evidence", [])
                          if isinstance(item, dict) and str(item.get("path", "")).endswith(".json")]
        if not evidence_paths:
            raise ValueError("ready TicketSpec has measurement but no JSON evidence path")
        target = OPS / evidence_paths[0]
        if target.exists():
            raise ValueError("measurement destination already exists: %s" % target)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(measurement, indent=2, sort_keys=True) + "\n")
        os.replace(temp, target)
    TICKETS.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    temp.write_text(json.dumps(ticket, indent=2, sort_keys=True) + "\n")
    os.replace(temp, destination)
    return "queued", ticket["id"]


def load_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_jobs():
    value = load_json(JOBS)
    if not isinstance(value, dict) or not isinstance(value.get("jobs"), dict):
        return {"schema": "factory.ng-jobs/v1", "jobs": {}}
    return value


def save_jobs(value):
    JOBS.parent.mkdir(parents=True, exist_ok=True)
    value["updated_at"] = now()
    temp = JOBS.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, JOBS)


def observed_ticket_ids():
    seen = {}
    for path in RUNS.glob("*.json"):
        value = load_json(path)
        if value and value.get("schema") == "factory.observation-receipt/v1":
            ticket_id = value.get("ticket", {}).get("id")
            if ticket_id:
                seen[ticket_id] = {"receipt": str(path.relative_to(OPS)),
                                   "outcome": value.get("outcome", "unknown"),
                                   "integration": value.get("integration", "observation_only")}
    return seen


def integrated_ticket_ids():
    seen = {}
    for path in RUNS.glob("*.json"):
        value = load_json(path)
        if not value or value.get("schema") != "factory.integration-receipt/v1":
            continue
        if value.get("outcome") not in ("pushed_full_production_gate_green",
                                         "committed_locally_full_production_gate_green") and not str(value.get("outcome", "")).startswith("committed_locally_fully_gated"):
            continue
        for parent in value.get("parents", []):
            if isinstance(parent, str) and parent.startswith("ticket:"):
                seen[parent] = {"receipt": str(path.relative_to(OPS)),
                                "outcome": value.get("outcome", "unknown")}
    return seen


def policy():
    value = load_json(POLICY) or {}
    if value.get("schema") != "factory-ng-policy/v1":
        raise ValueError("invalid Factory NG policy")
    return value


def usage_gate(worker):
    usage_policy = worker.get("usage_policy", "unmetered")
    if usage_policy == "unmetered":
        return True, "unmetered local worker"
    scripts = {
        "claude-weekly": (OPS / "scripts/lib-pace-gate.sh", "pace_ok"),
        "codex-weekly": (OPS / "scripts/lib-pace-gate-codex.sh", "pace_ok_codex"),
    }
    if usage_policy not in scripts:
        return False, "unknown usage policy %s" % usage_policy
    script, function = scripts[usage_policy]
    try:
        checked = subprocess.run(["bash", "-c", 'source "$1"; "$2"', "factory-ng", str(script), function],
                                 cwd=OPS, capture_output=True, text=True, timeout=30)
        status = subprocess.run(["bash", str(script), "status"], cwd=OPS,
                                capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False, "usage check timed out; dispatch held safely"
    detail = " ".join(status.stdout.strip().splitlines()) or "usage status unavailable"
    return checked.returncode == 0, detail


def sync_jobs():
    """Reconcile immutable specs/receipts into the durable operator job state."""
    workers = (load_json(WORKERS) or {}).get("workers", [])
    by_profile = {worker.get("profile"): worker for worker in workers if worker.get("enabled")}
    observed = observed_ticket_ids()
    integrated = integrated_ticket_ids()
    settings = policy()
    automatic_integration = settings.get("integration", {}).get("automatic", False)
    max_attempts = max(1, int(settings.get("retry", {}).get("infrastructure_attempts", 3)))
    backoff = max(0, int(settings.get("retry", {}).get("backoff_seconds", 300)))
    jobs = load_jobs()
    specs = []
    superseded = set()
    for path in TICKETS.glob("*.json"):
        ticket = load_json(path)
        if ticket and ticket.get("schema") == "factory.ticket-spec/v1":
            specs.append((path, ticket))
            if ticket.get("supersedes"):
                superseded.add(ticket["supersedes"])
    for path, ticket in sorted(specs, key=lambda item: item[0].stat().st_mtime):
        ticket_id = ticket["id"]
        if ticket_id in superseded or ticket.get("lifecycle") != "ready_for_observation":
            continue
        profile = ticket.get("execution", {}).get("selected_profile")
        job = jobs["jobs"].setdefault(ticket_id, {
            "ticket_id": ticket_id, "ticket_path": str(path.relative_to(OPS)),
            "work_type": ticket.get("work_type"), "profile": profile,
            "state": "queued", "created_at": now(), "updated_at": now(),
        })
        if job.get("state") != "working":
            job.pop("pid", None)
        if ticket_id in integrated:
            job.update({"state": "completed", "integration_receipt": integrated[ticket_id]["receipt"],
                        "integration_outcome": integrated[ticket_id]["outcome"], "updated_at": now()})
        elif (ticket_id in observed and job.get("state") not in ("working", "integrating", "integration_failed")
              and job.get("processed_receipt") != observed[ticket_id]["receipt"]):
            observation = observed[ticket_id]
            outcome = observation["outcome"]
            job.update({"receipt": observation["receipt"], "outcome": outcome,
                        "processed_receipt": observation["receipt"],
                        "finished_at": now(), "updated_at": now()})
            job.pop("pid", None)
            attempts = int(job.get("attempts", 0))
            if outcome.startswith("accepted"):
                eligible = observation.get("integration") == "eligible_full_gate"
                job["state"] = "awaiting_integration" if automatic_integration and eligible else "completed"
            elif outcome.startswith("infrastructure_failed") and attempts > 0 and attempts < max_attempts:
                job["state"] = "queued"
                job["retry_after_epoch"] = int(time.time()) + backoff
                job["waiting_reason"] = "bounded infrastructure retry %d/%d after backoff" % (attempts + 1, max_attempts)
            elif outcome == "parked":
                job["state"] = "parked"
            else:
                job["state"] = "failed"
        elif job.get("state") == "queued" and profile not in by_profile:
            job["waiting_reason"] = "selected worker is disabled or not configured"
        elif job.get("state") == "queued":
            job.pop("waiting_reason", None)
    save_jobs(jobs)
    return jobs, by_profile


def next_dispatch(jobs, by_profile):
    """Return up to one compatible queued job per enabled worker."""
    busy = {job.get("worker") for job in jobs["jobs"].values() if job.get("state") == "working"}
    selected = []
    for ticket_id, job in sorted(jobs["jobs"].items(), key=lambda item: item[1].get("created_at", "")):
        if job.get("state") != "queued":
            continue
        if int(job.get("retry_after_epoch", 0)) > int(time.time()):
            continue
        profile = job.get("profile")
        worker = by_profile.get(profile)
        if not worker or worker.get("id") in busy:
            continue
        allowed, usage_status = usage_gate(worker)
        job["usage_status"] = usage_status
        if not allowed:
            job["waiting_reason"] = "weekly usage pace gate paused this worker"
            continue
        if job.get("waiting_reason", "").startswith(("weekly usage", "bounded infrastructure")):
            job.pop("waiting_reason", None)
        supported = ((profile == "qwen-prepared-direct@1.0.2" and job.get("work_type") == "map") or
                     (profile in ("claude-staged@1.0.0", "codex-constrained@1.0.0") and job.get("work_type") in ("map", "engine")))
        if supported:
            selected.append((Path(job["ticket_path"]), job, worker))
            busy.add(worker["id"])
    return selected


def job_files(ticket_id):
    stem = ticket_id.removeprefix("ticket:").replace("/", "-").replace(".", "-")
    JOB_OUTPUTS.mkdir(parents=True, exist_ok=True)
    return JOB_OUTPUTS / (stem + ".json"), JOB_OUTPUTS / (stem + ".log")


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        # A zombie has exited even though its PID remains visible until reaped.
        if Path("/proc/%d/stat" % pid).read_text().split()[2] == "Z":
            return False
        os.kill(pid, 0)
        return True
    except (OSError, IndexError):
        return False


def reconcile_running(jobs, results):
    """Turn ended worker processes into durable terminal job states."""
    changed = False
    for job in jobs["jobs"].values():
        if job.get("state") not in ("working", "integrating") or process_alive(job.get("pid")):
            continue
        result_path = OPS / job.get("result_path", "")
        payload = load_json(result_path) or {"status": "infrastructure_failed",
                                             "reason": "worker exited without a machine-readable result"}
        outcome = payload.get("status", "infrastructure_failed")
        if job.get("state") == "integrating":
            final_state = "completed" if outcome in ("pushed_full_production_gate_green", "committed_locally_full_production_gate_green") else "awaiting_integration" if outcome in ("integration_busy", "push_deferred_deploy_lock_busy", "push_failed_after_full_gate") else "integration_failed"
        else:
            settings = policy().get("retry", {})
            max_attempts = max(1, int(settings.get("infrastructure_attempts", 3)))
            retryable = outcome.startswith("infrastructure_failed") and int(job.get("attempts", 0)) < max_attempts
            final_state = "awaiting_integration" if outcome.startswith("accepted") else "queued" if retryable else "parked" if outcome == "parked" else "failed"
        job.update({"state": final_state,
                    "outcome": outcome, "finished_at": now(), "updated_at": now()})
        job.pop("pid", None)
        if payload.get("receipt"):
            job["integration_receipt" if final_state in ("completed", "awaiting_integration", "integration_failed") and job.get("state") != "working" and "integration" in str(payload.get("receipt")) else "receipt"] = payload["receipt"]
        if payload.get("reason"):
            job["reason"] = payload["reason"]
        if final_state == "queued":
            job["retry_after_epoch"] = int(time.time()) + max(0, int(settings.get("backoff_seconds", 300)))
            job["waiting_reason"] = "bounded infrastructure retry %d/%d after backoff" % (int(job.get("attempts", 0)) + 1, max_attempts)
        results.append({"worker": job.get("worker"), "ticket_id": job["ticket_id"], "status": outcome,
                        **({"receipt": payload["receipt"]} if payload.get("receipt") else {})})
        log("worker=%s status=%s ticket=%s" % (job.get("worker", "?"), outcome, job["ticket_id"]))
        changed = True
    if changed:
        save_jobs(jobs)


def dispatch_one(results, queued):
    jobs, by_profile = sync_jobs()
    reconcile_running(jobs, results)
    selected = next_dispatch(jobs, by_profile)
    if not selected:
        return jobs
    for path, job, worker in selected:
        ticket_id = job["ticket_id"]
        if ticket_id not in queued:
            queued.append(ticket_id)
        job.update({"state": "working", "worker": worker["id"], "model": worker["model"],
                    "started_at": now(), "updated_at": now(),
                    "attempts": int(job.get("attempts", 0)) + 1})
        result_file, log_file = job_files(ticket_id)
        if worker["profile"] == "qwen-prepared-direct@1.0.2":
            command = [sys.executable, str(OPS / "scripts/factory-ng-run-map-ticket.py"),
                       "--ticket", str(OPS / path), "--worker", worker["id"], "--model", worker["model"]]
        else:
            command = [sys.executable, str(OPS / "scripts/factory-ng-run-engine-ticket.py"),
                       "--ticket", str(OPS / path), "--worker", worker["id"], "--model", worker["model"],
                       "--profile", worker["profile"]]
        with result_file.open("w") as stdout, log_file.open("w") as stderr:
            process = subprocess.Popen(command, cwd=OPS, stdout=stdout, stderr=stderr, start_new_session=True)
        job.update({"pid": process.pid, "result_path": str(result_file.relative_to(OPS)),
                    "log_path": str(log_file.relative_to(OPS))})
        results.append({"worker": worker["id"], "ticket_id": ticket_id, "status": "working"})
        log("worker=%s status=working ticket=%s pid=%s" % (worker["id"], ticket_id, process.pid))
    save_jobs(jobs)
    return jobs


def dispatch_integration(jobs, results):
    if any(job.get("state") == "integrating" for job in jobs["jobs"].values()):
        return
    for job in sorted(jobs["jobs"].values(), key=lambda item: item.get("finished_at", "")):
        if job.get("state") != "awaiting_integration" or not job.get("receipt"):
            continue
        result_file, log_file = job_files(job["ticket_id"] + "-integration")
        command = [sys.executable, str(OPS / "scripts/factory-ng-integrate.py"),
                   "--receipt", str(OPS / job["receipt"])]
        with result_file.open("w") as stdout, log_file.open("w") as stderr:
            process = subprocess.Popen(command, cwd=OPS, stdout=stdout, stderr=stderr, start_new_session=True)
        job.update({"state": "integrating", "pid": process.pid,
                    "result_path": str(result_file.relative_to(OPS)),
                    "log_path": str(log_file.relative_to(OPS)), "updated_at": now()})
        results.append({"worker": "integration-harness", "ticket_id": job["ticket_id"], "status": "integrating"})
        log("integration status=working ticket=%s pid=%s" % (job["ticket_id"], process.pid))
        save_jobs(jobs)
        return


last_producer_results = []


def run_once(produce=True):
    global last_producer_results
    results, queued = list(last_producer_results), []
    if produce:
        results = []
        for producer_id, command in producers():
            write_status(state="running", phase="producing_ticket", active=[{"kind": "producer", "id": producer_id}],
                         queued=queued, results=results, message="Checking deterministic ticket producers.")
            completed = subprocess.run(command, cwd=OPS, capture_output=True, text=True, timeout=90)
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                payload = {"status": "producer_error", "reason": completed.stderr[-500:] or completed.stdout[-500:]}
            status = payload.get("status", "producer_error")
            ticket_id = payload.get("ticket_id")
            if completed.returncode == 0 and status == "ready":
                try:
                    status, ticket_id = persist_ready(payload)
                except (KeyError, OSError, ValueError) as exc:
                    status = "producer_error"
                    payload["reason"] = str(exc)
            item = {"producer": producer_id, "status": status}
            if ticket_id:
                item["ticket_id"] = ticket_id
            if payload.get("reason"):
                item["reason"] = payload["reason"]
            results.append(item)
            if status == "queued" and ticket_id:
                queued.append(ticket_id)
            log("producer=%s status=%s ticket=%s" % (producer_id, status, ticket_id or "-"))
        last_producer_results = list(results)
    jobs = dispatch_one(results, queued)
    dispatch_integration(jobs, results)
    active = [{"kind": "integration" if job.get("state") == "integrating" else "worker",
               "id": "integration-harness" if job.get("state") == "integrating" else job.get("worker"),
               "model": job.get("model"), "ticket_id": job["ticket_id"], "state": job.get("state")}
              for job in jobs["jobs"].values() if job.get("state") in ("working", "integrating")]
    producer_results = [item for item in results if item.get("producer")]
    exhausted = bool(producer_results) and all(item.get("status") in
                                               ("duplicate_ticket", "already_registered", "no_existing_dispatcher",
                                                "ground_truth_changed", "needs_primitive")
                                               for item in producer_results)
    message = ("Factory NG has active isolated work; final states will be retained with immutable receipts." if active else
               "Registered ground-truth producers are exhausted; add a reviewed producer to config/factory-ng-producers.json or enqueue an explicit TicketSpec with scripts/factory-ng-enqueue.py." if exhausted else
               "No eligible queued TicketSpec is awaiting a supported worker; waiting for ground-truth work.")
    write_status(state="running", phase="building" if active else "waiting_for_ticket", active=active, queued=queued,
                 jobs=list(jobs["jobs"].values()), results=results, message=message)


stopping = False


def stop_handler(signum, frame):
    global stopping
    stopping = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=15,
                        help="job lifecycle reconciliation interval in seconds")
    parser.add_argument("--producer-interval", type=int, default=300,
                        help="ground-truth producer scan interval in seconds")
    args = parser.parse_args()
    if args.interval < 5 or args.producer_interval < args.interval:
        parser.error("--interval must be at least 5 seconds and --producer-interval must not be shorter")
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGHUP, stop_handler)
    write_status(state="running", phase="starting", active=[], queued=[], results=[],
                 message="Factory NG controller started.")
    next_production = 0
    while not stopping:
        try:
            current = time.monotonic()
            run_once(produce=current >= next_production)
            if current >= next_production:
                next_production = current + args.producer_interval
        except Exception as exc:  # keep the controller observable and retryable
            log("controller_error=%s" % exc)
            write_status(state="running", phase="producer_error", active=[], queued=[], results=[],
                         message="Producer sweep failed: %s" % exc)
        if args.once:
            break
        for _ in range(args.interval):
            if stopping:
                break
            time.sleep(1)
    write_status(state="stopped", phase="stopped", active=[], queued=[], results=[],
                 message="Factory NG controller stopped.")


if __name__ == "__main__":
    main()
