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
PLAN = Path(os.environ["OPENMAGIC_BUILD_PLAN"]) if os.environ.get("OPENMAGIC_BUILD_PLAN") else None


def configured_plan():
    if PLAN is not None:
        return PLAN
    config = load_json(OPS / 'config/factory-ng-producers.json', {}) or {}
    for producer in config.get('producers', []):
        command = producer.get('command', [])
        if (producer.get('enabled') and 'scripts/factory-ng-produce-build-plan.py' in command
                and '--plan' in command and '--lane' in command
                and command[command.index('--lane') + 1] == 'fresh'):
            path = Path(command[command.index('--plan') + 1])
            return path if path.is_absolute() else OPS / path
    return Path('/opt/development/test/openmagic/corpus/build-plan.jsonl')


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
    plan = configured_plan()
    if not plan.is_file():
        return {"generated_at": None, "error": "coverage plan not found: %s" % PLAN, "shapes": []}
    plan_rows = [json.loads(line) for line in plan.read_text().splitlines() if line.strip()]
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
        "plan_path": str(plan),
        "source_revision": next((r.get('source_revision') for r in plan_rows if r.get('source_revision')), None),
        "measured_at": next((r.get('measured_at') for r in plan_rows if r.get('measured_at')), None),
        "measurement_note": "Measured one-miss candidates, not runnable tickets or guaranteed enabled cards. Ticket zones describe all-time history.",
        "shapes": shapes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    atomic_write(args.out, build())


if __name__ == "__main__":
    main()
