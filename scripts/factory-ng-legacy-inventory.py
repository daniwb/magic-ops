#!/usr/bin/env python3
"""Read-only Factory NG classification of the legacy dispatcher backlog."""
import argparse
import collections
import hashlib
import json
import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "services" / "dispatcher" / "v4" / "dispatcher.db"
TERMINAL = {"archived-v1", "done", "parked-era1", "superseded"}


def sha256(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def classify(ticket, cap_states, now):
    state = ticket["state"]
    if state == "dup":
        return "duplicate", "legacy dispatcher marked duplicate"
    if state in TERMINAL:
        return "terminal", "legacy terminal state: " + state
    if state == "blocked" or ticket["missing_prim"] or "open" in cap_states:
        why = ticket["missing_prim"] or "linked open capability"
        return "blocked_by_capability", why
    if state == "wait":
        return "legacy_unverified", "legacy wait requires fresh corpus/code evidence"
    if state == "fable":
        return "mixed_or_ambiguous", "legacy class-round assignment needs TicketSpec split"
    if ticket["descr"].count('template family') > 1 or "REPARSE-SWEEP: 2 small shapes" in ticket["title"] or "REPARSE-SWEEP: 5 small shapes" in ticket["title"]:
        return "mixed_or_ambiguous", "legacy ticket combines several independently testable shape families"
    if state == "todo":
        if now - ticket["updated_at"] > 7 * 24 * 3600:
            return "stale", "unchanged todo for more than seven days; recompile from ground truth"
        return "ready", "legacy todo has no recorded capability block; validate before dispatch"
    return "legacy_unverified", "unrecognized legacy state: " + state


def inventory(db_path):
    db = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    db.row_factory = sqlite3.Row
    capabilities = collections.defaultdict(list)
    for row in db.execute("""select tc.ticket_id, c.state from ticket_capabilities tc
                             join capabilities c on c.id=tc.capability_id"""):
        capabilities[row["ticket_id"]].append(row["state"])
    now = int(time.time())
    rows = []
    for ticket in db.execute("""select id,title,type,state,worker_id,lease_exp,retry_count,
                                      missing_prim,vocab_id,parent_id,updated_at,descr
                               from tickets order by id"""):
        item = dict(ticket)
        category, reason = classify(item, capabilities[item["id"]], now)
        rows.append({"legacy_id": item["id"], "title": item["title"], "type": item["type"],
                     "legacy_state": item["state"], "classification": category,
                     "reason": reason, "linked_capability_states": capabilities[item["id"]],
                     "retry_count": item["retry_count"], "updated_at": item["updated_at"]})
    counts = collections.Counter(row["classification"] for row in rows)
    attempts = dict(db.execute("select outcome,count(*) from attempts group by outcome"))
    cap_counts = dict(db.execute("select state,count(*) from capabilities group by state"))
    return {"schema": "factory.legacy-inventory/v1", "database": str(db_path),
            "database_sha256": sha256(db_path), "generated_at": now,
            "totals": {"tickets": len(rows), "classifications": dict(sorted(counts.items())),
                       "capabilities": cap_counts, "attempts": attempts}, "tickets": rows}


def markdown(report):
    lines = ["# Factory NG legacy backlog reconciliation", "",
             "Read-only classification; it does not alter dispatcher state.", "",
             "- Database: `%s`" % report["database"],
             "- Snapshot: `%s`" % report["database_sha256"],
             "- Tickets reconciled: %d" % report["totals"]["tickets"], "",
             "## Exact classification totals", "",
             "| Classification | Tickets |", "|---|---:|"]
    for key, value in report["totals"]["classifications"].items():
        lines.append("| %s | %d |" % (key, value))
    lines += ["", "## Candidates requiring fresh TicketSpec compilation", "",
              "| Legacy ID | Classification | Title | Reason |", "|---:|---|---|---|"]
    candidates = [row for row in report["tickets"] if row["classification"] in {"ready", "stale", "mixed_or_ambiguous"}]
    for row in candidates:
        lines.append("| %d | %s | %s | %s |" % (row["legacy_id"], row["classification"], row["title"].replace("|", "/"), row["reason"]))
    lines += ["", "No legacy row is directly dispatched by this report. `ready` means only that no block is recorded; a Factory NG producer must refresh evidence, split mixed scopes, and deduplicate before a TicketSpec reaches a worker."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    report = inventory(args.db.resolve())
    print(json.dumps(report, indent=2, sort_keys=True) if args.format == "json" else markdown(report), end="")


if __name__ == "__main__":
    main()
