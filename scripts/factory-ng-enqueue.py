#!/usr/bin/env python3
"""Validate and atomically enqueue one explicit Factory NG TicketSpec."""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / "docs/factory-ng/tickets"
WORKERS = OPS / "config/factory-ng-workers.json"


def fail(message):
    print(json.dumps({"status": "rejected", "reason": message}, sort_keys=True))
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", type=Path, help="TicketSpec JSON (default: stdin)")
    args = parser.parse_args()
    try:
        value = json.loads(args.ticket.read_text() if args.ticket else sys.stdin.read())
    except (OSError, json.JSONDecodeError) as exc:
        return fail("invalid JSON: %s" % exc)
    required = ("id", "title", "work_type", "lifecycle", "source", "skill",
                "scope", "evidence", "required_behavior", "gates", "execution")
    if value.get("schema") != "factory.ticket-spec/v1" or any(key not in value for key in required):
        return fail("not a complete factory.ticket-spec/v1")
    ticket_id = value["id"]
    if not isinstance(ticket_id, str) or not re.fullmatch(r"ticket:[a-z0-9][a-z0-9._-]*/v[1-9][0-9]*", ticket_id):
        return fail("ticket id must be a versioned ticket:<slug>/vN identifier")
    if value["lifecycle"] != "ready_for_observation" or value["work_type"] not in ("map", "engine"):
        return fail("ticket must be ready_for_observation Map or Engine work")
    profile = value.get("execution", {}).get("selected_profile")
    known = set()
    for item in json.loads(WORKERS.read_text()).get("workers", []):
        known.add(item.get("profile"))
        known.update(item.get("alternate_profiles") or [])
    if profile not in known:
        return fail("selected_profile is not configured in Factory NG")
    allowed = value.get("scope", {}).get("allowed_paths")
    gates = value.get("gates")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(item, str) and item for item in allowed):
        return fail("scope.allowed_paths must be a non-empty string list")
    if not isinstance(gates, list) or not gates or not all(isinstance(item, str) and item for item in gates):
        return fail("gates must be a non-empty command list")
    revision = value.get("source", {}).get("revision", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        return fail("source.revision must be a full Git SHA")
    skill = value.get("skill", {})
    skill_path = OPS / skill.get("path", "")
    if not skill_path.is_file():
        return fail("bound skill path does not exist")
    actual = "sha256:" + hashlib.sha256(skill_path.read_bytes()).hexdigest()
    if skill.get("sha256") != actual:
        return fail("bound skill digest does not match")
    for existing in TICKETS.glob("*.json"):
        try:
            if json.loads(existing.read_text()).get("id") == ticket_id:
                return fail("duplicate ticket id already exists at %s" % existing.relative_to(OPS))
        except (OSError, json.JSONDecodeError):
            continue
    stem = ticket_id.removeprefix("ticket:").replace("/", "-").replace(".", "-")
    destination = TICKETS / (stem + ".json")
    TICKETS.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, destination)
    print(json.dumps({"status": "queued", "ticket_id": ticket_id,
                      "ticket_path": str(destination.relative_to(OPS)), "profile": profile}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
