#!/usr/bin/env python3
"""Read-only summary of Factory NG's blocked/parked backlog.

For each stuck job, resolves its *actual* capability demand and current
Engine-chain state the same way `factory-ng-produce-capability-dependency.py`
does -- not a guessed verb-prefix match. An earlier version of this script
grouped blocked Map tickets by their coarse build-plan verb category (e.g.
"grant_eot") and guessed at a link to Engine capability keys by substring
containment. That produced false negatives whenever a card's actual demand
didn't share the verb's literal text -- e.g. "grant_eot"-tagged tickets that
actually demand "grant_haste_to_mana_paid_dragon_spell", or "regrow"-tagged
ones that demand "return_from_graveyard_lesser_toughness_filter". This
version reads each Map job's own receipt to get its real capability_demand
and computes the identical engine_identity() the producer uses, so the link
is exact instead of heuristic.

Usage: python3 scripts/factory-ng-stale-report.py [--min-age-hours 24]
"""
import argparse
import importlib.util
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
JOBS = OPS / "state/factory-ng-jobs.json"
TICKETS = OPS / "docs/factory-ng/tickets"
BACKLOG_STATES = ("blocked", "parked", "failed")


def load_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def load_producer():
    spec = importlib.util.spec_from_file_location(
        "factory_ng_stale_report_producer", OPS / "scripts/factory-ng-produce-capability-dependency.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_ticket_index():
    tickets_by_id = {}
    versions_by_base = {}
    successors_by_parent = {}
    for path in TICKETS.glob("*.json"):
        item = load_json(path, {}) or {}
        ticket_id = item.get("id")
        if not ticket_id:
            continue
        tickets_by_id[ticket_id] = item
        found = re.fullmatch(r"(ticket:[a-z0-9][a-z0-9._-]*)/v(\d+)", ticket_id)
        if found:
            versions_by_base.setdefault(found.group(1), []).append(item)
        if item.get("supersedes"):
            successors_by_parent.setdefault(item["supersedes"], []).append(item)
    for chain in versions_by_base.values():
        chain.sort(key=lambda item: int(item["id"].rsplit("/v", 1)[1]))
    return tickets_by_id, versions_by_base, successors_by_parent


def age_hours(job, now):
    ts = job.get("updated_at") or job.get("finished_at") or job.get("created_at")
    if not ts:
        return None
    try:
        return (now - time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))) / 3600.0
    except ValueError:
        return None


def capability_from_receipt(job, producer):
    """A Map job's own receipt carries the real capability_demand it hit."""
    receipt_path = job.get("receipt") or job.get("processed_receipt")
    if not receipt_path:
        return None
    receipt = load_json(OPS / receipt_path, {}) or {}
    capability = receipt.get("capability_demand")
    if receipt.get("outcome") == "invalid_capability_demand":
        capability = producer.recover_valid_capability(receipt)
    return capability if isinstance(capability, dict) and capability.get("key") else None


def capability_key_from_production(job):
    """An Engine job's own production.key already names its real capability."""
    key = job.get("production", {}).get("key", "")
    parts = key.split(":")
    return parts[1] if len(parts) >= 2 and parts[0] == "capability" else None


def engine_chain_state(capability, producer, versions_by_base, jobs):
    engine_id, _ = producer.engine_identity(capability)
    base = engine_id.rsplit("/v", 1)[0]
    chain = versions_by_base.get(base)
    if not chain:
        return "not_started"
    return jobs.get(chain[-1]["id"], {}).get("state", "unknown")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-age-hours", type=float, default=24.0,
                         help="only flag a stale-with-no-active-work group past this age")
    args = parser.parse_args()

    jobs = (load_json(JOBS, {}) or {}).get("jobs", {})
    now = time.time()
    producer = load_producer()
    _tickets_by_id, versions_by_base, successors_by_parent = build_ticket_index()

    active_states = {"queued", "working", "integrating", "awaiting_integration"}

    for state in BACKLOG_STATES:
        by_bucket = defaultdict(list)  # bucket -> [(capability_key, age)]
        unresolved = 0
        for job in jobs.values():
            if job.get("state") != state:
                continue
            is_map = str(job.get("ticket_id", "")).startswith("ticket:map.")
            if is_map:
                # A "blocked" job's own state field is never rewritten once a
                # successor ticket resumes it, so a job showing "blocked" here
                # can already be superseded bookkeeping rather than something
                # still genuinely stuck.
                if successors_by_parent.get(job.get("ticket_id")):
                    by_bucket["already_superseded"].append((None, age_hours(job, now)))
                    continue
                capability = capability_from_receipt(job, producer)
                if not capability:
                    unresolved += 1
                    continue
                bucket = engine_chain_state(capability, producer, versions_by_base, jobs)
                key = capability["key"]
            else:
                key = capability_key_from_production(job)
                if not key:
                    unresolved += 1
                    continue
                bucket = "own_capability(%s)" % state
            by_bucket[bucket].append((key, age_hours(job, now)))
        total = sum(len(v) for v in by_bucket.values()) + unresolved
        if not total:
            continue
        print("=== %s (%d total, %d unresolved receipt) ===" % (state, total, unresolved))
        for bucket, entries in sorted(by_bucket.items(), key=lambda kv: -len(kv[1])):
            ages = [a for _, a in entries if a is not None]
            oldest = max(ages) if ages else None
            in_progress = bucket in active_states
            informational = bucket == "already_superseded"
            stale = (not in_progress and not informational and bucket != "completed" and
                     oldest is not None and oldest >= args.min_age_hours)
            marker = ("!! STALE" if stale else
                      "in progress" if in_progress else
                      "READY TO RESUME (free win)" if bucket == "completed" else
                      "stale bookkeeping, already resumed by a newer ticket" if informational else bucket)
            age_str = ("%.0fh" % oldest) if oldest is not None else "?"
            print("  %-22s n=%-4d oldest=%-6s %s" % (bucket, len(entries), age_str, marker))
            sample = Counter(k for k, _ in entries if k is not None).most_common(3)
            for key, count in sample:
                print("      e.g. %s (x%d)" % (key, count))
        print()


if __name__ == "__main__":
    main()
