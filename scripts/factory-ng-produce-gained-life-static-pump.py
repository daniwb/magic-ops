#!/usr/bin/env python3
"""Produce the one atomic static-condition Map ticket used for Factory NG rollout.

This is deliberately not a generic static-condition classifier.  It accepts
only the two current Oracle-equal cards whose parser gap is the exact phrase
"you gained life this turn" and whose runtime condition already exists.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / "docs/factory-ng/tickets"
SKILL = OPS / "docs/factory-ng/skills/v1/implement-map-class/SKILL.md"
PARENT = "ticket:factory.evidence.static-conditional/v1"
TICKET_ID = "ticket:map.static-condition-gained-life-pump/v1"
PHRASE = "This creature gets +2/+0 as long as you gained life this turn."
MEMBERS = ("Tenured Concocter", "Ulna Alley Shopkeep")


def sha(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def revision(repo):
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def card(repo, name):
    shard = repo / "backend/data/carddb" / (name[0].lower() + ".json")
    return json.loads(shard.read_text())[name]


def known_ticket(ticket_dir):
    for path in ticket_dir.glob("*.json"):
        try:
            if json.loads(path.read_text()).get("id") == TICKET_ID:
                return str(path)
        except (OSError, ValueError):
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path("/opt/development/test/openmagic"))
    ap.add_argument("--ticket-dir", type=Path, default=TICKETS)
    args = ap.parse_args()
    repo = args.repo.resolve()
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True):
        ap.error("--repo must be a clean ground-truth checkout")
    parser = repo / "scripts/paragraph/reparse.py"
    runtime = repo / "backend/game/condition.go"
    if 'case "you_gained_life":' not in runtime.read_text():
        print(json.dumps({"schema": "factory.ticket-production/v1", "status": "needs_primitive",
                          "ticket_id": TICKET_ID,
                          "reason": "runtime does not expose happened/you_gained_life"}, indent=2))
        return
    rows = []
    for name in MEMBERS:
        value = card(repo, name)
        if PHRASE not in value.get("text", ""):
            print(json.dumps({"schema": "factory.ticket-production/v1", "status": "ground_truth_changed",
                              "ticket_id": TICKET_ID, "card": name}, indent=2))
            return
        rows.append({"name": name, "text_sha256": "sha256:" + hashlib.sha256(value["text"].encode()).hexdigest(),
                     "all_miss_shapes": ["static_conditional"], "details": [PHRASE.lower()]})
    duplicate = known_ticket(args.ticket_dir)
    if duplicate:
        print(json.dumps({"schema": "factory.ticket-production/v1", "status": "duplicate_ticket",
                          "ticket_id": TICKET_ID, "ticket_path": duplicate}, indent=2))
        return
    measurement = {
        "schema": "factory.targeted-demand/v1", "shape": "static_conditional",
        "member_count": len(rows), "members": rows, "review_cards_scanned": len(rows),
        "source": {"repository": str(repo), "revision": revision(repo), "parser_sha256": sha(parser)},
    }
    ticket = {
        "schema": "factory.ticket-spec/v1", "id": TICKET_ID,
        "title": "Map the exact gained-life-this-turn static pump condition",
        "work_type": "map", "lifecycle": "ready_for_observation", "parents": [PARENT],
        "source": {"repository": str(repo), "revision": revision(repo), "clean": True},
        "skill": {"name": "implement-map-class", "path": str(SKILL.relative_to(OPS)), "sha256": sha(SKILL)},
        "scope": {"allowed_paths": ["scripts/paragraph/reparse.py", "scripts/paragraph/test_static_condition_gained_life.py"],
                  "forbidden_paths": ["backend/", "backend/data/", "scripts/paragraph/slotparse_oneshot.py"]},
        "evidence": [
            {"path": "docs/factory-ng/measurements/static-condition-gained-life-pump-v1.json",
             "fact": "Exactly two pinned, sole static_conditional misses share the same Oracle sentence."},
            {"path": "backend/game/condition.go", "sha256": sha(runtime), "anchor": "494-511",
             "fact": "The existing happened/you_gained_life condition reads LifeGainedThisTurn; this ticket requires no Engine behavior."},
            {"path": "scripts/paragraph/reparse.py", "sha256": sha(parser), "anchor": "10652-10931",
             "fact": "parse_static_condition is the narrow Map seam; it already attaches a parsed condition to a static pump."},
        ],
        "required_behavior": [
            "Map exactly `you gained life this turn` to {kind: happened, what: you_gained_life}.",
            "The two pinned +2/+0 self-pump cards parse with that condition and no static_conditional miss.",
            "Do not generalize to other life-gain wording, other actors, quantities, or other static effects.",
            "Do not edit Engine, converter, corpus data, or use card-name special cases."
        ],
        "gates": [
            "cd scripts/paragraph && python3 -m unittest test_static_condition_gained_life",
            "git diff --check",
            "git status --porcelain adds or changes only scripts/paragraph/reparse.py and scripts/paragraph/test_static_condition_gained_life.py",
            "python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo . --members-from /opt/development/magic-ops/docs/factory-ng/measurements/static-condition-gained-life-pump-v1.json reports zero remaining pinned members"
        ],
        "execution": {"mode": "isolated_clone_observation_only", "selected_profile": "qwen-prepared-direct@1.0.2",
                      "selection_reason": "A two-card, one-sentence parser-only change with a proven runtime representation is the validated local Qwen direct Map profile.",
                      "effective_token_target": 200000, "warning_reflection_threshold": 500000, "automatic_stop": False,
                      "model_may_not_commit_push_deploy_or_mutate_live_tickets": True},
        "on_failure": "Record a receipt. A need to change the runtime condition vocabulary is a separate Engine TicketSpec."
    }
    print(json.dumps({"schema": "factory.ticket-production/v1", "status": "ready", "measurement": measurement,
                      "ticket": ticket}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
