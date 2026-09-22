#!/usr/bin/env python3
"""Snapshot the capability coverage plan for the live dashboard view.

Reads the canonical ranked coverage plan (openmagic/corpus/build-plan.jsonl)
and the durable job ledger (state/factory-ng-jobs.json), and writes a compact
JSON snapshot to state/factory-ng-coverage.json for the Go dispatcher to
serve at /factory-ng/coverage.json. Ticket-to-shape membership is read from
each ticket's own declared "plan:<shape>" parent reference (the same field
the build-plan producer writes), not a keyword guess.

Cheap (well under a second for the current corpus size); intended to be
re-run on a short interval by factory-ng-viz-snapshot.py.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / "docs/factory-ng/tickets"
JOBS = OPS / "state/factory-ng-jobs.json"
OUT = OPS / "state/factory-ng-coverage.json"
PLAN = Path(os.environ.get("OPENMAGIC_BUILD_PLAN", "/opt/development/test/openmagic/corpus/build-plan.jsonl"))


def load_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-" + path.name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def build():
    if not PLAN.is_file():
        return {"generated_at": None, "error": "coverage plan not found: %s" % PLAN, "shapes": []}
    plan_rows = [json.loads(line) for line in PLAN.read_text().splitlines() if line.strip()]
    jobs = (load_json(JOBS, {}) or {}).get("jobs", {})

    tickets = {}
    for path in TICKETS.glob("*.json"):
        ticket = load_json(path)
        if not ticket or not ticket.get("id"):
            continue
        tickets[ticket["id"]] = ticket

    shape_members = {row["item"]: [] for row in plan_rows}
    for tid, ticket in tickets.items():
        for parent in ticket.get("parents") or []:
            if isinstance(parent, str) and parent.startswith("plan:"):
                item = parent[len("plan:"):]
                if item in shape_members:
                    shape_members[item].append(tid)

    shapes = []
    for row in plan_rows:
        item = row["item"]
        members = shape_members.get(item, [])
        states = {}
        for tid in members:
            state = (jobs.get(tid) or {}).get("state")
            states[state] = states.get(state, 0) + 1
        zone = "idle" if not members else ("producing" if states.get("completed") else "active")
        shapes.append({
            "item": item,
            "rank": row.get("rank"),
            "unlock": row.get("marginal_unlock", 0) or 0,
            "examples": len(row.get("examples") or []),
            "matched": len(members),
            "states": states,
            "zone": zone,
            "samples": sorted(members)[:6],
        })
    shapes.sort(key=lambda s: -(s["unlock"] or 0))

    return {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                         .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_tickets": len(tickets),
        "shapes": shapes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    atomic_write(args.out, build())


if __name__ == "__main__":
    main()
