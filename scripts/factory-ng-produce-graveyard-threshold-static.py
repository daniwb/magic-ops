#!/usr/bin/env python3
"""Emit one bounded Map ticket for proven graveyard-threshold static clauses."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from factory_ng_paths import SOURCE


OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / "docs/factory-ng/tickets"
SKILL = OPS / "docs/factory-ng/skills/v1/implement-map-class/SKILL.md"
TICKET_ID = "ticket:map.static-condition-graveyard-thresholds/v1"
RECOVERY_TICKET_ID = "ticket:map.static-condition-graveyard-thresholds/v2"
PARSER_REL = "scripts/paragraph/reparse.py"
TEST_REL = "scripts/paragraph/test_static_condition_graveyard_thresholds.py"
MEMBERS = (
    ("A-Dragon's Rage Channeler", "as long as there are four or more card types among cards in your graveyard",
     {"kind": "threshold", "zone": "graveyard", "what": "card_types", "amount": 4}),
    ("Dragon's Rage Channeler", "as long as there are four or more card types among cards in your graveyard",
     {"kind": "threshold", "zone": "graveyard", "what": "card_types", "amount": 4}),
    ("Winter, Misanthropic Guide", "as long as there are four or more card types among cards in your graveyard",
     {"kind": "threshold", "zone": "graveyard", "what": "card_types", "amount": 4}),
    ("A-Syndicate Infiltrator", "as long as there are five or more mana values among cards in your graveyard",
     {"kind": "threshold", "zone": "graveyard", "what": "mana_value", "amount": 5}),
    ("Aven Heartstabber", "as long as there are five or more mana values among cards in your graveyard",
     {"kind": "threshold", "zone": "graveyard", "what": "mana_value", "amount": 5}),
    ("Snooping Newsie", "as long as there are five or more mana values among cards in your graveyard",
     {"kind": "threshold", "zone": "graveyard", "what": "mana_value", "amount": 5}),
    ("Syndicate Infiltrator", "as long as there are five or more mana values among cards in your graveyard",
     {"kind": "threshold", "zone": "graveyard", "what": "mana_value", "amount": 5}),
)


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_card(repo, name):
    return json.loads((repo / "backend/data/carddb" / (name[0].lower() + ".json")).read_text())[name]


def known_ticket(ticket_dir, ticket_id):
    for path in ticket_dir.glob("*.json"):
        try:
            if json.loads(path.read_text()).get("id") == ticket_id:
                return path
        except (OSError, ValueError):
            continue
    return None


def transport_recovery_needed(ticket_path):
    """Recognize only the observed pre-fix local-loopback failure.

    This is deliberately narrower than a generic retry: it refunds neither
    model nor gate failures, and can emit one successor only when the original
    Halogen direct adapter returned no bytes at all.
    """
    jobs_path = OPS / "state/factory-ng-jobs.json"
    try:
        job = json.loads(jobs_path.read_text()).get("jobs", {}).get(TICKET_ID, {})
        receipt = OPS / job["receipt"]
        observation = json.loads(receipt.read_text())
        raw = OPS / observation["raw_artifacts"][0]["path"]
    except (KeyError, OSError, ValueError, TypeError):
        return False
    return (job.get("state") == "failed" and job.get("outcome") == "infrastructure_failed" and
            job.get("attempts") == 3 and job.get("dispatch_profile") == "qwen-prepared-direct@1.0.2" and
            job.get("model") == "halogen-qwen3.8-flash-next" and
            observation.get("execution", {}).get("model_exit_code") == 1 and raw.stat().st_size == 0)


def emit(status, ticket_id, **extra):
    print(json.dumps({"schema": "factory.ticket-production/v1", "status": status,
                      "ticket_id": ticket_id, **extra}, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=SOURCE)
    parser.add_argument("--ticket-dir", type=Path, default=TICKETS)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True):
        parser.error("--repo must be a clean ground-truth checkout")
    original = known_ticket(args.ticket_dir, TICKET_ID)
    recovery = known_ticket(args.ticket_dir, RECOVERY_TICKET_ID)
    if recovery:
        emit("duplicate_ticket", RECOVERY_TICKET_ID, ticket_path=str(recovery))
        return
    if original and not transport_recovery_needed(original):
        emit("duplicate_ticket", TICKET_ID, ticket_path=str(original))
        return
    ticket_id = RECOVERY_TICKET_ID if original else TICKET_ID

    runtime = repo / "backend/game/condition.go"
    required_runtime = ('case "threshold":', 'c.What == "card_types"', 'c.What == "mana_value"')
    if not all(marker in runtime.read_text() for marker in required_runtime):
        emit("needs_primitive", ticket_id, reason="runtime lacks a proven graveyard threshold condition")
        return

    parser_path = repo / PARSER_REL
    sys.path.insert(0, str(parser_path.parent))
    import reparse
    rows = []
    for name, phrase, condition in MEMBERS:
        card = load_card(repo, name)
        if phrase not in card.get("text", "").lower():
            emit("ground_truth_changed", ticket_id, card=name)
            return
        misses = reparse.reparse_card(card).get("misses", [])
        if len(misses) != 1 or misses[0][0] != "static_conditional":
            emit("ground_truth_changed", ticket_id, card=name, misses=misses)
            return
        rows.append({"name": name, "text_sha256": "sha256:" + hashlib.sha256(card["text"].encode()).hexdigest(),
                     "all_miss_shapes": ["static_conditional"], "details": [phrase], "condition": condition})

    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    measurement_path = ("docs/factory-ng/measurements/static-condition-graveyard-thresholds-v2.json"
                        if original else
                        "docs/factory-ng/measurements/static-condition-graveyard-thresholds-v1.json")
    measurement = {"schema": "factory.targeted-demand/v1", "shape": "static_conditional",
                   "member_count": len(rows), "review_cards_scanned": len(rows), "members": rows,
                   "source": {"repository": str(repo), "revision": revision, "parser_sha256": digest(parser_path)}}
    ticket = {
        "schema": "factory.ticket-spec/v1", "id": ticket_id,
        "title": "Map exact graveyard card-type and mana-value threshold static conditions",
        "work_type": "map", "lifecycle": "ready_for_observation",
        "parents": ["ticket:factory.evidence.static-conditional/v1"],
        "production": {"producer": "graveyard-threshold-static", "key": "static-condition-graveyard-thresholds:v1",
                       "predicted_class_unlock": len(rows)},
        "source": {"repository": str(repo), "revision": revision, "clean": True},
        "skill": {"name": "implement-map-class", "path": str(SKILL.relative_to(OPS)), "sha256": digest(SKILL)},
        "scope": {"allowed_paths": [PARSER_REL, TEST_REL],
                  "forbidden_paths": ["backend/", "backend/data/", "scripts/paragraph/slotparse_oneshot.py"]},
        "evidence": [
            {"path": measurement_path, "fact": "Seven pinned sole static_conditional misses use exactly two graveyard threshold clauses."},
            {"path": "backend/game/condition.go", "sha256": digest(runtime), "anchor": "358-375",
             "fact": "The existing threshold condition evaluates distinct graveyard card types and graveyard mana-value totals."},
            {"path": PARSER_REL, "sha256": digest(parser_path), "anchor": "10652-10941",
             "fact": "parse_static_condition is the bounded Map seam; no Engine change is permitted."},
        ],
        "required_behavior": [
            "Map exactly `as long as there are four or more card types among cards in your graveyard` to {kind: threshold, zone: graveyard, what: card_types, amount: 4}.",
            "Map exactly `as long as there are five or more mana values among cards in your graveyard` to {kind: threshold, zone: graveyard, what: mana_value, amount: 5}.",
            "All seven pinned cards must lose their sole static_conditional miss; preserve their existing effects and conditions.",
            "Do not generalize to another zone, threshold, count kind, player, static clause, or use a card-name special case.",
            "Do not edit Engine, converter, corpus data, or the V2 registry.",
        ],
        "gates": [
            "cd scripts/paragraph && python3 -m unittest test_static_condition_graveyard_thresholds",
            "git diff --check",
            "git status --porcelain adds or changes only scripts/paragraph/reparse.py and scripts/paragraph/test_static_condition_graveyard_thresholds.py",
            "python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo . --members-from /opt/development/magic-ops/%s reports zero remaining pinned members" % measurement_path,
        ],
        "execution": {"mode": "isolated_clone_observation_only", "selected_profile": "qwen-prepared-direct@1.0.2",
                      "compatible_profiles": ["qwen-prepared-direct@1.0.2", "claude-staged@1.0.0", "codex-constrained@1.1.0"],
                      "selection_reason": "Seven exact parser-only clauses map to two already-proven runtime condition shapes.",
                      "effective_token_target": 200000, "warning_reflection_threshold": 500000, "automatic_stop": False,
                      "model_may_not_commit_push_deploy_or_mutate_live_tickets": True},
        "on_failure": "Record a receipt. Any missing threshold behavior is a separate Engine TicketSpec; do not partially map a clause.",
    }
    if original:
        ticket["title"] = "Retry exact graveyard threshold static-condition mapping after local adapter transport repair"
        ticket["supersedes"] = TICKET_ID
        ticket["parents"].append(TICKET_ID)
        ticket["production"]["retry_reason"] = "adapter_transport_repair"
        ticket["evidence"].append({
            "path": "scripts/qwen-prepared-call.py",
            "fact": "The v1 Halogen direct attempts failed before any response bytes because localhost selected the rootless forwarder's failing path; the adapter now uses 127.0.0.1.",
        })
    emit("ready", ticket_id, measurement=measurement, ticket=ticket)


if __name__ == "__main__":
    main()
