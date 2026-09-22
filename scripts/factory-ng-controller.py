#!/usr/bin/env python3
"""Small supervised Factory NG controller.

This is deliberately a small supervised controller, not a hidden generic
agent loop. It runs registered deterministic producers, dispatches compatible
workers under weekly usage pacing, retries bounded infrastructure failures,
and sends accepted durable patches through the configured full integration
gate. Models never receive integration, push, or deploy authority.
"""
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import openrouter_cooldown
import factory_ng_attention_recovery as attention_recovery
from factory_ng_quiet import compilation_status, apply_resources
from factory_ng_safety import source_problem
from factory_ng_verification import (recover_remote_batch_fallbacks, corrected_proposal_can_reverify,
                                     load_proposal, singleton_repair_evidence, recover_bundle_export_fallbacks)
from factory_ng_recovery import annotate_repair_blockers, annotate_dependency_blockers, INTEGRATION_REPAIR_MARKER
from factory_ng_archive import archived, archive_jobs
from factory_ng_frontier_reserve import reconcile_reserve


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
WORKER_PAUSES = OPS / "state" / "factory-ng-worker-pauses.json"
WORKER_TRIALS = OPS / "state" / "factory-ng-worker-trials.json"
AUTHENTICATION_OUTCOME = "infrastructure_failed_authentication"
AUTHENTICATION_REASON = "Provider OAuth session expired or could not be refreshed."
RATE_LIMIT_OUTCOME = "infrastructure_failed_rate_limited"
RATE_LIMIT_REASON = "OpenRouter rate limited the request; provider cooldown is active."
MINIMAX_PROFILE = "minimax-prepared-direct@1.0.0"
QWEN_GOOSE_PROFILE = "qwen-goose-staged@1.0.0"
OPENROUTER_GOOSE_PROFILE = "openrouter-goose-staged@1.0.0"
QWEN_DIRECT_PROFILE = "qwen-prepared-direct@1.0.2"
QWEN_AGENTIC_PROFILE = "qwen-prepared-local@1.0.1"
CLAUDE_AGENTIC_PROFILE = "claude-agentic@1.0.0"
CLAUDE_AGENTIC_TEST_PROFILE = "claude-agentic-test@1.0.0"
REMOTE_CONSTRAINED_PROFILES = ("claude-staged@1.0.0", "codex-constrained@1.0.0")
QUEUE_STATES = {"queued"}
ACTIVE_STATES = {"working", "integrating"}
from factory_ng_paths import SOURCE
INTEGRATION_RETRY_OUTCOMES = {'infrastructure_failed', 'integration_source_blocked'}


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
        timeout = item.get("timeout_seconds", 90)
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("invalid Factory NG producer timeout_seconds")
        result.append((item["id"], command, timeout))
    return result


def write_status(**status):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    if status.get('phase') == 'producing_ticket':
        previous = load_json(STATE) or {}
        for key in ('queue', 'deferred', 'jobs', 'worker_pauses', 'integration_blocked'):
            if key not in status and key in previous:
                status[key] = previous[key]
    status["compilation"] = compilation_status(policy())
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
        jobs = load_jobs()["jobs"]
        state = (jobs.get(ticket["id"]) or {}).get("state")
        return ("duplicate_active" if state in QUEUE_STATES | ACTIVE_STATES else
                "duplicate_terminal"), ticket["id"]
    from factory_ng_retry_batch import read_batch, selected, active_count
    batch = read_batch(OPS)
    if selected(batch, ticket['id']):
        specs = {value['id']: value for path in TICKETS.glob('*.json')
                 if (value := load_json(path)) and value.get('id')}
        if active_count(batch, specs, load_jobs()['jobs']) >= 2:
            return 'retry_batch_full', ticket['id']
    trial_id = ticket.get('production', {}).get('trial_id')
    if trial_id:
        jobs = load_jobs()['jobs']
        active_trial = 0
        for path in TICKETS.glob('*.json'):
            existing = load_json(path) or {}
            job = jobs.get(existing.get('id'), {})
            if (existing.get('production', {}).get('trial_id') == trial_id
                    and not job.get('superseded_by')
                    and job.get('state', 'queued') in ('queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating')):
                active_trial += 1
        if active_trial >= 2:
            return 'trial_reserve_full', ticket['id']
    production_key = ticket.get("production", {}).get("key")
    if production_key:
        jobs = load_jobs()["jobs"]
        matches = []
        for path, existing in admission_projections():
            if existing.get("production", {}).get("key") != production_key:
                continue
            existing_id = existing.get("id", "unknown")
            state = (jobs.get(existing_id) or {}).get("state")
            matches.append((path.stat().st_mtime, existing_id, state))
        if matches:
            matches.sort()
            active = next(((ticket_id, state) for _, ticket_id, state in matches
                           if state in QUEUE_STATES | ACTIVE_STATES), None)
            if active:
                return "duplicate_active", active[0]
            latest_id, latest_state = matches[-1][1], matches[-1][2]
            retrying_latest_failure = (ticket.get("supersedes") == latest_id and
                                       latest_state in ("failed", "integration_failed"))
            if latest_state == 'parked' and ticket.get('supersedes') == latest_id:
                from factory_ng_context_recovery import valid_context_successor
                specs = {value['id']: value for path in TICKETS.glob('*.json')
                         if (value := load_json(path)) and value.get('id')}
                retrying_latest_failure = valid_context_successor(
                    OPS, ticket, jobs.get(latest_id, {}), specs[latest_id], specs)
            if not retrying_latest_failure:
                return "duplicate_terminal", latest_id
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


def load_worker_pauses():
    value = load_json(WORKER_PAUSES) or {}
    if value.get("schema") != "factory.ng-worker-pauses/v1" or not isinstance(value.get("workers"), dict):
        return {"schema": "factory.ng-worker-pauses/v1", "workers": {}}
    return value


def save_worker_pauses(value):
    WORKER_PAUSES.parent.mkdir(parents=True, exist_ok=True)
    value["updated_at"] = now()
    temp = WORKER_PAUSES.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, WORKER_PAUSES)


def pause_worker_for_authentication(job, receipt=None):
    worker_id = job.get("worker")
    if not worker_id:
        return
    pauses = load_worker_pauses()
    pauses["workers"][worker_id] = {
        "worker_id": worker_id,
        "profile": job.get("dispatch_profile", job.get("profile")),
        "reason": AUTHENTICATION_REASON,
        "ticket_id": job.get("ticket_id"),
        "receipt": receipt or job.get("receipt"),
        "paused_at": now(),
        "recovery": "Relogin to the provider, then choose Resume worker in the dashboard.",
    }
    save_worker_pauses(pauses)


def refund_authentication_attempt(job, receipt=None):
    token = receipt or job.get("receipt") or job.get("updated_at") or "unknown"
    refunded = job.setdefault("authentication_refunds", [])
    if token in refunded:
        return False
    job["attempts"] = max(0, int(job.get("attempts", 0)) - 1)
    refunded.append(token)
    return True


def refund_rate_limit_attempt(job, receipt=None):
    token = receipt or job.get("receipt") or job.get("updated_at") or "unknown"
    refunded = job.setdefault("rate_limit_refunds", [])
    if token in refunded:
        return False
    job["attempts"] = max(0, int(job.get("attempts", 0)) - 1)
    refunded.append(token)
    return True


def refund_source_wait_attempt(job, receipt):
    value = load_json(OPS / receipt) if receipt else None
    if (not value or value.get('outcome') != 'source_unavailable'
            or value.get('ticket', {}).get('id') != job.get('ticket_id')
            or value.get('execution', {}).get('model_called') is not False):
        return False
    refunded = job.setdefault('source_wait_refunds', [])
    if receipt in refunded:
        return False
    job['attempts'] = max(0, int(job.get('attempts', 0)) - 1)
    refunded.append(receipt)
    return True


def receipt_has_authentication_failure(value):
    for artifact in value.get("raw_artifacts", []):
        path = artifact.get("path") if isinstance(artifact, dict) else None
        if not path:
            continue
        try:
            text = (OPS / path).read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if "failed to authenticate" in text and "oauth session expired" in text:
            return True
    return False


def migrate_authentication_failures(jobs):
    if jobs.get("oauth_retry_migration_v1"):
        return
    by_ticket = {}
    for path in RUNS.glob("*.json"):
        value = load_json(path)
        if not value or value.get("schema") != "factory.observation-receipt/v1":
            continue
        ticket_id = value.get("ticket", {}).get("id")
        if ticket_id and receipt_has_authentication_failure(value):
            by_ticket.setdefault(ticket_id, []).append(str(path.relative_to(OPS)))
    recovered = 0
    for ticket_id, receipts in by_ticket.items():
        job = jobs.get("jobs", {}).get(ticket_id)
        if not job or job.get("state") in ("completed", "awaiting_verification", "awaiting_integration", "integrating"):
            continue
        existing = set(job.get("authentication_refunds", []))
        new_receipts = [item for item in sorted(set(receipts)) if item not in existing]
        if not new_receipts:
            continue
        refund = min(int(job.get("attempts", 0)), len(new_receipts))
        job["attempts"] = max(0, int(job.get("attempts", 0)) - refund)
        job["authentication_refunds"] = sorted(existing.union(new_receipts))
        if str(job.get("outcome", "")).startswith("infrastructure_failed"):
            job.update({"state": "queued", "outcome": AUTHENTICATION_OUTCOME,
                        "reason": AUTHENTICATION_REASON, "updated_at": now()})
            job.pop("retry_after_epoch", None)
            job["waiting_reason"] = "OAuth-only attempts were refunded; waiting for an available compatible worker"
        recovered += refund
    jobs["oauth_retry_migration_v1"] = {
        "completed_at": now(),
        "refunded_attempts": recovered,
        "explanation": "OAuth authentication failures were returned to the queue without consuming ticket attempts.",
    }


_receipt_projection_cache = {}
_ticket_projection_cache = {}
_admission_projection_cache = {}
_archive_ticket_paths = set()
_archive_ids = set()
_directory_projection_stamps = {}


def cached_artifacts(directory, cache, project, cold=None):
    """Refresh changed files, checking every file even when the directory is unchanged."""
    present = set()
    # Only archived immutable artifacts may skip revalidation. Active and
    # partial files still get a stat check even if the directory is unchanged.
    try:
        directory_stat = directory.stat()
        directory_stamp = (directory_stat.st_ino, directory_stat.st_mtime_ns, directory_stat.st_ctime_ns)
    except FileNotFoundError:
        cache.clear()
        return cache
    cache_key = (str(directory), id(cache))
    if cold and _directory_projection_stamps.get(cache_key) == directory_stamp:
        for key, previous in list(cache.items()):
            if cold(previous):
                continue
            path = Path(key)
            try:
                stat = path.stat()
            except FileNotFoundError:
                cache.pop(key, None)
                continue
            stamp = (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            if previous[0] != stamp:
                value = project(load_json(path))
                cache[key] = (stamp, value, str(path.relative_to(OPS)) if value is not None else None, path)
        return cache
    try:
        entries = os.scandir(directory)
    except FileNotFoundError:
        cache.clear()
        return cache
    with entries as entries:
        for entry in entries:
            if not entry.name.endswith('.json'):
                continue
            key = entry.path
            present.add(key)
            if key in cache and cold and cold(cache[key]):
                continue
            try:
                stat = entry.stat()
            except OSError:
                cache.pop(key, None)
                continue
            stamp = (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            previous = cache.get(key)
            if previous is None or previous[0] != stamp:
                path = Path(key)
                value = project(load_json(path))
                reference = str(path.relative_to(OPS)) if value is not None else None
                cache[key] = (stamp, value, reference, path)
    for key in cache.keys() - present:
        del cache[key]
    _directory_projection_stamps[cache_key] = directory_stamp
    return cache


def admission_projections():
    """Keep duplicate checks fresh without decoding every full packet per admission."""
    def project(value):
        if not isinstance(value, dict):
            return None
        return {key: value[key] for key in ('id', 'production') if key in value}
    cache = cached_artifacts(TICKETS, _admission_projection_cache, project)
    return [(entry[3], entry[1]) for entry in cache.values() if entry[1] is not None]


def ticket_projections():
    """Retain only lifecycle inputs; worker packets still read complete TicketSpecs."""
    def project(value):
        if not isinstance(value, dict) or value.get('schema') != 'factory.ticket-spec/v1':
            return None
        projected = {key: value[key] for key in
                     ('id', 'supersedes', 'lifecycle', 'work_type', 'production', 'parents')
                     if key in value}
        projected['execution'] = {key: value.get('execution', {})[key] for key in
                                  ('selected_profile', 'compatible_profiles', 'profile_policy')
                                  if key in value.get('execution', {})}
        return projected
    cache = cached_artifacts(TICKETS, _ticket_projection_cache, project,
                             cold=lambda entry: str(entry[3]) in _archive_ticket_paths)
    return [(entry[3], entry[1], entry[2]) for entry in
            sorted(cache.values(), key=lambda entry: entry[0][2]) if entry[1] is not None]


def receipt_projections():
    """Read changed artifacts only; retain compact lifecycle fields, not raw logs.

    Stat each source on every scan so replacement, partial publication and
    removal are visible without trusting directory timestamps or job state.
    """
    def project(value):
        if isinstance(value, dict) and value.get('schema') in (
                'factory.observation-receipt/v1', 'factory.integration-receipt/v1'):
            return {key: value[key] for key in
                    ('schema', 'ticket', 'outcome', 'integration', 'parents') if key in value}
        return None
    def cold(entry):
        value = entry[1]
        if not value:
            return False
        if value.get('schema') == 'factory.observation-receipt/v1':
            return value.get('ticket', {}).get('id') in _archive_ids
        parents = [p for p in value.get('parents', []) if isinstance(p, str) and p.startswith('ticket:')]
        return bool(parents) and all(p in _archive_ids for p in parents)
    cache = cached_artifacts(RUNS, _receipt_projection_cache, project, cold=cold)
    for key in sorted(cache):
        value = cache[key][1]
        if value is not None and not cold(cache[key]):
            yield cache[key][2], value


def observed_ticket_ids(receipts=None):
    seen = {}
    for reference, value in receipt_projections() if receipts is None else receipts:
        if value and value.get("schema") == "factory.observation-receipt/v1":
            ticket_id = value.get("ticket", {}).get("id")
            if ticket_id:
                seen[ticket_id] = {"receipt": reference,
                                   "outcome": value.get("outcome", "unknown"),
                                   "integration": value.get("integration", "observation_only")}
    return seen


def integrated_ticket_ids(receipts=None):
    seen = {}
    for reference, value in receipt_projections() if receipts is None else receipts:
        if not value or value.get("schema") != "factory.integration-receipt/v1":
            continue
        if value.get("outcome") not in ("pushed_full_production_gate_green",
                                         "committed_locally_full_production_gate_green") and not str(value.get("outcome", "")).startswith("committed_locally_fully_gated"):
            continue
        for parent in value.get("parents", []):
            if isinstance(parent, str) and parent.startswith("ticket:"):
                seen[parent] = {"receipt": reference,
                                "outcome": value.get("outcome", "unknown")}
    return seen


def policy():
    value = load_json(POLICY) or {}
    if value.get("schema") != "factory-ng-policy/v1":
        raise ValueError("invalid Factory NG policy")
    return value


def max_attempts_for(job, settings):
    """Prepared-Qwen owns one bounded repair internally; do not retry the whole packet."""
    if job.get("dispatch_profile", job.get("profile")) in (QWEN_DIRECT_PROFILE,
                                                              QWEN_AGENTIC_PROFILE, QWEN_GOOSE_PROFILE, OPENROUTER_GOOSE_PROFILE):
        return attention_recovery.attempt_limit(job, 1)
    return attention_recovery.attempt_limit(job, max(1, int(settings.get("infrastructure_attempts", 3))))


def max_attempts_for_outcome(job, settings, outcome):
    """Harness launch/transport failures may retry even for prepared Qwen."""
    if outcome == "infrastructure_failed":
        return attention_recovery.attempt_limit(job, max(1, int(settings.get("infrastructure_attempts", 3))))
    return max_attempts_for(job, settings)


def trial_expired(worker):
    # Keep deadlines outside the dashboard's typed worker-config round trip.
    trials = load_json(WORKER_TRIALS) or {}
    deadline = trials.get(worker.get('id'), {}).get('ends_at_epoch', worker.get("trial_ends_at_epoch"))
    return deadline is not None and (not isinstance(deadline, (int, float)) or time.time() >= deadline)


def usage_gate(worker):
    if trial_expired(worker):
        return False, "One-hour worker trial ended; no new claims"
    usage_policy = worker.get("usage_policy", "unmetered")
    if usage_policy == "unmetered":
        return True, "unmetered local worker"
    if usage_policy == "openrouter-cooldown":
        cooldown = openrouter_cooldown.status()
        if cooldown["allowed"]:
            return True, "OpenRouter ready after %d consecutive 429(s)" % int(
                cooldown.get("consecutive_429s", 0))
        return False, "OpenRouter cooldown %ds remaining (429 stage %d, until %s)" % (
            cooldown["remaining_seconds"], cooldown.get("consecutive_429s", 1),
            cooldown.get("paused_until", "unknown"))
    scripts = {
        "claude-weekly": (OPS / "scripts/lib-pace-gate.sh", "pace_ok"),
        "codex-weekly": (OPS / "scripts/lib-pace-gate-codex.sh", "pace_ok_codex"),
    }
    if usage_policy not in scripts:
        return False, "unknown usage policy %s" % usage_policy
    script, function = scripts[usage_policy]
    environment = os.environ.copy()
    default_mode = "none" if usage_policy == "codex-weekly" else "paced"
    weekly_mode = worker.get("weekly_gate_mode", default_mode)
    if weekly_mode not in ("paced", "fixed", "none"):
        return False, "unknown weekly gate mode %s" % weekly_mode
    try:
        weekly_pct = int(worker.get("weekly_gate_pct", 95))
    except (TypeError, ValueError):
        return False, "invalid weekly gate percentage"
    if not 1 <= weekly_pct <= 100:
        return False, "weekly gate percentage must be between 1 and 100"
    environment["WEEKLY_GATE_MODE"] = weekly_mode
    environment["WEEKLY_GATE_PCT"] = str(weekly_pct)
    if usage_policy == 'claude-weekly':
        environment['PACE_OFF_FILE'] = str(OPS / 'state' / ('factory-ng-pace-%s.until' % worker['id']))
    try:
        checked = subprocess.run(["bash", "-c", 'source "$1"; "$2"', "factory-ng", str(script), function],
                                 cwd=OPS, env=environment, capture_output=True, text=True, timeout=30)
        status = subprocess.run(["bash", str(script), "status"], cwd=OPS,
                                env=environment, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False, "usage check timed out; dispatch held safely"
    detail = " ".join(status.stdout.strip().splitlines()) or "usage status unavailable"
    return checked.returncode == 0, detail


def worker_supports(worker, work_type):
    if worker.get('profile') in (CLAUDE_AGENTIC_PROFILE, CLAUDE_AGENTIC_TEST_PROFILE):
        return False  # Claude exploration is now a runner-owned evidence phase.
    routing_mode = worker.get("routing_mode", "auto")
    if routing_mode not in ("auto", "map", "engine"):
        return False
    if routing_mode != "auto" and routing_mode != work_type:
        return False
    profile = worker.get("profile")
    if profile in (QWEN_DIRECT_PROFILE, MINIMAX_PROFILE):
        return work_type == "map"
    if profile == QWEN_AGENTIC_PROFILE:
        return work_type == "engine"
    return (profile in ("claude-staged@1.0.0", "codex-constrained@1.0.0", "codex-constrained@1.1.0", CLAUDE_AGENTIC_PROFILE,
                         CLAUDE_AGENTIC_TEST_PROFILE, QWEN_GOOSE_PROFILE, OPENROUTER_GOOSE_PROFILE)
            and work_type in ("map", "engine"))


def configured_workers_by_profile(workers):
    """Expand routing profiles without inventing additional physical workers.

    Multiple enabled worker entries may declare the same profile (a second
    concurrent lease of one adapter, e.g. two "claude-staged@1.0.0" workers
    under distinct ids) — each profile maps to the ordered list of worker
    entries offering it, not a single winner.
    """
    by_profile = {}
    for worker in workers:
        if not worker.get("enabled") or trial_expired(worker):
            continue
        profiles = [worker.get("profile")] + list(worker.get("alternate_profiles") or [])
        for profile in profiles:
            if not profile:
                continue
            routed = dict(worker)
            routed["profile"] = profile
            routed["resume_only"] = profile in worker.get("draining_profiles", [])
            by_profile.setdefault(profile, []).append(routed)
    return by_profile


def worker_supports_job(worker, job):
    if trial_expired(worker):
        return False
    if worker.get("resume_only") and job.get("state") != "awaiting_verification":
        return False
    if not worker_supports(worker, job.get('work_type')):
        return False
    required_model = job.get('attention_recovery', {}).get('required_model')
    if attention_recovery.pending(job) and required_model and worker.get('model') != required_model:
        return False
    if job.get('production', {}).get('retry_batch') and worker.get('profile') != 'claude-staged@1.0.0':
        return False
    trial = worker.get('map_trial_only')
    return (not trial or job.get('work_type') != 'map'
            or job.get('production', {}).get('trial_id') == trial)


def physical_worker_keys(by_profile, allowed_profiles=None):
    profiles = allowed_profiles if allowed_profiles is not None else by_profile
    return {
        worker.get("id") or profile
        for profile in profiles for worker in by_profile.get(profile, [])
    }


def default_compatible_profiles(ticket, preferred):
    """Derive a safe adapter pool for older model-neutral TicketSpecs."""
    if preferred in (CLAUDE_AGENTIC_PROFILE, CLAUDE_AGENTIC_TEST_PROFILE):
        preferred = 'claude-staged@1.0.0'
    remote = ["claude-staged@1.0.0", "codex-constrained@1.0.0", "codex-constrained@1.1.0"]
    if ticket.get("work_type") == "engine":
        candidates = [preferred, OPENROUTER_GOOSE_PROFILE, QWEN_GOOSE_PROFILE, QWEN_AGENTIC_PROFILE] + remote
    elif int(ticket.get("production", {}).get("retry_generation", 0)) > 0:
        # A Map retry must not fall back to the local profile that exhausted v1.
        candidates = [preferred, MINIMAX_PROFILE] + remote
    else:
        candidates = [preferred, OPENROUTER_GOOSE_PROFILE, QWEN_GOOSE_PROFILE, QWEN_DIRECT_PROFILE, MINIMAX_PROFILE] + remote
    return list(dict.fromkeys(item for item in candidates if item))


def compatible_profiles_for(ticket, preferred):
    """Resolve declared profiles, including the qualified remote-profile successor.

    Older immutable TicketSpecs could not name MiniMax before its profile was
    registered.  A ticket already compatible with a constrained remote staged
    profile may use the new no-tools direct profile through the same harness.
    This does not broaden local-only or otherwise unrelated profile contracts.
    """
    declared = ticket.get("execution", {}).get("compatible_profiles")
    if ticket.get("execution", {}).get("profile_policy") == "exact":
        # Controlled cohorts must not silently acquire a different adapter.
        exact = [p for p in declared if p not in (CLAUDE_AGENTIC_PROFILE, CLAUDE_AGENTIC_TEST_PROFILE)] if isinstance(declared, list) else []
        return list(dict.fromkeys(exact)) or ['invalid-exact-profile-policy']
    if not isinstance(declared, list) or not declared:
        return default_compatible_profiles(ticket, preferred)
    compatible = list(dict.fromkeys('claude-staged@1.0.0' if p in (CLAUDE_AGENTIC_PROFILE, CLAUDE_AGENTIC_TEST_PROFILE)
                                    else p for p in declared))
    if (ticket.get('work_type') in ('map', 'engine') and QWEN_GOOSE_PROFILE not in compatible
            and any(p in compatible for p in REMOTE_CONSTRAINED_PROFILES)
            and not (ticket.get('work_type') == 'map' and int(ticket.get('production', {}).get('retry_generation', 0)) > 0)):
        compatible.append(QWEN_GOOSE_PROFILE)
    if (ticket.get('work_type') in ('map', 'engine') and OPENROUTER_GOOSE_PROFILE not in compatible
            and any(p in compatible for p in REMOTE_CONSTRAINED_PROFILES)
            and not (ticket.get('work_type') == 'map' and int(ticket.get('production', {}).get('retry_generation', 0)) > 0)):
        compatible.append(OPENROUTER_GOOSE_PROFILE)
    if 'codex-constrained@1.0.0' in compatible and 'codex-constrained@1.1.0' not in compatible:
        compatible.append('codex-constrained@1.1.0')
    if ticket.get("work_type") != "map":
        compatible = [profile for profile in compatible if profile != MINIMAX_PROFILE]
        if (QWEN_AGENTIC_PROFILE not in compatible and
                any(profile in compatible for profile in REMOTE_CONSTRAINED_PROFILES)):
            insertion = (compatible.index("codex-constrained@1.0.0")
                         if "codex-constrained@1.0.0" in compatible else len(compatible))
            compatible.insert(insertion, QWEN_AGENTIC_PROFILE)
    else:
        compatible = [profile for profile in compatible if profile != QWEN_AGENTIC_PROFILE]
    if (ticket.get("work_type") == "map" and MINIMAX_PROFILE not in compatible and
            any(profile in compatible for profile in REMOTE_CONSTRAINED_PROFILES)):
        insertion = (compatible.index("codex-constrained@1.0.0")
                     if "codex-constrained@1.0.0" in compatible else len(compatible))
        compatible.insert(insertion, MINIMAX_PROFILE)
    return list(dict.fromkeys(item for item in compatible if item))


def record_profile_failure(job, outcome):
    """Prevent deterministic adapter failures from consuming repeat attempts."""
    if outcome != "infrastructure_failed_model_protocol":
        return
    profile = job.get("dispatch_profile")
    if not profile:
        return
    failed = list(job.get("failed_profiles") or [])
    if profile not in failed:
        failed.append(profile)
    job["failed_profiles"] = failed


def migrate_minimax_engine_protocol_retries(jobs):
    """Refund duplicate controlled-rollout attempts and move them to qualified workers."""
    if jobs.get("minimax_engine_protocol_migration_v1"):
        return 0
    migrated = 0
    refunded = 0
    for job in jobs.get("jobs", {}).values():
        if (job.get("work_type") != "engine" or
                job.get("outcome") != "infrastructure_failed_model_protocol" or
                job.get("dispatch_profile", job.get("profile")) != MINIMAX_PROFILE):
            continue
        previous_attempts = max(1, int(job.get("attempts", 0)))
        refunded += max(0, previous_attempts - 1)
        job["attempts"] = 1
        failed = list(job.get("failed_profiles") or [])
        if MINIMAX_PROFILE not in failed:
            failed.append(MINIMAX_PROFILE)
        job["failed_profiles"] = failed
        job["state"] = "queued"
        job.pop("retry_after_epoch", None)
        job["waiting_reason"] = (
            "duplicate MiniMax Engine protocol attempts refunded; waiting for a qualified Engine worker")
        job["updated_at"] = now()
        migrated += 1
    jobs["minimax_engine_protocol_migration_v1"] = {
        "migrated_jobs": migrated,
        "refunded_attempts": refunded,
        "explanation": "MiniMax remains Map-qualified; repeated Engine protocol attempts moved to qualified profiles.",
    }
    return migrated


def migrate_unstarted_minimax_engine_dispatches(jobs):
    """Refund rollout leases rejected locally after Engine routing was withdrawn."""
    if jobs.get("minimax_engine_dispatch_migration_v2"):
        return 0
    migrated = 0
    for job in jobs.get("jobs", {}).values():
        if (job.get("work_type") != "engine" or job.get("worker") != "minimax-m3-free" or
                job.get("outcome") != "infrastructure_failed" or job.get("receipt")):
            continue
        job["attempts"] = max(0, int(job.get("attempts", 0)) - 1)
        failed = list(job.get("failed_profiles") or [])
        if MINIMAX_PROFILE not in failed:
            failed.append(MINIMAX_PROFILE)
        job["failed_profiles"] = failed
        job["state"] = "queued"
        job.pop("retry_after_epoch", None)
        job["waiting_reason"] = "withdrawn MiniMax Engine lease refunded; waiting for a qualified Engine worker"
        job["updated_at"] = now()
        migrated += 1
    jobs["minimax_engine_dispatch_migration_v2"] = {
        "migrated_jobs": migrated,
        "explanation": "Locally rejected MiniMax Engine leases did not call a provider and do not consume attempts.",
    }
    return migrated


def worker_availability(by_profile):
    """Probe each enabled worker once and retain the exact hold reason.

    Returns {profile: {worker_id: {"allowed": bool, "detail": str}}} — a
    profile with two concurrent worker leases (two entries sharing one
    profile) carries one entry per worker id, so a busy/paused lease never
    hides an idle sibling lease of the same adapter.
    """
    availability = {}
    checked = {}
    pauses = load_worker_pauses().get("workers", {})
    for profile, workers in by_profile.items():
        entries = {}
        for worker in workers:
            worker_id = worker.get("id") or profile
            pause = pauses.get(worker_id)
            if pause:
                entries[worker_id] = {
                    "allowed": False,
                    "detail": "authentication paused: %s" % pause.get("reason", AUTHENTICATION_REASON),
                    "pause": pause,
                }
                continue
            if worker_id not in checked:
                checked[worker_id] = usage_gate(worker)
            allowed, detail = checked[worker_id]
            entries[worker_id] = {"allowed": allowed, "detail": detail}
        availability[profile] = entries
    return availability


def all_workers_pace_paused(by_profile, availability):
    """Return true when every enabled physical worker is held only by pacing.

    A paced hold is a scheduled lack of provider capacity, not a shortage of
    ground-truth supply.  In that state producer scans cannot make a ticket
    runnable, so running them only burns local I/O until the next gate opens.
    Keep this narrow: authentication, rate-limit, compatibility, and unknown
    failures must continue to expose supply problems normally.
    """
    workers = [worker for entries in by_profile.values() for worker in entries]
    if not workers:
        return False
    holds = []
    for worker in workers:
        worker_id = worker.get("id") or worker.get("profile")
        profile = worker.get("profile")
        entry = availability.get(profile, {}).get(worker_id, {})
        detail = str(entry.get("detail", "")).lower()
        holds.append(not entry.get("allowed", False) and
                     ("pace-pause" in detail or "pace pause" in detail))
    return bool(holds) and all(holds)


def queue_inventory(jobs, by_profile, availability):
    """Classify queued records by whether any compatible adapter can run them."""
    runnable, deferred = [], []
    current = int(time.time())
    for job in jobs["jobs"].values():
        if job.get("state") != "queued" or job.get('superseded_by'):
            continue
        profiles = attention_recovery.profiles(job, job.get("compatible_profiles") or [job.get("profile")])
        failed_profiles = attention_recovery.failed_profiles(job)
        can_run = int(job.get("retry_after_epoch", 0)) <= current and any(
            worker_supports_job(worker, job) and
            availability.get(profile, {}).get(worker.get("id") or profile, {}).get("allowed", False)
            for profile in profiles if profile not in failed_profiles
            for worker in by_profile.get(profile, [])
        )
        (runnable if can_run else deferred).append(job["ticket_id"])
    return {
        "runnable": sorted(runnable, key=lambda key: dispatch_priority((key, jobs['jobs'][key]))),
        "deferred": sorted(deferred, key=lambda key: dispatch_priority((key, jobs['jobs'][key]))),
        "total": len(runnable) + len(deferred),
    }


def sync_jobs():
    """Reconcile immutable specs/receipts into the durable operator job state."""
    global _archive_ticket_paths, _archive_ids
    jobs = load_jobs()
    _archive_ids = {key for key, job in jobs['jobs'].items() if archived(job)}
    _archive_ticket_paths = {str(OPS / job['ticket_path']) for job in jobs['jobs'].values()
                             if archived(job) and job.get('ticket_path')}
    workers = (load_json(WORKERS) or {}).get("workers", [])
    by_profile = configured_workers_by_profile(workers)
    receipts = list(receipt_projections())
    observed = observed_ticket_ids(receipts)
    integrated = integrated_ticket_ids(receipts)
    settings = policy()
    automatic_integration = settings.get("integration", {}).get("automatic", False)
    retry_settings = settings.get("retry", {})
    backoff = max(0, int(settings.get("retry", {}).get("backoff_seconds", 300)))
    migrate_authentication_failures(jobs)
    migrate_minimax_engine_protocol_retries(jobs)
    migrate_unstarted_minimax_engine_dispatches(jobs)
    specs = ticket_projections()
    superseded = set()
    superseded_by = {}
    for path, ticket, reference in specs:
        if ticket.get("supersedes"):
            superseded.add(ticket["supersedes"])
            superseded_by[ticket['supersedes']] = ticket['id']
    for ticket_id, successor in superseded_by.items():
        if ticket_id in jobs['jobs']:
            jobs['jobs'][ticket_id]['superseded_by'] = successor
    for path, ticket, reference in specs:
        ticket_id = ticket["id"]
        if archived(jobs['jobs'].get(ticket_id, {})):
            continue
        if ticket_id in superseded or ticket.get("lifecycle") != "ready_for_observation":
            continue
        profile = ticket.get("execution", {}).get("selected_profile")
        compatible_profiles = compatible_profiles_for(ticket, profile)
        job = jobs["jobs"].setdefault(ticket_id, {
            "ticket_id": ticket_id, "ticket_path": reference,
            "work_type": ticket.get("work_type"), "profile": profile,
            "state": "queued", "created_at": now(), "updated_at": now(),
        })
        job["preferred_profile"] = profile
        job["compatible_profiles"] = compatible_profiles
        # Keep the producer's repair classification in the mutable dispatch
        # index.  This lets the scheduler prefer evidence-backed semantic
        # repairs over older generic/infra retries without reopening or
        # rewriting immutable TicketSpecs.
        job["production"] = dict(ticket.get("production", {}))
        # Integration is also a live child process. Dropping its PID here made
        # the next controller pass declare a healthy long-running gate dead.
        if job.get("state") not in ("working", "integrating"):
            job.pop("pid", None)
        if ticket_id in integrated:
            job.update({"state": "completed", "integration_receipt": integrated[ticket_id]["receipt"],
                        "integration_outcome": integrated[ticket_id]["outcome"],
                        "outcome": integrated[ticket_id]["outcome"], "updated_at": now()})
            for stale in ("reason", "waiting_reason", "retry_after_epoch"):
                job.pop(stale, None)
        elif (ticket_id in observed and job.get("state") not in ("working", "integrating")
              and job.get("processed_receipt") != observed[ticket_id]["receipt"]):
            observation = observed[ticket_id]
            outcome = observation["outcome"]
            job.update({"receipt": observation["receipt"], "outcome": outcome,
                        "processed_receipt": observation["receipt"],
                        "finished_at": now(), "updated_at": now()})
            job.pop("pid", None)
            attempts = int(job.get("attempts", 0))
            max_attempts = max_attempts_for(job, retry_settings)
            record_profile_failure(job, outcome)
            if outcome.startswith("accepted"):
                eligible = observation.get("integration") == "eligible_full_gate"
                job["state"] = "awaiting_integration" if automatic_integration and eligible else "completed"
            elif outcome == AUTHENTICATION_OUTCOME:
                refund_authentication_attempt(job, observation["receipt"])
                pause_worker_for_authentication(job, observation["receipt"])
                job["state"] = "queued"
                job["reason"] = AUTHENTICATION_REASON
                job["waiting_reason"] = "worker paused for provider login; this dispatch did not consume a retry"
            elif outcome == RATE_LIMIT_OUTCOME:
                refund_rate_limit_attempt(job, observation["receipt"])
                job["state"] = "queued"
                job["reason"] = RATE_LIMIT_REASON
                job["waiting_reason"] = "OpenRouter cooldown active; this dispatch did not consume a retry"
            elif outcome == 'source_unavailable':
                refund_source_wait_attempt(job, observation['receipt'])
                job['state'] = 'queued'
                job['retry_after_epoch'] = int(time.time()) + backoff
                job['waiting_reason'] = 'waiting for available canonical source; no model attempt consumed'
            elif outcome.startswith("infrastructure_failed") and attempts > 0 and attempts < max_attempts:
                job["state"] = "queued"
                job["retry_after_epoch"] = int(time.time()) + backoff
                job["waiting_reason"] = "bounded infrastructure retry %d/%d after backoff" % (attempts + 1, max_attempts)
            elif outcome == "blocked_by_capability":
                job["state"] = "blocked"
                job["waiting_reason"] = "validated atomic Engine dependency is being compiled automatically"
            elif outcome == "parked":
                job["state"] = "parked"
            else:
                job["state"] = "failed"
        # Migrate the one older receipt shape where a malformed provider
        # payload was reported as gate_failed. It is equivalent to the new
        # infrastructure_failed_model_protocol classification and gets one
        # bounded retry without rewriting the immutable receipt.
        elif (ticket_id in observed and job.get("state") == "failed"
              and not job.get("protocol_retry_queued")
              and observed[ticket_id]["outcome"] == "gate_failed"):
            old_receipt = load_json(OPS / observed[ticket_id]["receipt"]) or {}
            first_gate = (old_receipt.get("gates") or [{}])[0]
            detail = str(first_gate.get("detail", "")).lower()
            if first_gate.get("id") == "patch-apply" and ("no edit blocks" in detail or "no verdict" in detail):
                attempts = int(job.get("attempts", 0))
                max_attempts = max_attempts_for(job, retry_settings)
                if attempts < max_attempts:
                    job["state"] = "queued"
                    job["protocol_retry_queued"] = True
                    job["retry_after_epoch"] = int(time.time()) + backoff
                    job["waiting_reason"] = "bounded retry for legacy malformed model response"
        elif (job.get("state") == "failed" and job.get("outcome") == "infrastructure_failed" and
              int(job.get("attempts", 0)) < max_attempts_for_outcome(
                  job, retry_settings, job.get("outcome"))):
            job["state"] = "queued"
            job["retry_after_epoch"] = int(time.time()) + backoff
            job["waiting_reason"] = "bounded harness infrastructure retry after backoff"
        elif (job.get("state") == "queued" and
              str(job.get("outcome", "")).startswith("infrastructure_failed") and
              int(job.get("attempts", 0)) >= max_attempts_for_outcome(
                  job, retry_settings, job.get("outcome"))):
            # Must agree with the failed->queued retry check above, or a job
            # whose outcome gets the wider infrastructure_failed exception
            # (e.g. a qwen job, normally capped to 1 attempt by
            # max_attempts_for) oscillates between "failed" and "queued"
            # every reconciliation pass -- and re-issuing a fresh backoff on
            # each "failed"->"queued" flip means it never actually clears.
            job["state"] = "failed"
            job["waiting_reason"] = "profile retry budget exhausted after its internal bounded repair"
        elif (job.get('state') == 'queued' and job.get('compatible_profiles') and
              set(job['compatible_profiles']).issubset(attention_recovery.failed_profiles(job))):
            job['state'] = 'failed'
            job['waiting_reason'] = 'all compatible profiles exhausted their bounded protocol attempt; a reviewed repair is required'
        elif job.get("state") == "queued" and profile not in by_profile:
            job["waiting_reason"] = "selected worker is disabled or not configured"
        elif job.get("state") == "queued":
            job.pop("waiting_reason", None)
    recover_integration_failures(jobs, settings)
    ticket_index = {ticket['id']: ticket for _, ticket, _ in specs}
    from factory_ng_context_recovery import park_legacy_context_failure
    for ticket_id, job in jobs['jobs'].items():
        if not archived(job) and ticket_id in ticket_index and not attention_recovery.pending(job):
            park_legacy_context_failure(OPS, job, ticket_index[ticket_id], ticket_index)
    annotate_repair_blockers(jobs['jobs'], ticket_index)
    annotate_dependency_blockers(jobs['jobs'], ticket_index)
    reconcile_reserve(jobs['jobs'], max(1, int(settings.get('queue', {}).get('max_queued', 12))), dispatch_priority, now())
    archive_jobs(OPS, jobs['jobs'], now())
    save_jobs(jobs)
    return jobs, by_profile


def recover_integration_failures(jobs, settings):
    """Retry landing accepted patches without spending another model attempt."""
    if not settings.get('integration', {}).get('automatic', False):
        return
    retry = settings.get('retry', {})
    limit = int(retry.get('infrastructure_attempts', 3))
    for job in jobs['jobs'].values():
        if job.get('superseded_by'):
            continue
        if job.get('state') != 'integration_failed' or job.get('outcome') not in INTEGRATION_RETRY_OUTCOMES:
            continue
        attempts = int(job.get('integration_attempts', 1))
        if attempts >= limit or not job.get('receipt'):
            continue
        observation = load_json(OPS / job['receipt']) or {}
        if (not str(observation.get('outcome', '')).startswith('accepted') or
                observation.get('integration') != 'eligible_full_gate'):
            continue
        job.update(state='awaiting_integration', integration_attempts=attempts,
                   integration_retry_after_epoch=int(time.time()) + int(retry.get('backoff_seconds', 300)),
                   waiting_reason='accepted patch retained for bounded integration-only recovery')


def dispatch_priority(item):
    """Prefer gate-informed repairs, then fresh Map work, before broad Engine work."""
    _ticket_id, job = item
    if job.get("state") == "awaiting_verification":
        return -4, job.get("created_at", ""), job.get("ticket_id", _ticket_id)
    production = job.get("production") or {}
    if production.get('attention_recovery_parent'):
        # Finish an admitted review's dependency before admitting more reviews.
        # Verification (-4) remains first; ordinary reviewed retries are -3.
        lane = -3.5
    elif attention_recovery.pending(job) or production.get('trial_id') or production.get('retry_batch'):
        lane = -3
    elif job.get('priority_recovery_parent') or production.get('integration_recovery_parent'):
        lane = -2
    elif job.get('work_type') == 'map' and production.get('retry_reason') in ('integration_conflict_repair', 'context_repair'):
        lane = -1
    elif job.get('work_type') == 'map' and production.get('producer') == 'capability-dependencies':
        lane = 0
    elif job.get('work_type') == 'engine' and INTEGRATION_REPAIR_MARKER in str(production.get('key', '')):
        lane = 0
    elif production.get("retry_reason") == "semantic_gate_repair":
        lane = 0
    elif production.get('contract_correction_batch'):
        lane = 0
    elif production.get('producer') == 'corpus-frontier':
        # Discovery must not outrun the Engine dependencies it just exposed.
        # Finish executable foundations before spending every lease on new
        # unknown shapes; proven Map resumes remain above both.
        lane = 4
    elif job.get("work_type") == "map" and production.get("retry_reason") != "infrastructure_repair":
        lane = 1
    elif str(production.get("key", "")).endswith((":need-continuation-v2", ":evidence-refresh-v1")):
        lane = 2
    elif job.get("work_type") == "engine":
        lane = 3
    else:
        lane = 4
    rank = production.get('ranking')
    fit = tuple(rank) if isinstance(rank, list) and len(rank) == 4 and all(isinstance(n, (int, float)) for n in rank) else (0, 0, 0, 0)
    return lane, fit, job.get("created_at", ""), job.get("ticket_id", _ticket_id)


def integration_ready(jobs):
    """Reserve the shared gate slot for accepted, retry-eligible patches."""
    settings = policy()
    return (compilation_status(settings)['allowed']
            and settings.get('integration', {}).get('automatic', False)
            and any(job.get('state') == 'awaiting_integration' and job.get('receipt')
                    and not job.get('superseded_by')
                    and int(job.get('integration_retry_after_epoch', 0)) <= int(time.time())
                    for job in jobs['jobs'].values()))


def verification_slot_busy(jobs, host='local'):
    """Bound verifier processes per host; optionally overlap the sole integration."""
    overlap = policy().get('verification', {}).get('overlap_integration') is True
    limit = max(1, min(2, int(policy().get('verification', {}).get('local_slots', 1)))) if host == 'local' else 1
    # A batch has several ticket rows but owns one process/slot.
    active = {job.get('pid') or job.get('result_path') or key
              for key, job in jobs['jobs'].items()
              if job.get('state') == 'working' and job.get('verification_resume')
              and job.get('verification_host', 'local') == host}
    return (len(active) >= limit
            or (not overlap and (integration_ready(jobs) or any(
                job.get('state') == 'integrating' for job in jobs['jobs'].values()))))


def repair_only_ready(job):
    """Repair or finalize a proven failure without occupying a local test slot."""
    settings = policy().get('verification', {})
    remote = settings.get('remote', {})
    profile = job.get('dispatch_profile')
    if (profile not in ('claude-staged@1.0.0', 'codex-constrained@1.1.0', QWEN_GOOSE_PROFILE, OPENROUTER_GOOSE_PROFILE) or
            not job.get('verification_remote_failed') or not job.get('verification_isolate') or
            not job.get('result_path') or not job.get('proposal') or
            remote.get('enabled') is not True or not remote.get('id') or
            int(settings.get('batch_size', 1)) <= 1):
        return False
    status = load_json(OPS / 'state/factory-ng-remote-status.json') or {}
    if int(status.get('retry_after_epoch', 0)) > int(time.time()):
        return False
    try:
        identity = {'worker': job['worker'], 'model': job['model'], 'profile': profile}
        ticket, proposal = OPS / job['ticket_path'], OPS / job['proposal']
        load_proposal(proposal, ticket, identity)
        # The runner checks the saved allowance: repair if available, otherwise
        # publish the proven failure. Neither path runs backend tests here.
        return singleton_repair_evidence(OPS, OPS / job['result_path'], ticket, proposal, identity) is not None
    except (OSError, ValueError, KeyError, TypeError):
        return False


def next_dispatch(jobs, by_profile, availability=None):
    """Return one claimed ticket per worker, honoring global lane priority.

    Auto workers are eligible for both supported lanes. They must not ignore
    runnable Map work merely because the Engine backlog is numerically larger;
    dispatch_priority is the single ordering authority.
    """
    availability = availability or worker_availability(by_profile)
    # Combined verifiers retain the proposal's author for attribution, but
    # never call a model. Only drafting and individual repair own its lease.
    busy = {job.get("worker") for job in jobs["jobs"].values()
            if job.get("state") == "working" and not job.get("verification_batch")}
    selected = []
    ready = [(key, job) for key, job in jobs['jobs'].items()
             if job.get('state') in ('queued', 'awaiting_verification') and not job.get('superseded_by')]
    for ticket_id, job in sorted(ready, key=dispatch_priority):
        if job.get("state") not in ("queued", "awaiting_verification") or job.get('superseded_by'):
            continue
        if int(job.get("retry_after_epoch", 0)) > int(time.time()):
            job["waiting_reason"] = "bounded infrastructure retry backoff"
            continue
        resuming = job.get("state") == "awaiting_verification"
        repair_only = resuming and repair_only_ready(job)
        job.pop('verification_repair_only', None)
        if resuming and not repair_only and verification_slot_busy(jobs):
            job['waiting_reason'] = 'verification slot is occupied or reserved for integration'
            continue
        if resuming and policy().get('verification', {}).get('batch_size', 1) > 1:
            if not job.get('verification_isolate'):
                continue
        if resuming and not repair_only and any(item[1].get('state') == 'awaiting_verification'
                                               and not item[1].get('verification_repair_only') for item in selected):
            continue
        if resuming and not compilation_status(policy())["allowed"]:
            job["waiting_reason"] = "saved patch waits for compilation/testing switch"
            continue
        profiles = attention_recovery.profiles(job, job.get("compatible_profiles") or [job.get("profile")])
        failed_profiles = attention_recovery.failed_profiles(job)
        compatible = [(profile, worker) for profile in profiles if profile not in failed_profiles
                      for worker in by_profile.get(profile, [])
                      if worker_supports_job(worker, job) and (not resuming or
                          (worker.get("id") == job.get("worker") and profile == job.get("dispatch_profile")))]
        candidates = [(profile, worker) for profile, worker in compatible
                      if availability.get(profile, {}).get(worker.get("id") or profile, {}).get("allowed", False)
                      and worker.get("id") not in busy]
        chosen = next(iter(candidates), None)
        job["usage_status"] = {
            (worker.get("id") or profile): availability.get(profile, {}).get(worker.get("id") or profile, {}).get("detail", "unavailable")
            for profile, worker in compatible
        }
        if chosen is None:
            if not compatible:
                job["waiting_reason"] = "no enabled compatible worker"
            elif any(availability.get(profile, {}).get(worker.get('id') or profile, {}).get('allowed', False)
                     for profile, worker in compatible):
                job["waiting_reason"] = "compatible worker is busy; retained as runnable reserve"
            else:
                job["waiting_reason"] = "all compatible workers are usage-paused; retained as deferred inventory"
            continue
        profile, worker = chosen
        job.pop("waiting_reason", None)
        job["dispatch_profile"] = profile
        if repair_only:
            job['verification_repair_only'] = True
        selected.append((Path(job["ticket_path"]), job, worker))
        busy.add(worker["id"])
    return selected


def job_files(ticket_id):
    stem = ticket_id.removeprefix("ticket:").replace("/", "-").replace(".", "-")
    JOB_OUTPUTS.mkdir(parents=True, exist_ok=True)
    return JOB_OUTPUTS / (stem + ".json"), JOB_OUTPUTS / (stem + ".log")


def clear_terminal_metadata(job):
    for stale in ("outcome", "reason", "finished_at", "integration_receipt", "integration_outcome"):
        job.pop(stale, None)


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
        if (job.get('state') == 'integrating' or job.get('verification_batch')) and payload.get('ticket_results'):
            payload = payload['ticket_results'].get(job['ticket_id'], payload)
        if job.get('state') == 'working' and job.get('verification_batch') and payload.get('status') == 'infrastructure_failed':
            payload = {'status': 'verification_pending', 'proposal': job['proposal'],
                       'verification_isolate': True, 'reason': payload.get('reason', 'batch process failed')}
        if payload.get('status') == 'verification_pending':
            if (payload.get('repaired_proposal') and
                    corrected_proposal_can_reverify(OPS, job, payload.get('proposal'))):
                job.pop('verification_remote_failed', None)
                payload = dict(payload, verification_isolate=False)
            if payload.get('verification_remote_failed'):
                job['verification_remote_failed'] = True
            job['verification_isolate'] = payload.get('verification_isolate', job.get('verification_isolate', False))
            job.pop('verification_batch', None)
            job.update(state='awaiting_verification', finished_at=now(), proposal=payload['proposal'],
                       updated_at=now(), waiting_reason=payload.get('reason', 'waiting for compilation/testing'))
            if job.get('verification_resume'):
                job['verification_attempts'] = max(0, int(job.get('verification_attempts', 0)) - 1)
            job.pop('pid', None)
            results.append({'worker': job.get('worker'), 'ticket_id': job['ticket_id'],
                            'status': 'verification_pending', 'proposal': payload['proposal']})
            changed = True
            continue
        job.pop("verification_batch", None)
        outcome = payload.get("status", "infrastructure_failed")
        if job.get('verification_resume') and outcome in ('source_unavailable', AUTHENTICATION_OUTCOME, RATE_LIMIT_OUTCOME):
            if outcome == AUTHENTICATION_OUTCOME:
                pause_worker_for_authentication(job, payload.get('receipt'))
            job.update(state='awaiting_verification', updated_at=now(),
                       verification_attempts=max(0, int(job.get('verification_attempts', 0)) - 1),
                       retry_after_epoch=int(time.time()) + int(policy().get('retry', {}).get('backoff_seconds', 300)),
                       waiting_reason=payload.get('reason', 'verification waits for source/provider availability'))
            if payload.get('receipt'):
                job['processed_receipt'] = payload['receipt']
            job.pop('pid', None)
            changed = True
            continue
        if job.get("state") == "integrating":
            final_state = "completed" if outcome in ("pushed_full_production_gate_green", "committed_locally_full_production_gate_green") else "awaiting_integration" if outcome in ("integration_busy", "integration_source_blocked", "push_deferred_deploy_lock_busy", "push_failed_after_full_gate") else "integration_failed"
            if final_state == 'awaiting_integration':
                job['integration_retry_after_epoch'] = int(time.time()) + int(policy().get('retry', {}).get('backoff_seconds', 300))
                if outcome in ('integration_busy', 'integration_source_blocked'):
                    job['integration_attempts'] = max(0, int(job.get('integration_attempts', 1)) - 1)
            elif outcome == 'full_gate_failed' and int(job.get('integration_wave_size', 1)) > 1:
                # Separate candidate-specific failures are already isolated in
                # the wave result. Only a shared final-wave failure is bisected.
                if not payload.get('gates'):
                    final_state = 'awaiting_integration'
                    job['integration_isolate'] = True
        else:
            settings = policy().get("retry", {})
            max_attempts = max_attempts_for_outcome(job, settings, outcome)
            record_profile_failure(job, outcome)
            if outcome == AUTHENTICATION_OUTCOME:
                refund_authentication_attempt(job, payload.get("receipt"))
                pause_worker_for_authentication(job, payload.get("receipt"))
                final_state = "queued"
            elif outcome == RATE_LIMIT_OUTCOME:
                refund_rate_limit_attempt(job, payload.get("receipt"))
                final_state = "queued"
            elif outcome == 'source_unavailable':
                refund_source_wait_attempt(job, payload.get('receipt'))
                final_state = 'queued'
            else:
                retryable = outcome.startswith("infrastructure_failed") and int(job.get("attempts", 0)) < max_attempts
                final_state = ("awaiting_integration" if outcome.startswith("accepted") else
                               "queued" if retryable else
                               "blocked" if outcome == "blocked_by_capability" else
                               "parked" if outcome == "parked" else "failed")
        if job.get('verification_resume') and final_state == 'queued' and job.get('proposal'):
            if int(job.get('verification_attempts', 0)) < int(policy().get('retry', {}).get('infrastructure_attempts', 3)):
                final_state = 'awaiting_verification'
                job['retry_after_epoch'] = int(time.time()) + int(policy().get('retry', {}).get('backoff_seconds', 300))
            else:
                final_state = 'failed'
        # Resumed jobs retain verification_resume during integration. Its receipt
        # must not replace the consumed observation: that makes reconciliation
        # rediscover the old acceptance and resubmit a conflicting patch forever.
        if job.get('state') == 'working' and job.get('verification_resume') and payload.get('receipt'):
            job['processed_receipt'] = payload['receipt']
        job.update({"state": final_state,
                    "outcome": outcome, "finished_at": now(), "updated_at": now()})
        job.pop("pid", None)
        if payload.get("receipt"):
            job["integration_receipt" if final_state in ("completed", "awaiting_integration", "integration_failed") and job.get("state") != "working" and "integration" in str(payload.get("receipt")) else "receipt"] = payload["receipt"]
        if payload.get("reason"):
            job["reason"] = payload["reason"]
        if final_state == "queued" and outcome == AUTHENTICATION_OUTCOME:
            job.pop("retry_after_epoch", None)
            job["reason"] = payload.get("reason", AUTHENTICATION_REASON)
            job["waiting_reason"] = "worker paused for provider login; this dispatch did not consume a retry"
        elif final_state == "queued" and outcome == RATE_LIMIT_OUTCOME:
            job.pop("retry_after_epoch", None)
            job["reason"] = payload.get("reason", RATE_LIMIT_REASON)
            job["waiting_reason"] = "OpenRouter cooldown active; this dispatch did not consume a retry"
        elif final_state == 'queued' and outcome == 'source_unavailable':
            job['retry_after_epoch'] = int(time.time()) + max(5, int(settings.get('backoff_seconds', 300)))
            job['waiting_reason'] = 'waiting for available canonical source; no model attempt consumed'
        elif final_state == "queued":
            job["retry_after_epoch"] = int(time.time()) + max(0, int(settings.get("backoff_seconds", 300)))
            job["waiting_reason"] = "bounded infrastructure retry %d/%d after backoff" % (int(job.get("attempts", 0)) + 1, max_attempts)
        results.append({"worker": job.get("worker"), "ticket_id": job["ticket_id"], "status": outcome,
                        **({"receipt": payload["receipt"]} if payload.get("receipt") else {})})
        log("worker=%s status=%s ticket=%s" % (job.get("worker", "?"), outcome, job["ticket_id"]))
        changed = True
    if changed:
        save_jobs(jobs)


def dispatch_one(results, queued, availability=None):
    jobs, by_profile = sync_jobs()
    reconcile_running(jobs, results)
    recovered = recover_remote_batch_fallbacks(OPS, jobs['jobs'], now())
    if recovered:
        results.append({'worker': 'verification-harness', 'status': 'remote_individual_verification_recovered',
                        'tickets': recovered})
        log('remote batch attribution corrected; individual verification eligible: ' + ', '.join(recovered))
    recovered = recover_bundle_export_fallbacks(OPS, jobs['jobs'], now())
    if recovered:
        results.append({'worker': 'verification-harness', 'status': 'bundle_export_transport_recovered',
                        'tickets': recovered})
        log('incremental bundle export transport retry eligible: ' + ', '.join(recovered))
    problem = source_problem(SOURCE)
    if problem:
        results.append({'worker': 'dispatch', 'status': 'source_unavailable', 'reason': problem})
        save_jobs(jobs)
        return jobs
    # Admit completed work before another verification retry can take the slot.
    # This also runs between producers, rather than only after a full sweep.
    dispatch_integration(jobs, results)
    remote = policy().get('verification', {}).get('remote', {})
    remote_status = load_json(OPS / 'state/factory-ng-remote-status.json') or {}
    if (remote.get('enabled') is True and remote.get('id')
            and int(remote_status.get('retry_after_epoch', 0)) <= int(time.time())):
        slots = max(1, min(4, int(remote.get('slots', 1))))
        # Drain a pre-slots proxy before admitting the new slot identities.
        legacy_busy = slots > 1 and any(j.get('state') == 'working' and
            j.get('verification_host') == remote['id'] for j in jobs['jobs'].values())
        if not legacy_busy:
            for slot in range(slots):
                host = remote['id'] if slots == 1 else remote['id'] + '-' + str(slot + 1)
                dispatch_verification_batch(jobs, results, host=host, slot=slot)
    dispatch_verification_batch(jobs, results)
    availability = availability or worker_availability(by_profile)
    queue_settings = policy().get('queue', {})
    attention_recovery.admit(
        OPS, jobs['jobs'], now(),
        max(effective_target_ready(queue_settings, by_profile),
            int(queue_settings.get('max_queued', 12))),
        len(queue_inventory(jobs, by_profile, availability)['runnable']))
    selected = next_dispatch(jobs, by_profile, availability)
    if not selected:
        save_jobs(jobs)
        return jobs
    for path, job, worker in selected:
        if stopping:
            break
        ticket_id = job["ticket_id"]
        if ticket_id not in queued:
            queued.append(ticket_id)
        resuming = job.get("state") == "awaiting_verification"
        if resuming and not compilation_status(policy())["allowed"]:
            continue
        selected_model = job.get("model", worker["model"]) if resuming else worker["model"]
        clear_terminal_metadata(job)
        job.update({"state": "working", "worker": worker["id"], "model": selected_model,
                    "dispatch_profile": worker["profile"],
                    "started_at": now(), "updated_at": now(),
                    "attempts": int(job.get("attempts", 0)) + (0 if resuming else 1)})
        result_file, log_file = job_files(ticket_id)
        if worker["profile"] == "qwen-prepared-direct@1.0.2":
            command = [sys.executable, str(OPS / "scripts/factory-ng-run-map-ticket.py"),
                       "--ticket", str(OPS / path), "--worker", worker["id"], "--model", selected_model]
        else:
            command = [sys.executable, str(OPS / "scripts/factory-ng-run-engine-ticket.py"),
                       "--ticket", str(OPS / path), "--worker", worker["id"], "--model", selected_model,
                       "--profile", worker["profile"]]
        if resuming:
            command.extend(["--resume-proposal", str(OPS / job["proposal"])])
            if (job.get('verification_remote_failed') and job.get('result_path') and
                    worker['profile'] in ('claude-staged@1.0.0', 'codex-constrained@1.1.0', QWEN_GOOSE_PROFILE, OPENROUTER_GOOSE_PROFILE)):
                command.extend(['--repair-evidence', str(OPS / job['result_path'])])
            if (remote.get('enabled') is True and int(policy().get('verification', {}).get('batch_size', 1)) > 1 and
                    int(remote_status.get('retry_after_epoch', 0)) <= int(time.time()) and
                    worker['profile'] in ('claude-staged@1.0.0', 'codex-constrained@1.1.0', QWEN_GOOSE_PROFILE, OPENROUTER_GOOSE_PROFILE)):
                command.append('--defer-repaired-verification')
            if job.get('verification_repair_only'):
                command.append('--repair-only')
                if '--defer-repaired-verification' not in command:
                    command.append('--defer-repaired-verification')
            job["verification_attempts"] = int(job.get("verification_attempts", 0)) + 1
        elif policy().get('verification', {}).get('batch_size', 1) > 1:
            command.append('--defer-verification')
        job.pop('verification_batch', None)
        job["verification_resume"] = resuming
        job['verification_host'] = 'model-repair' if resuming and job.get('verification_repair_only') else 'local'
        with result_file.open("w") as stdout, log_file.open("w") as stderr:
            process = subprocess.Popen(command, cwd=OPS, stdout=stdout, stderr=stderr, start_new_session=True)
        job.update({"pid": process.pid, "result_path": str(result_file.relative_to(OPS)),
                    "log_path": str(log_file.relative_to(OPS))})
        results.append({"worker": worker["id"], "ticket_id": ticket_id, "status": "working"})
        log("worker=%s status=working ticket=%s pid=%s" % (worker["id"], ticket_id, process.pid))
    save_jobs(jobs)
    return jobs


def dispatch_verification_batch(jobs, results, host='local', slot=0):
    settings = policy().get('verification', {})
    if int(settings.get('batch_size', 1)) <= 1 or not compilation_status(policy())['allowed']:
        return
    if verification_slot_busy(jobs, host):
        return
    selected, revision = [], None
    for _, job in sorted(jobs['jobs'].items(), key=dispatch_priority):
        if (job.get('state') != 'awaiting_verification'
                or (host == 'local' and job.get('verification_isolate'))
                or (host != 'local' and job.get('verification_remote_failed'))
                or job.get('superseded_by') or int(job.get('retry_after_epoch', 0)) > int(time.time())):
            continue
        ticket = load_json(OPS / job['ticket_path']) or {}
        base = ticket.get('source', {}).get('revision')
        if job.get('verification_isolate') and selected:
            continue
        if not base or (revision is not None and base != revision):
            continue
        selected.append(job)
        revision = base
        if job.get('verification_isolate') or len(selected) >= min(8, int(settings['batch_size'])):
            break
    if not selected:
        return
    collection = dict(settings, wave_size=settings['batch_size'])
    # An isolated proposal must run alone, so another arrival cannot make
    # its batch fuller. Do not apply the ordinary collection delay to it.
    wait = 0 if selected[0].get('verification_isolate') else integration_collection_wait(selected, jobs, collection)
    if wait:
        results.append({'worker': 'verification-harness', 'status': 'collecting_verification',
                        'candidates': len(selected), 'remaining_seconds': wait})
        return
    result_file, log_file = job_files(selected[0]['ticket_id'] + '-verification-' + host)
    manifest = result_file.with_suffix('.manifest.json')
    manifest.write_text(json.dumps([{'ticket_id': job['ticket_id'], 'ticket_path': job['ticket_path'],
                                    'proposal': job['proposal'],
                                    'identity': {'worker': job['worker'], 'model': job['model'],
                                                 'profile': job['dispatch_profile']}} for job in selected]))
    script = 'factory-ng-verify-batch.py' if host == 'local' else 'factory-ng-verify-remote.py'
    command = [sys.executable, str(OPS / 'scripts' / script), '--manifest', str(manifest)]
    if host != 'local':
        command.extend(['--slot', str(slot)])
    with result_file.open('w') as stdout, log_file.open('w') as stderr:
        process = subprocess.Popen(command, cwd=OPS, stdout=stdout, stderr=stderr, start_new_session=True)
    for job in selected:
        job.update(state='working', pid=process.pid, verification_batch=True, verification_resume=True,
                   verification_host=host,
                   verification_attempts=int(job.get('verification_attempts', 0)) + 1,
                   result_path=str(result_file.relative_to(OPS)), log_path=str(log_file.relative_to(OPS)),
                   started_at=now(), updated_at=now())
        results.append({'worker': 'verification-harness', 'ticket_id': job['ticket_id'],
                        'status': 'verifying_batch', 'batch_size': len(selected), 'verification_host': host})
    save_jobs(jobs)


def integration_collection_wait(selected, jobs, settings, epoch=None):
    """Briefly collect a wave while workers can still produce another patch.

    Anchor the deadline to the oldest accepted patch, so arrivals and controller
    restarts never extend it. Isolated retries and an idle fleet never wait.
    """
    window = max(0, min(300, int(settings.get('collect_seconds', 120))))
    target = max(1, min(int(settings.get('wave_size', 8)),
                        int(settings.get('collect_min_candidates', 3))))
    if (not selected or len(selected) >= target or not window
            or any(j.get('integration_isolate') for j in selected)
            or not any(j.get('state') == 'working' and not j.get('superseded_by')
                       for j in jobs['jobs'].values())):
        return 0
    epoch = time.time() if epoch is None else epoch
    try:
        stamps = [datetime.fromisoformat(j['finished_at'].replace('Z', '+00:00'))
                  for j in selected]
        # Missing/invalid timestamps must never strand legacy receipts.
        if any(s.tzinfo is None for s in stamps):
            return 0
        oldest = min(s.timestamp() for s in stamps)
    except (KeyError, TypeError, ValueError, AttributeError):
        return 0
    if oldest > epoch:
        return 0
    return max(0, int(oldest + window - epoch + 0.999))


def dispatch_integration(jobs, results):
    if not compilation_status(policy())["allowed"]:
        return
    if not policy().get('integration', {}).get('automatic', False):
        return
    overlap = policy().get('verification', {}).get('overlap_integration') is True
    if any(job.get("state") == "integrating" or
           (not overlap and job.get("state") == "working" and job.get("verification_resume"))
           for job in jobs["jobs"].values()):
        return
    problem = source_problem(SOURCE)
    if problem:
        results.append({'worker': 'integration-harness', 'status': 'integration_source_blocked', 'reason': problem})
        return
    selected = []
    wave_size = max(1, int(policy().get('integration', {}).get('wave_size', 8)))
    for job in sorted(jobs["jobs"].values(), key=lambda item: (item.get('work_type') != 'map', item.get("finished_at", ""))):
        if job.get('superseded_by'):
            continue
        if job.get("state") != "awaiting_integration" or not job.get("receipt"):
            continue
        if int(job.get('integration_retry_after_epoch', 0)) > int(time.time()):
            continue
        if job.get('integration_isolate') and selected:
            continue
        selected.append(job)
        if len(selected) >= wave_size or job.get('integration_isolate'):
            break
    if not selected:
        return
    wait_seconds = integration_collection_wait(selected, jobs, policy().get('integration', {}))
    if wait_seconds:
        results.append({'worker': 'integration-harness', 'status': 'collecting_wave',
                        'candidates': len(selected), 'remaining_seconds': wait_seconds})
        return
    result_file, log_file = job_files(selected[0]['ticket_id'] + '-integration')
    command = [sys.executable, str(OPS / 'scripts/factory-ng-integrate.py')]
    for job in selected:
        command.extend(['--receipt', str(OPS / job['receipt'])])
    with result_file.open('w') as stdout, log_file.open('w') as stderr:
        process = subprocess.Popen(command, cwd=OPS, stdout=stdout, stderr=stderr, start_new_session=True)
    for job in selected:
        job.update({"state": "integrating", "pid": process.pid,
                    "integration_attempts": int(job.get('integration_attempts', 0)) + 1,
                    "integration_wave_size": len(selected),
                    "result_path": str(result_file.relative_to(OPS)),
                    "log_path": str(log_file.relative_to(OPS)), "updated_at": now()})
        results.append({"worker": "integration-harness", "ticket_id": job["ticket_id"], "status": "integrating"})
        log("integration status=working ticket=%s pid=%s" % (job["ticket_id"], process.pid))
    save_jobs(jobs)


last_producer_results = []


def producer_lane_admission(payload, admission):
    """Reserve runnable queue slots for Map work before persisting Engine work."""
    if not admission or payload.get("ticket", {}).get("work_type") != "engine":
        return True, None
    queued_engine = int(admission.get("runnable_engine", 0))
    engine_cap = max(0, int(admission["max_runnable"]) - int(admission["map_reserve"]))
    if queued_engine < engine_cap:
        return True, None
    return False, ("Map reserve holds %d runnable queue slot(s); Engine queue is at its cap of %d" %
                   (int(admission["map_reserve"]), engine_cap))


_producer_last_dispatch = None


def producer_command(command, timeout, results, queued, tick_seconds=15):
    """Wait for producer I/O while the owning thread keeps leases moving.

    Only subprocess execution leaves this thread. All job reconciliation,
    dispatch, integration and ticket publication retain their single owner.
    """
    global _producer_last_dispatch
    if _producer_last_dispatch is None:
        _producer_last_dispatch = time.monotonic()
    def service():
        global _producer_last_dispatch
        if not stopping:
            jobs = dispatch_one(results, queued)
            dispatch_integration(jobs, results)
        _producer_last_dispatch = time.monotonic()
    # The deadline spans adjacent short producers as well as a single slow one.
    if time.monotonic() - _producer_last_dispatch >= tick_seconds:
        service()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(subprocess.run, command, cwd=OPS,
                                 capture_output=True, text=True, timeout=timeout)
        while True:
            try:
                return future.result(timeout=max(.001, tick_seconds - (time.monotonic() - _producer_last_dispatch)))
            except FutureTimeout:
                if future.done():
                    return future.result()
                service()


def run_producer(producer_id, command, timeout, results, queued, admission=None):
    """Run and persist one deterministic producer result."""
    write_status(state="running", phase="producing_ticket", active=[{"kind": "producer", "id": producer_id}],
                 queued=queued, results=results, message="Replenishing the automatic ground-truth queue.")
    try:
        completed = producer_command(command, timeout, results, queued)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = {"status": "producer_error",
                       "reason": completed.stderr[-500:] or completed.stdout[-500:] or
                       "producer returned no machine-readable result"}
        if completed.returncode != 0:
            payload = {"status": "producer_error",
                       "reason": completed.stderr[-500:] or completed.stdout[-500:] or
                       "producer exited with status %d" % completed.returncode}
    except subprocess.TimeoutExpired:
        # A slow or broken producer must not starve independent producers or
        # prevent already-runnable tickets from reaching workers.
        payload = {"status": "producer_error", "reason": "timed out after %d seconds" % timeout}
    status = payload.get("status", "producer_error")
    ticket_id = payload.get("ticket_id")
    if stopping:
        return 'stopping'
    if status == "ready":
        try:
            # Dispatch may have changed the reserve while the producer ran.
            if admission is not None:
                live_jobs, profiles = sync_jobs()
                live_inventory = queue_inventory(live_jobs, profiles, worker_availability(profiles))
                admission = dict(admission, runnable_engine=sum(
                    live_jobs['jobs'].get(key, {}).get('work_type') == 'engine'
                    for key in live_inventory['runnable']))
            allowed, reason = producer_lane_admission(payload, admission)
            if (allowed and payload.get('ticket', {}).get('production', {}).get('attention_recovery_parent')
                    and not attention_recovery.dependency_admission(OPS, load_jobs()['jobs'], payload)):
                allowed, reason = False, 'Reviewed recovery cohort already has six active tickets.'
            if allowed:
                status, ticket_id = persist_ready(payload)
            else:
                status = "lane_capacity_reserved"
                payload["reason"] = reason
        except (KeyError, OSError, ValueError) as exc:
            status = "producer_error"
            payload["reason"] = str(exc)
    item = {"producer": producer_id, "status": status}
    if payload.get('candidate_errors'):
        item['candidate_errors'] = payload['candidate_errors']
        item['candidate_error_count'] = payload.get('candidate_error_count', len(payload['candidate_errors']))
    if ticket_id:
        item["ticket_id"] = ticket_id
    if payload.get("reason"):
        item["reason"] = payload["reason"]
    if status == "parent_satisfied" and ticket_id:
        jobs = load_jobs()
        job = jobs["jobs"].get(ticket_id)
        if job:
            job.update({"state": "completed", "outcome": "ground_truth_satisfied_after_dependency",
                        "finished_at": now(), "updated_at": now()})
            job.pop("waiting_reason", None)
            save_jobs(jobs)
    if status == 'recovery_dependency' and ticket_id:
        jobs = load_jobs()
        job = jobs['jobs'].get(ticket_id)
        if job:
            job['priority_recovery_parent'] = payload['parent_id']
            save_jobs(jobs)
    results.append(item)
    if status == "queued" and ticket_id:
        queued.append(ticket_id)
    log("producer=%s status=%s ticket=%s%s" % (
        producer_id, status, ticket_id or "-",
        (" reason=%s" % payload["reason"].replace("\n", " ")[:200]) if payload.get("reason") else ""))
    return status


def dependency_resume_slot_available(jobs, reserve):
    active = sum(job.get('work_type') == 'map' and not job.get('superseded_by')
                 and job.get('state') in ('queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating')
                 and job.get('production', {}).get('producer') == 'capability-dependencies'
                 for job in jobs['jobs'].values())
    return active < reserve


def engine_integration_repair_slot_available(jobs, reserve):
    active = sum(job.get('work_type') == 'engine' and not job.get('superseded_by')
                 and job.get('state') in ('queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating')
                 and INTEGRATION_REPAIR_MARKER in str(job.get('production', {}).get('key', ''))
                 for job in jobs['jobs'].values())
    return active < reserve


def reserve_engine_integration_repair(producer_set, jobs, reserve, results, queued):
    if not engine_integration_repair_slot_available(jobs, reserve):
        return False
    if not any(job.get('work_type') == 'engine' and job.get('state') == 'integration_failed'
               and not job.get('superseded_by') and not job.get('repair_blocker')
               for job in jobs['jobs'].values()):
        return False
    for producer_id, command, timeout in producer_set:
        if producer_id == 'capability-dependencies':
            run_producer(producer_id, command + ['--engine-integration-repairs-only'], timeout,
                         results, queued, admission=None)
            return True
    return False


def producer_loop_needed(inventory, target_ready, max_runnable, first_round):
    """Deferred inventory is durable history, not runnable queue capacity."""
    return (len(inventory["runnable"]) < max_runnable and
            (first_round or len(inventory["runnable"]) < target_ready))


def producer_burst_limit(producer_id):
    """Opt-in bounded refill before slow discovery; all admissions still apply."""
    entries = (load_json(PRODUCER_CONFIG) or {}).get('producers', [])
    item = next((p for p in entries if p.get('id') == producer_id), {})
    value = item.get('refill_burst', 1)
    return max(1, min(24, value)) if type(value) is int else 1


def active_producer_jobs(jobs):
    return frozenset(key for key, job in jobs['jobs'].items()
                     if not job.get('superseded_by') and job.get('state') in
                     ('queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating'))


def run_supply_producer(producer_id, command, timeout, results, queued, admission,
                        attempts, source_retries):
    """Spend ordinary sweep budget on at most one clean-base race retry."""
    status = run_producer(producer_id, command, timeout, results, queued, admission)
    attempts -= 1
    latest = next((r for r in reversed(results) if r.get('producer') == producer_id), {})
    if (status == 'source_unavailable' and attempts > 0 and not stopping
            and producer_burst_limit(producer_id) > 1 and producer_id not in source_retries
            and latest.get('reason') in (
                'source changed during reviewed production',
                'canonical source changed during producer scan; retry on current source')
            and not source_problem(SOURCE)):
        source_retries.add(producer_id)
        log('producer=%s retry=clean_source_advanced remaining_sweep_budget=%s' % (producer_id, attempts))
        status = run_producer(producer_id, command, timeout, results, queued, admission)
        attempts -= 1
    return status, attempts


def refill_after_drain(blocked, producer_set, next_id, attempts, jobs, by_profile,
                       inventory, availability, admission, target, results, queued, source_retries):
    """Revisit a bounded ready source when tests free its admission capacity.

    This runs only between producer commands, on the controller's owning
    thread. The producer still checks its own cohort bound; every extra call
    consumes the ordinary sweep budget and uses ordinary queue admission.
    """
    if not blocked or attempts <= 0 or stopping:
        return attempts, jobs, by_profile, inventory
    jobs = load_jobs()  # producer_command services and persists live completions
    inventory = queue_inventory(jobs, by_profile, availability)
    active = active_producer_jobs(jobs)
    for producer_id, command, timeout in producer_set:
        previous = blocked.get(producer_id)
        if (producer_id == next_id or previous is None or not previous - active
                or len(inventory['runnable']) >= target):
            continue
        for _ in range(producer_burst_limit(producer_id)):
            if attempts <= 0 or stopping or len(inventory['runnable']) >= target:
                break
            status, attempts = run_supply_producer(producer_id, command, timeout, results, queued,
                                                   admission, attempts, source_retries)
            jobs, by_profile = sync_jobs()
            inventory = queue_inventory(jobs, by_profile, availability)
            admission['runnable_engine'] = sum(jobs['jobs'].get(key, {}).get('work_type') == 'engine'
                                               for key in inventory['runnable'])
            active = active_producer_jobs(jobs)
            if status == 'reviewed_harness_reserve_full':
                blocked[producer_id] = active
            elif status != 'queued':
                blocked.pop(producer_id, None)
            if status != 'queued':
                break
    return attempts, jobs, by_profile, inventory


def effective_target_ready(queue_settings, by_profile):
    """Keep a configurable runnable buffer per enabled physical worker."""
    minimum = max(1, int(queue_settings.get("target_ready", 1)))
    per_worker = max(0, int(queue_settings.get("ready_per_worker", 0)))
    return max(minimum, per_worker * len(physical_worker_keys(by_profile)))


def producer_fill_target(target_ready, max_queued, by_profile, availability):
    """Fill the reserve plus every lease that could open during this sweep."""
    dispatch_slots = sum(
        1 for profile, workers in by_profile.items() for worker in workers
        if availability.get(profile, {}).get(worker.get("id") or profile, {}).get("allowed", False)
    )
    return min(max_queued, target_ready + dispatch_slots)


def producer_queue_cap(max_queued, jobs, target_ready=0):
    """Reserve retry headroom without reducing the configured ready reserve."""
    active_workers = sum(job.get("state") == "working" for job in jobs["jobs"].values())
    return max(min(target_ready, max_queued), max_queued - active_workers, 0)


def reserve_refill_due(runtime):
    """Refill promptly after leases, but do not spin on an exhausted frontier."""
    queue = runtime.get("queue") if isinstance(runtime.get("queue"), dict) else {}
    runnable = int(queue.get("runnable", 0))
    fill_target = int(queue.get("fill_target", queue.get("target_ready", 0)))
    admission_cap = int(queue.get("admission_cap", queue.get("max_queued", fill_target)))
    latest = {item['producer']: item.get('status') for item in runtime.get('results', [])
              if item.get('producer')}
    producer_progress = any(status in ('queued', 'scan_pending') for status in latest.values())
    return bool(fill_target and runnable < fill_target and
                runnable < admission_cap and producer_progress)


def run_once(produce=True):
    global last_producer_results
    results, queued = list(last_producer_results), []
    pace_paused = bool((load_json(STATE) or {}).get("pace_paused", False))
    if produce:
        results = []
        producer_set = producers()
        queue_settings = policy().get("queue", {})
        jobs, by_profile = sync_jobs()
        target_ready = effective_target_ready(queue_settings, by_profile)
        max_queued = max(target_ready, int(queue_settings.get("max_queued", target_ready * 4)))
        jobs = dispatch_one(results, queued)
        dispatch_integration(jobs, results)
        jobs, by_profile = sync_jobs()
        availability = worker_availability(by_profile)
        pace_paused = all_workers_pace_paused(by_profile, availability)
        # A paced hold is a scheduled pause, not an empty supply frontier.
        # Keep reconciliation above this point, but make every producer path
        # below a no-op until at least one worker can accept a lease.
        if pace_paused:
            producer_set = []
        inventory = queue_inventory(jobs, by_profile, availability)
        write_status(state='running', phase='planning', active=[], queued=inventory['runnable'],
                     deferred=inventory['deferred'], queue={'runnable': len(inventory['runnable']),
                     'deferred': len(inventory['deferred']), 'total': inventory['total'],
                     'target_ready': target_ready}, results=results,
                     message='Queue inventory measured before producer sweep.')
        admission_cap = producer_queue_cap(max_queued, jobs, target_ready)
        map_reserve = max(0, min(admission_cap, int(queue_settings.get("map_reserve", 0))))
        producer_admission = {
            "max_runnable": admission_cap,
            "map_reserve": map_reserve,
            "runnable_engine": sum(
                jobs["jobs"].get(ticket_id, {}).get("work_type") == "engine"
                for ticket_id in inventory["runnable"]),
        }
        # A large recovered queue must not starve already-accepted Map
        # obligations. Admit at most a tiny replacement-repair reserve even
        # when ordinary fresh production is at capacity.
        repair_reserve = max(0, int(queue_settings.get('integration_repair_reserve', 2)))
        outstanding_repairs = sum(
            job.get('work_type') == 'map' and not job.get('superseded_by')
            and job.get('state') in ('queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating')
            and job.get('production', {}).get('retry_reason') in ('integration_conflict_repair', 'context_repair')
            for job in jobs['jobs'].values())
        outstanding_recovery_engines = sum(
            job.get('work_type') == 'engine' and not job.get('superseded_by')
            and job.get('state') in ('queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating')
            and bool(job.get('priority_recovery_parent') or job.get('production', {}).get('integration_recovery_parent'))
            for job in jobs['jobs'].values())
        recovery_maps = any(
            job.get('work_type') == 'map' and job.get('state') == 'blocked' and not job.get('superseded_by')
            and (job.get('production', {}).get('integration_repair_generation')
                 or job.get('production', {}).get('integration_recovery_parent'))
            for job in jobs['jobs'].values())
        if (not stopping and recovery_maps and len(inventory['runnable']) >= admission_cap
                and outstanding_recovery_engines < repair_reserve):
            for producer_id, command, timeout in producer_set:
                if producer_id != 'capability-dependencies':
                    continue
                run_producer(producer_id, command + ['--integration-recovery-only'], timeout,
                             results, queued, admission=None)
                jobs, by_profile = sync_jobs()
                inventory = queue_inventory(jobs, by_profile, availability)
                break
        if (not stopping and len(inventory['runnable']) >= admission_cap
                and outstanding_repairs < repair_reserve):
            for producer_id, command, timeout in producer_set:
                if producer_id != 'build-plan-integration-conflict':
                    continue
                if run_producer(producer_id, command, timeout, results, queued, producer_admission) == 'queued':
                    jobs, by_profile = sync_jobs()
                    inventory = queue_inventory(jobs, by_profile, availability)
                break
        # Completed Engine work must reach its Map verification even while a
        # recovered ordinary backlog exceeds the normal admission cap. This
        # reserve can only create Map resumes, never more Engine demand.
        if (not stopping and len(inventory['runnable']) >= admission_cap
                and dependency_resume_slot_available(jobs, repair_reserve)):
            for producer_id, command, timeout in producer_set:
                if producer_id != 'capability-dependencies':
                    continue
                run_producer(producer_id, command + ['--completed-dependencies-only'], timeout,
                             results, queued, admission=None)
                jobs, by_profile = sync_jobs()
                inventory = queue_inventory(jobs, by_profile, availability)
                break
        fill_target = producer_fill_target(target_ready, admission_cap, by_profile, availability)
        # Failed Engine integrations owe a bounded repair even when old
        # ordinary work exceeds admission capacity. This producer mode cannot
        # create new capability demand or replay a completed/superseded job.
        if not stopping and reserve_engine_integration_repair(producer_set, jobs, repair_reserve, results, queued):
            jobs, by_profile = sync_jobs()
            inventory = queue_inventory(jobs, by_profile, availability)
            producer_admission['runnable_engine'] = sum(
                jobs['jobs'].get(ticket_id, {}).get('work_type') == 'engine'
                for ticket_id in inventory['runnable'])
        cohort_ids = {'staged-five-card-trial', 'context-retry-batch'}
        cohort_producers = [p for p in producer_set if p[0] in cohort_ids]
        remaining_producers = [p for p in producer_set if p[0] not in cohort_ids]
        # A deferred result must not consume runnable capacity. Keep the sweep
        # itself bounded even when every producer discovers deferred work.
        attempts_left = max(0, admission_cap - len(inventory["runnable"])) + len(remaining_producers)
        blocked_refillers = {}
        source_retries = set()
        first_round = True
        # Round-robin producers so deferred Engine dependencies cannot crowd
        # out runnable local Map work. Paused tickets remain durable inventory
        # but never satisfy the runnable reserve.  Always perform one producer
        # sweep when the bounded queue has capacity: a raw ticket count is not
        # proof that the queue contains the newest gate-informed repair.
        while (producer_loop_needed(inventory, fill_target, admission_cap, first_round) and
               attempts_left > 0 and remaining_producers and not stopping):
            progress = False
            next_round = []
            for producer_id, command, timeout in remaining_producers:
                if stopping:
                    break
                budget_before_refill = attempts_left
                attempts_left, jobs, by_profile, inventory = refill_after_drain(
                    blocked_refillers, producer_set, producer_id, attempts_left, jobs, by_profile,
                    inventory, availability, producer_admission, fill_target, results, queued, source_retries)
                if attempts_left != budget_before_refill:
                    write_status(queued=inventory['runnable'], deferred=inventory['deferred'],
                                 queue={'runnable': len(inventory['runnable']),
                                        'deferred': len(inventory['deferred']), 'total': inventory['total'],
                                        'target_ready': target_ready, 'fill_target': fill_target,
                                        'max_queued': max_queued, 'admission_cap': admission_cap})
                if attempts_left <= 0 or len(inventory['runnable']) >= admission_cap:
                    break
                status, attempts_left = run_supply_producer(producer_id, command, timeout, results, queued,
                                                            producer_admission, attempts_left, source_retries)
                if status in ("queued", "scan_pending"):
                    progress = True
                    next_round.append((producer_id, command, timeout))
                elif producer_id == 'capability-dependencies' and status == 'awaiting_dependency':
                    # Model results arriving during this sweep can introduce
                    # new demand after the dependency producer found none.
                    next_round.append((producer_id, command, timeout))
                if status == "queued":
                    jobs, by_profile = sync_jobs()
                    inventory = queue_inventory(jobs, by_profile, availability)
                    producer_admission["runnable_engine"] = sum(
                        jobs["jobs"].get(ticket_id, {}).get("work_type") == "engine"
                        for ticket_id in inventory["runnable"])
                # A finite ready frontier may refill several slots before
                # expensive corpus scans. The global sweep budget, runnable
                # cap, producer cohort cap and every admission gate remain.
                for _ in range(1, producer_burst_limit(producer_id)):
                    if (status != 'queued' or stopping or attempts_left <= 0
                            or len(inventory['runnable']) >= fill_target):
                        break
                    status, attempts_left = run_supply_producer(producer_id, command, timeout, results, queued,
                                                                producer_admission, attempts_left, source_retries)
                    if status != 'queued':
                        break
                    jobs, by_profile = sync_jobs()
                    inventory = queue_inventory(jobs, by_profile, availability)
                    producer_admission['runnable_engine'] = sum(
                        jobs['jobs'].get(key, {}).get('work_type') == 'engine' for key in inventory['runnable'])
                    write_status(queued=inventory['runnable'], deferred=inventory['deferred'],
                                 queue={'runnable': len(inventory['runnable']),
                                        'deferred': len(inventory['deferred']), 'total': inventory['total'],
                                        'target_ready': target_ready, 'fill_target': fill_target,
                                        'max_queued': max_queued, 'admission_cap': admission_cap})
                if producer_burst_limit(producer_id) > 1:
                    if status == 'reviewed_harness_reserve_full':
                        blocked_refillers[producer_id] = active_producer_jobs(jobs)
                    elif status != 'queued':
                        blocked_refillers.pop(producer_id, None)
                if len(inventory["runnable"]) >= admission_cap or (not first_round and
                                                                  len(inventory["runnable"]) >= fill_target):
                    break
            first_round = False
            if not progress:
                break
            remaining_producers = next_round
        # Keep the bounded cohorts admitted even when the ordinary queue is
        # full, but refill available worker leases before their slow historical
        # scans. They still run once in every producer cycle, with their own
        # unchanged two-active admission limits.
        for producer_id, command, timeout in ([] if pace_paused else cohort_producers):
            if stopping:
                break
            run_producer(producer_id, command, timeout, results, queued, admission=None)
            jobs, by_profile = sync_jobs()
            inventory = queue_inventory(jobs, by_profile, availability)
        last_producer_results = list(results)
    if stopping:
        return
    jobs = dispatch_one(results, queued)
    dispatch_integration(jobs, results)
    active = [{"kind": "integration" if job.get("state") == "integrating" else "worker",
               "id": "integration-harness" if job.get("state") == "integrating" else job.get("worker"),
               "model": job.get("model"), "ticket_id": job["ticket_id"], "state": job.get("state")}
              for job in jobs["jobs"].values() if job.get("state") in ("working", "integrating")]
    producer_results = [item for item in results if item.get("producer")]
    durable_queued = [key for key, job in sorted(
        ((key, job) for key, job in jobs['jobs'].items() if job.get('state') == 'queued' and not job.get('superseded_by')),
        key=dispatch_priority)]
    by_profile = configured_workers_by_profile((load_json(WORKERS) or {}).get("workers", []))
    availability = worker_availability(by_profile)
    inventory = queue_inventory(jobs, by_profile, availability)
    final_queue_settings = policy().get("queue", {})
    final_target_ready = effective_target_ready(final_queue_settings, by_profile)
    final_max_queued = max(final_target_ready, int(final_queue_settings.get(
        "max_queued", final_target_ready * 4)))
    final_admission_cap = producer_queue_cap(final_max_queued, jobs, final_target_ready)
    final_fill_target = producer_fill_target(
        final_target_ready, final_admission_cap, by_profile, availability)
    exhausted = bool(producer_results) and all(item.get("status") in
                                               ("duplicate_active", "duplicate_terminal", "already_registered",
                                                "no_existing_dispatcher", "ground_truth_changed", "needs_primitive",
                                                "no_safe_candidate", "exhausted_supported_plan")
                                               for item in producer_results)
    message = ("Factory NG has active isolated work; final states will be retained with immutable receipts." if active else
               "All enabled workers are pace-gated; automatic producers are paused until a worker lease opens." if pace_paused else
               "Current safe producer frontier is exhausted; automatic discovery will rescan current ground truth." if exhausted else
               "%d tickets are deferred, but no runnable ticket exists; automatic producers remain armed." % len(inventory["deferred"]) if not inventory["runnable"] and inventory["deferred"] else
               "No runnable tickets exist; workers are idle while producers search current ground truth." if not inventory["runnable"] else
               "Runnable ticket reserve is available; waiting for a compatible worker lease.")
    pending_count = sum(j.get('state') == 'awaiting_verification' and not j.get('superseded_by')
                        for j in jobs['jobs'].values())
    if not compilation_status(policy())['allowed']:
        message = ('Workers may prepare patches. Compilation/testing is off; %d saved patches await verification. '
                   'Enable Compilation & testing on the dashboard to run the checks and integration.' % pending_count)
    pause_state = load_worker_pauses()
    write_status(state="running", pending_verification=pending_count, phase="building" if active else "waiting_for_ticket", active=active, queued=durable_queued,
                 deferred=inventory["deferred"], queue={"runnable": len(inventory["runnable"]),
                 "deferred": len(inventory["deferred"]), "total": inventory["total"],
                 "target_ready": final_target_ready, "fill_target": final_fill_target,
                 "max_queued": final_max_queued, "admission_cap": final_admission_cap},
                 jobs=list(jobs["jobs"].values()), results=results, message=message,
                 supply=load_json(OPS / 'state/factory-ng-frontier.json'),
                 archived_jobs=sum(archived(job) for job in jobs['jobs'].values()),
                 backlog_jobs=sum(job.get('state') == 'backlog' and not job.get('superseded_by') for job in jobs['jobs'].values()),
                 pace_paused=pace_paused,
                 worker_pauses=list(pause_state.get("workers", {}).values()),
                 authentication_recovery=jobs.get("oauth_retry_migration_v1"))


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
    controller_lock = open(OPS / 'state/factory-ng-controller.lock', 'a+')
    try:
        fcntl.flock(controller_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('a Factory NG controller already owns job reconciliation')
    if args.interval < 5 or args.producer_interval < args.interval:
        parser.error("--interval must be at least 5 seconds and --producer-interval must not be shorter")
    apply_resources(policy())
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGHUP, stop_handler)
    write_status(state="running", phase="starting", active=[], queued=[], results=[],
                 message="Factory NG controller started.")
    next_production = 0
    while not stopping:
        try:
            current = time.monotonic()
            refill = reserve_refill_due(load_json(STATE) or {})
            should_produce = current >= next_production or refill
            run_once(produce=should_produce)
            if should_produce:
                next_production = current + args.producer_interval
        except Exception as exc:  # keep the controller observable and retryable
            log("controller_error=%s" % exc)
            write_status(state="running", phase="producer_error", active=[], queued=[],
                         results=[{"producer": "controller-sweep", "status": "producer_error",
                                   "reason": str(exc)}],
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
