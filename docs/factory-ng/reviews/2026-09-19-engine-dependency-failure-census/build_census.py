#!/usr/bin/env python3
"""Regenerate the engine-dependency failure census artifacts.

Reads live controller state and observation receipts, emits machine-readable
lists so a follow-up worker can pick up individual tickets without re-deriving
the grouping. Read-only over state; writes only into this review directory.

Usage:  python3 docs/factory-ng/reviews/2026-09-19-engine-dependency-failure-census/build_census.py
"""
import json
import re
import collections
from pathlib import Path

OPS = Path(__file__).resolve().parents[4]
JOBS = OPS / "state/factory-ng-jobs.json"
OUT = Path(__file__).resolve().parent

# Repair-lane rule as implemented in scripts/factory-ng-produce-build-plan.py
# candidate_retry(): a gate_failed repair is admitted only for this profile.
REPAIR_ALLOWED_PROFILE = "qwen-prepared-direct@1.0.2"

SEAM_RE = re.compile(r"backend/[a-z_/]+\.go")
SCOPE_RE = re.compile(r"allowed_paths|outside allowed|excluded from allowed|not in allowed", re.I)
EVID_RE = re.compile(r"insufficient|unresolved|missing evidence|no evidence", re.I)
NO_VERDICT = "no edit blocks and no verdict found in model output"


def load(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def receipt_of(job):
    for field in ("receipt", "processed_receipt"):
        p = job.get(field)
        if p:
            r = load(OPS / p) if not Path(p).is_absolute() else load(Path(p))
            if r:
                return r
    return None


def gate_details(receipt):
    return [(g.get("id"), g.get("outcome"), g.get("detail") or "")
            for g in (receipt.get("gates") or [])
            if g.get("outcome") not in ("passed", None)]


def main():
    jobs = json.loads(JOBS.read_text())["jobs"]

    # blocked Map jobs -> their terminal engine parents (observed 1:1)
    parents = collections.defaultdict(list)
    for job in jobs.values():
        if job.get("state") != "blocked":
            continue
        for child, child_state in (job.get("dependency_blocker") or {}).get("children", {}).items():
            parents[child].append(job.get("ticket_id"))

    rows = []
    for parent_id, children in sorted(parents.items()):
        job = jobs.get(parent_id)
        if not job:
            rows.append({"engine_ticket": parent_id, "state": "MISSING",
                        "blocked_map_jobs": children})
            continue
        receipt = receipt_of(job)
        failed_gates = gate_details(receipt) if receipt else []
        blob = json.dumps(receipt) if receipt else ""
        details = " ".join(d for _, _, d in failed_gates)

        seams = sorted(set(SEAM_RE.findall(details)))
        row = {
            "engine_ticket": parent_id,
            "engine_ticket_path": job.get("ticket_path"),
            "state": job.get("state"),
            "outcome": job.get("outcome"),
            "profile": job.get("dispatch_profile", job.get("profile")),
            "attempts": job.get("attempts"),
            "retry_generation": (job.get("production") or {}).get("retry_generation"),
            "updated_at": job.get("updated_at"),
            "receipt": job.get("receipt"),
            "failure_category": (receipt or {}).get("failure_category"),
            "failed_gates": sorted({gid for gid, _, _ in failed_gates}),
            "blocked_map_jobs": children,
            "named_seam_files": seams,
            "scope_excluded_signal": bool(SCOPE_RE.search(blob)),
            "evidence_insufficient_signal": bool(EVID_RE.search(blob)),
            "explicit_ambiguous_verdict": "AMBIGUOUS" in details,
            "no_verdict_in_output": NO_VERDICT in blob,
            "repair_lane_eligible": (
                job.get("outcome") == "gate_failed"
                and row_profile(job) == REPAIR_ALLOWED_PROFILE
            ),
        }
        rows.append(row)

    out_jsonl = OUT / "engine-dependency-census.jsonl"
    with out_jsonl.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    # summary
    by_state = collections.Counter(r["state"] for r in rows)
    by_outcome = collections.Counter((r["state"], r["outcome"]) for r in rows)
    seam_counts = collections.Counter(f for r in rows for f in r["named_seam_files"])
    eligible = sum(1 for r in rows if r["repair_lane_eligible"])
    gate_failed = [r for r in rows if r["outcome"] == "gate_failed"]

    summary = {
        "generated_from": str(JOBS),
        "blocked_map_jobs_total": sum(len(r["blocked_map_jobs"]) for r in rows),
        "distinct_engine_parents": len(rows),
        "parents_by_state": dict(by_state),
        "parents_by_state_and_outcome": {f"{k[0]}/{k[1]}": v for k, v in by_outcome.most_common()},
        "gate_failed_total": len(gate_failed),
        "gate_failed_profiles": dict(collections.Counter(r["profile"] for r in gate_failed).most_common()),
        "gate_failed_retry_generation": dict(collections.Counter(
            str(r["retry_generation"]) for r in gate_failed)),
        "repair_lane_allowed_profile": REPAIR_ALLOWED_PROFILE,
        "repair_lane_eligible_count": eligible,
        "no_verdict_in_output_count": sum(1 for r in rows if r["no_verdict_in_output"]),
        "explicit_ambiguous_verdict_count": sum(1 for r in rows if r["explicit_ambiguous_verdict"]),
        "scope_excluded_signal_count": sum(1 for r in rows if r["scope_excluded_signal"]),
        "named_seam_files": dict(seam_counts.most_common()),
    }
    (OUT / "census-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    # worklists by action class
    lists = {
        "worklist-scope-excluded-seam.json": [r for r in rows if r["scope_excluded_signal"]],
        "worklist-no-verdict.json": [r for r in rows if r["no_verdict_in_output"]],
        "worklist-evidence-insufficient.json": [
            r for r in rows if r["evidence_insufficient_signal"] and not r["scope_excluded_signal"]],
        "worklist-parked-ambiguous.json": [
            r for r in rows if r["state"] == "parked" and r["explicit_ambiguous_verdict"]],
    }
    for name, items in lists.items():
        (OUT / name).write_text(json.dumps(items, indent=2, sort_keys=True) + "\n")

    print(json.dumps(summary, indent=2, sort_keys=True))


def row_profile(job):
    return job.get("dispatch_profile", job.get("profile"))


if __name__ == "__main__":
    main()
