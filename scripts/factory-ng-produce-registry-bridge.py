#!/usr/bin/env python3
"""Produce one deduplicated Engine TicketSpec for a missing v2 registry bridge.

This intentionally covers one atomic, mechanically provable class only:
an effect already dispatched by backend/game/ability_effects.go but absent from
the v2 card registry mirrored by the parser. Other Engine gaps need their own
producer, rather than a generic script inventing scope or semantics.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / "docs/factory-ng/tickets"
SKILL = OPS / "docs/factory-ng/skills/v1/implement-engine-capability/SKILL.md"


def sha(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision(repo):
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def registered(repo, effect):
    cards = repo / "backend/cards"
    for path in [cards / "registry.go", *sorted(cards.glob("registry_*.go"))]:
        if re.search(r'(?<![A-Za-z0-9_])"%s"\s*:' % re.escape(effect), path.read_text()):
            return True
        if re.search(r'regEffect\("%s"\s*,' % re.escape(effect), path.read_text()):
            return True
    return False


def dispatcher_exists(repo, effect):
    path = repo / "backend/game/ability_effects.go"
    return bool(re.search(r'case\s+"%s"\s*:' % re.escape(effect), path.read_text()))


def known_ticket(ticket_dir, ticket_id):
    for path in ticket_dir.glob("*.json"):
        try:
            if json.loads(path.read_text()).get("id") == ticket_id:
                return str(path)
        except (OSError, ValueError):
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path("/opt/development/test/openmagic"))
    ap.add_argument("--source-repo", type=Path,
                    help="clean base checkout recorded in the TicketSpec when --repo has accepted parent overlays")
    ap.add_argument("--effect", required=True)
    ap.add_argument("--parent", action="append", required=True,
                    help="accepted parent TicketSpec ID; repeatable")
    ap.add_argument("--ticket-dir", type=Path, default=TICKETS,
                    help="directory used only for deterministic deduplication")
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.effect):
        ap.error("--effect must be a lowercase snake_case effect name")
    repo = args.repo.resolve()
    if not (repo / "backend/game/ability_effects.go").is_file():
        ap.error("--repo must contain backend/game/ability_effects.go")
    source_repo = (args.source_repo or repo).resolve()
    if subprocess.check_output(["git", "-C", str(source_repo), "status", "--porcelain"], text=True):
        ap.error("--source-repo must be clean")
    slug = args.effect.replace("_", "-")
    ticket_id = "ticket:engine.%s-registry-bridge/v1" % slug
    if registered(repo, args.effect):
        print(json.dumps({"schema": "factory.ticket-production/v1", "status": "already_registered",
                          "effect": args.effect, "ticket_id": ticket_id}, indent=2, sort_keys=True))
        return
    if not dispatcher_exists(repo, args.effect):
        print(json.dumps({"schema": "factory.ticket-production/v1", "status": "no_existing_dispatcher",
                          "effect": args.effect, "ticket_id": ticket_id}, indent=2, sort_keys=True))
        return
    duplicate = known_ticket(args.ticket_dir, ticket_id)
    if duplicate:
        print(json.dumps({"schema": "factory.ticket-production/v1", "status": "duplicate_ticket",
                          "effect": args.effect, "ticket_id": ticket_id, "ticket_path": duplicate},
                         indent=2, sort_keys=True))
        return
    registry = repo / "backend/cards/registry.go"
    converter = repo / "backend/cards/converter.go"
    parser = repo / "scripts/paragraph/reparse.py"
    result = {
        "schema": "factory.ticket-spec/v1",
        "id": ticket_id,
        "title": "Register the existing %s executor in the v2 vocabulary" % args.effect,
        "work_type": "engine",
        "lifecycle": "ready_for_observation",
        "parents": args.parent,
        "source": {"repository": str(source_repo), "revision": git_revision(source_repo), "clean": True},
        "skill": {"name": "implement-engine-capability", "path": str(SKILL.relative_to(OPS)), "sha256": sha(SKILL)},
        "scope": {
            "allowed_paths": ["backend/cards/registry_%s.go" % args.effect,
                              "backend/cards/shape_%s_test.go" % args.effect],
            "forbidden_paths": ["backend/game/", "backend/cards/registry.go", "backend/cards/converter.go", "scripts/paragraph/"]
        },
        "evidence": [
            {"path": "backend/game/ability_effects.go", "fact": "A dispatch case for %s exists but the registry bridge is absent." % args.effect},
            {"path": "backend/cards/registry.go", "sha256": sha(registry), "anchor": "555-568",
             "fact": "New effects use registry_*.go plus regEffect; the frozen literal is not edited."},
            {"path": "backend/cards/converter.go", "sha256": sha(converter), "anchor": "138-247",
             "fact": "Existing v2 EffectAtom sequences use the shared ability-effect route; no alternate converter route is implied."},
            {"path": "scripts/paragraph/reparse.py", "sha256": sha(parser), "anchor": "85-98",
             "fact": "The parser mirrors the v2 registry and honestly refuses an unregistered effect."}
        ],
        "required_behavior": [
            "Register exactly one %s primitive through the registry_*.go init convention." % args.effect,
            "Prove the registry metadata names the existing dispatcher and a discriminating new shape test.",
            "Do not edit parser, converter, frozen registry literal, or backend/game."
        ],
        "gates": [
            "cd backend && go test ./cards ./game -run 'TestVocabulary|TestShape_%s' -count=1" % "".join(part.title() for part in args.effect.split("_")),
            "cd backend && go build ./...",
            "git diff --check"
        ],
        "execution": {"mode": "isolated_clone_observation_only", "selected_profile": "claude-staged@1.0.0",
                      "effective_token_target": 200000, "warning_reflection_threshold": 500000,
                      "automatic_stop": False, "model_may_not_commit_push_deploy_or_mutate_live_tickets": True}
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
