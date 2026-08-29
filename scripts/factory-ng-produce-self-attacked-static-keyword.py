#!/usr/bin/env python3
"""Produce the bounded Map ticket for the self-attacked static keyword gap.

The runtime already represents this exact turn-history condition.  This
producer deliberately pins the one current Oracle sentence instead of turning
the broad ``static_conditional`` or ``happened`` labels into a work queue.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / "docs/factory-ng/tickets"
SKILL = OPS / "docs/factory-ng/skills/v1/implement-map-class/SKILL.md"
PARENT = "ticket:factory.evidence.static-conditional/v1"
TICKET_ID = "ticket:map.static-condition-self-attacked-keyword/v1"
CARD_NAME = "Agent Frank Horrigan"
ORACLE_SENTENCE = "Agent Frank Horrigan has indestructible as long as it attacked this turn."
NORMALIZED_SENTENCE = "~ has indestructible as long as it attacked this turn"


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


def emit(status, **extra):
    print(json.dumps({"schema": "factory.ticket-production/v1", "status": status,
                      "ticket_id": TICKET_ID, **extra}, indent=2, sort_keys=True))


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
    if 'case "self_attacked_this_turn":' not in runtime.read_text():
        emit("needs_primitive", reason="runtime does not expose happened/self_attacked_this_turn")
        return
    value = card(repo, CARD_NAME)
    if ORACLE_SENTENCE not in value.get("text", ""):
        emit("ground_truth_changed", card=CARD_NAME)
        return
    duplicate = known_ticket(args.ticket_dir)
    if duplicate:
        emit("duplicate_ticket", ticket_path=duplicate)
        return
    text_hash = "sha256:" + hashlib.sha256(value["text"].encode()).hexdigest()
    measurement = {
        "schema": "factory.targeted-demand/v1", "shape": "static_conditional",
        "member_count": 1, "review_cards_scanned": 1,
        "members": [{"name": CARD_NAME, "text_sha256": text_hash,
                     "all_miss_shapes": ["static_conditional"],
                     "details": [NORMALIZED_SENTENCE]}],
        "source": {"repository": str(repo), "revision": revision(repo), "parser_sha256": sha(parser)},
    }
    ticket = {
        "schema": "factory.ticket-spec/v1", "id": TICKET_ID,
        "title": "Map the exact self-attacked-this-turn static keyword condition",
        "work_type": "map", "lifecycle": "ready_for_observation", "parents": [PARENT],
        "source": {"repository": str(repo), "revision": revision(repo), "clean": True},
        "skill": {"name": "implement-map-class", "path": str(SKILL.relative_to(OPS)), "sha256": sha(SKILL)},
        "scope": {"allowed_paths": ["scripts/paragraph/reparse.py", "scripts/paragraph/test_static_condition_self_attacked.py"],
                  "forbidden_paths": ["backend/", "backend/data/", "scripts/paragraph/slotparse_oneshot.py"]},
        "evidence": [
            {"path": "docs/factory-ng/measurements/static-condition-self-attacked-keyword-v1.json",
             "fact": "One pinned, sole static_conditional miss has the exact normalized self-attacked keyword sentence."},
            {"path": "backend/game/condition.go", "sha256": sha(runtime), "anchor": "483-540",
             "fact": "The existing happened/self_attacked_this_turn condition reads the source card's turn-scoped attack mark; this ticket requires no Engine behavior."},
            {"path": "scripts/paragraph/reparse.py", "sha256": sha(parser), "anchor": "10652-10941",
             "fact": "parse_static_condition is the narrow Map seam for this continuous keyword gate."},
        ],
        "required_behavior": [
            "Map exactly `it attacked this turn` to {kind: happened, what: self_attacked_this_turn} in parse_static_condition.",
            "The pinned Agent Frank Horrigan static indestructible sentence parses with that condition and no static_conditional miss.",
            "Do not generalize player-level `you attacked this turn`, other event wording, or other static effects.",
            "Do not edit Engine, converter, corpus data, or use card-name special cases."
        ],
        "gates": [
            "cd scripts/paragraph && python3 -m unittest test_static_condition_self_attacked",
            "git diff --check",
            "git status --porcelain adds or changes only scripts/paragraph/reparse.py and scripts/paragraph/test_static_condition_self_attacked.py",
            "python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo . --members-from /opt/development/magic-ops/docs/factory-ng/measurements/static-condition-self-attacked-keyword-v1.json reports zero remaining pinned members"
        ],
        "execution": {"mode": "isolated_clone_observation_only", "selected_profile": "qwen-prepared-direct@1.0.2",
                      "selection_reason": "A single parser tuple with a proven runtime representation is the validated local Qwen direct Map profile.",
                      "parser_probes": [
                          {"function": "parse_static_condition", "text": "it attacked this turn"},
                          {"function": "parse_static_condition", "text": "you attacked this turn"},
                          {"function": "parse_static_condition", "text": "it attacked last turn"}],
                      "effective_token_target": 200000, "warning_reflection_threshold": 500000, "automatic_stop": False,
                      "model_may_not_commit_push_deploy_or_mutate_live_tickets": True},
        "on_failure": "Record a receipt. A need to alter turn-history state is a separate Engine TicketSpec."
    }
    emit("ready", measurement=measurement, ticket=ticket)


if __name__ == "__main__":
    main()
