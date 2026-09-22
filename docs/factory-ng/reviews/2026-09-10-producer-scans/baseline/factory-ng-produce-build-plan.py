#!/usr/bin/env python3
"""Continuously compile the next safe build-plan item into a Map TicketSpec.

Unlike the rollout's fixed one-shot producers, this producer has no fixed
ticket id.  It walks the current deterministic coverage plan, revalidates the
example against the canonical source, proves that the target effect has a
registered executor and shape test, and emits the first unaccounted bounded
member.  Repeated calls therefore advance through ground-truth work instead
of stopping because an older TicketSpec file exists.

This producer is deliberately conservative.  It handles only concrete
``verb_unmapped:<verb>`` rows whose target effect is already registered.  A
worker must return a structured NEEDS_PRIMITIVE verdict when the exact
argument/recipient shape needs additional Engine behavior; the controller can
then compile that atomic dependency separately.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from factory_ng_safety import source_problem
from factory_ng_recovery import map_repair_history, MAP_REPAIR_LIMIT


OPS = Path(__file__).resolve().parents[1]
SOURCE = Path("/opt/development/test/openmagic")
TICKETS = OPS / "docs/factory-ng/tickets"
JOBS = OPS / "state/factory-ng-jobs.json"
SKILL = OPS / "docs/factory-ng/skills/v1/implement-map-class/SKILL.md"

# Coverage-plan labels are parser categories, while the registry contains the
# typed effect names.  Keep this map explicit: a fuzzy name match is not proof
# that the runtime behavior exists.
VERB_EFFECT = {
    "damage": "damage",
    "pump": "pump_until_eot",
    "grant_eot": "grant_keywords_until_eot",
    "create_token": "create_token",
    "destroy": "destroy",
    "exile": "exile",
    "put_counters": "put_counters",
    "tap": "tap",
    "bounce": "bounce",
    "search": "search",
    "untap": "untap",
    "reanimate": "return_from_graveyard",
    "regrow": "return_from_graveyard",
    "counter": "counter",
    "copy": "copy",
    "gain_control": "gain_control",
    "sacrifice": "sacrifice",
    "prevent": "prevent_damage_this_turn_scoped",
}

ACTIVE_STATES = {"queued", "working", "awaiting_integration", "integrating"}


def digest_bytes(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_file(path):
    return digest_bytes(path.read_bytes())


def load_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def source_revision(source):
    return subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()


def clean_source(source):
    return not source_problem(source)


def registry_effects(source):
    entries = {}
    registry = source / "backend/cards/registry.go"
    text = registry.read_text()
    for match in re.finditer(
        r'^\s*"([a-z0-9_]+)":\s*\{(?P<body>.*?)^\s*\},', text, re.M | re.S
    ):
        body = match.group("body")
        executor = re.search(r'Executor:\s*"((?:\\.|[^"])*)"', body)
        shape_test = re.search(r'ShapeTest:\s*"((?:\\.|[^"])*)"', body)
        if executor and shape_test:
            entries[match.group(1)] = {
                "path": "backend/cards/registry.go",
                "executor": json.loads('"' + executor.group(1) + '"'),
                "shape_test": json.loads('"' + shape_test.group(1) + '"'),
            }
    for path in (source / "backend/cards").glob("registry_*.go"):
        body = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'regEffect\("([a-z0-9_]+)"\s*,\s*Primitive\s*\{(.*?)\}\)', body, re.S):
            executor = re.search(r'Executor:\s*"((?:\\.|[^"])*)"', match.group(2))
            shape_test = re.search(r'ShapeTest:\s*"((?:\\.|[^"])*)"', match.group(2))
            if executor and shape_test:
                entries[match.group(1)] = {
                    "path": str(path.relative_to(source)),
                    "executor": json.loads('"' + executor.group(1) + '"'),
                    "shape_test": json.loads('"' + shape_test.group(1) + '"'),
                }
    return entries


def card_record(source, name):
    shard = source / "backend/data/carddb" / (name[0].lower() + ".json")
    return (load_json(shard, {}) or {}).get(name)


def discover_fresh_example(source, reparse, rows, effects, history):
    """Find the best unaccounted sole-shape member beyond plan sample names."""
    by_shape = {}
    for row in rows:
        match = re.fullmatch(r"verb_unmapped:([a-z0-9_]+)", row.get("item", ""))
        verb = match.group(1) if match else None
        effect = VERB_EFFECT.get(verb or "")
        if effect and effect in effects:
            by_shape[row["item"]] = row
    for shard in sorted((source / "backend/data/carddb").glob("*.json")):
        data = load_json(shard, {}) or {}
        if not isinstance(data, dict):
            continue
        for name, card in sorted(data.items()):
            if not isinstance(card, dict) or card.get("status") != "review":
                continue
            result = reparse.reparse_card(card)
            shapes = sorted({kind for kind, _ in result.get("misses", [])})
            if len(shapes) != 1 or shapes[0] not in by_shape:
                continue
            row = by_shape[shapes[0]]
            details = [detail for kind, detail in result.get("misses", []) if kind == shapes[0]]
            if len(details) != 1:
                continue
            text_hash = digest_bytes((card.get("text") or "").encode())
            production_key = "build-plan:%s:%s" % (row["item"], text_hash)
            if production_key in history:
                continue
            # Alphabetical shard/name order is deterministic. Return the
            # first safe unaccounted member instead of rescanning all 18k
            # review cards merely to optimize plan rank; keeping the local
            # worker fed is more valuable and stays within producer timeout.
            return row, name
    return None


def slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:54] or "work"


def next_ticket_id(ticket_dir, base):
    used = set()
    for path in ticket_dir.glob("*.json"):
        value = load_json(path, {}) or {}
        ticket_id = value.get("id", "")
        match = re.fullmatch(r"ticket:" + re.escape(base) + r"/v(\d+)", ticket_id)
        if match:
            used.add(int(match.group(1)))
    version = 1
    while version in used:
        version += 1
    return "ticket:%s/v%d" % (base, version)


def production_history(ticket_dir, jobs_path):
    jobs = (load_json(jobs_path, {}) or {}).get("jobs", {})
    result = {}
    for path in sorted(ticket_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
        value = load_json(path, {}) or {}
        key = value.get("production", {}).get("key")
        if not key:
            continue
        state = (jobs.get(value.get("id"), {}) or {}).get("state")
        job = jobs.get(value.get("id"), {}) or {}
        result.setdefault(key, []).append({"ticket_id": value.get("id"), "state": state,
                                           "outcome": job.get("outcome"),
                                           "profile": job.get("dispatch_profile", job.get("profile")),
                                           "receipt": (job.get("integration_receipt")
                                                       if job.get("state") == "integration_failed"
                                                       else job.get("receipt")),
                                           "retry_generation": int(value.get("production", {}).get("retry_generation", 0))})
    return result


def parser_anchor(parser_path):
    for number, line in enumerate(parser_path.read_text().splitlines(), 1):
        if line.startswith("def map_atom("):
            return "%d-%d" % (number, number + 339)
    raise ValueError("map_atom not found")


def emit(status, **extra):
    print(json.dumps({"schema": "factory.ticket-production/v1", "status": status, **extra},
                     indent=2, sort_keys=True))


def integration_repair_candidate(source, ticket_dir, jobs_path, reparse, trial_id=None, only_ids=None):
    """Repair accepted Map work independently of the changing discovery frontier.

    Already-auto cards and misses that moved to another parser stage disappear
    from the sole-shape plan, but their failed integration is still owed a
    truthful disposition. Keep the original gates/scope and issue a fresh,
    bounded revision with current parser evidence; never replay stale hunks.
    """
    jobs = (load_json(jobs_path, {}) or {}).get('jobs', {})
    specs = [load_json(path, {}) or {} for path in ticket_dir.glob('*.json')]
    ticket_index = {ticket['id']: ticket for ticket in specs if ticket.get('id')}
    superseded = {ticket.get('supersedes') for ticket in specs}
    from factory_ng_context_recovery import context_repair_requests, CONTEXT_VERSION
    from factory_ng_retry_batch import read_batch, selected, active_count
    batch = read_batch(OPS)
    batch_full = active_count(batch, ticket_index, jobs) >= 2
    for job in sorted(jobs.values(), key=lambda item: item.get('ticket_id', '')):
        if only_ids is not None and job.get('ticket_id') not in only_ids:
            continue
        if batch_full and selected(batch, job.get('ticket_id', '')):
            continue
        integration_failure = (job.get('state') == 'integration_failed'
                               and job.get('outcome') in ('candidate_conflict', 'full_gate_failed'))
        repair_gate_failure = (job.get('state') == 'failed' and job.get('outcome') == 'gate_failed')
        possible_context_failure = (job.get('state') in ('parked', 'failed')
                                    and job.get('outcome') in ('parked', 'infrastructure_failed_model_protocol'))
        if (job.get('work_type') != 'map' or not (integration_failure or repair_gate_failure or possible_context_failure)
                or job.get('superseded_by') or job.get('ticket_id') in superseded):
            continue
        original = next((ticket for ticket in specs if ticket.get('id') == job.get('ticket_id')), None)
        if not original:
            continue
        if trial_id is not None and original.get('production', {}).get('trial_id') != trial_id:
            continue
        history = map_repair_history(original, ticket_index)
        if history['error'] or history['generation'] >= MAP_REPAIR_LIMIT:
            continue
        if repair_gate_failure and not history['obligation']:
            continue  # This reserve repairs integration obligations, not generic worker failures.
        observation_path = OPS / job.get('receipt', '')
        observation = load_json(observation_path, {}) or {}
        requests = context_repair_requests(OPS, observation, original, history, ticket_index) if possible_context_failure else []
        if not (str(observation.get('outcome', '')).startswith('accepted') if integration_failure
                else bool(requests) if possible_context_failure else observation.get('outcome') == 'gate_failed'):
            continue
        original_path = OPS / job['ticket_path']
        if observation.get('ticket', {}).get('sha256') != digest_file(original_path):
            continue
        measurement_paths = [OPS / item['path'] for item in original.get('evidence', [])
                             if str(item.get('path', '')).endswith('.json')
                             and '/measurements/' in str(item.get('path', ''))]
        measurement = next((value for path in measurement_paths
                            if (value := load_json(path, {})).get('schema') == 'factory.targeted-demand/v1'), None)
        if not measurement or not measurement.get('members'):
            continue
        current = []
        for member in measurement['members']:
            card = card_record(source, member['name'])
            if (not card or card.get('status') not in ('review', 'auto')
                    or digest_bytes((card.get('text') or '').encode()) != member['text_sha256']):
                break
            result = reparse.reparse_card(card)
            current.append({'card': member['name'], 'status': card['status'],
                            'eligible': result.get('eligible'), 'misses': result.get('misses', []),
                            'oracle_text': card.get('text', '')})
        if len(current) != len(measurement['members']):
            continue
        ticket = json.loads(json.dumps(original))
        ticket['id'] = next_ticket_id(ticket_dir, original['id'].removeprefix('ticket:').rsplit('/v', 1)[0])
        ticket['supersedes'] = original['id']
        ticket['parents'] = list(dict.fromkeys(original.get('parents', []) + [original['id']]))
        ticket['title'] = 'Repair failed integration: ' + original['title']
        ticket['source'] = {'repository': str(source), 'revision': source_revision(source), 'clean': True}
        generation = history['generation'] + 1
        ticket['production'].update(producer='build-plan-integration-recovery',
                                    integration_repair_generation=generation,
                                    retry_reason='integration_conflict_repair')
        ticket['execution']['selection_reason'] = 'Rebase an accepted Map candidate against current source and verify its complete Oracle behavior; the discovery frontier no longer represents this failed obligation.'
        if requests:
            ticket['production']['context_repair_version'] = CONTEXT_VERSION
            ticket['production']['retry_reason'] = 'context_repair'
            if selected(batch, original['id']):
                ticket['production']['retry_batch'] = batch['id']
            ticket['execution']['context_requests'] = requests
            ticket['execution']['selection_reason'] = 'One bounded successor for a proven missing-source failure, with the original questions resolved against current source.'
        ticket['required_behavior'] += [
            'The prior observation is historical evidence, not proof that its patch is still correct. Preserve every current valid mapping. Do not restore an obsolete negative assertion for a shape now implemented.',
            'Keep every original gate command and allowed path. Add or repair the named positive and adjacent-negative tests on this revision; assert all Oracle clauses, counts, choices, controller restrictions and durations, not just eligibility or one removed miss.',
            'A pinned card already marked auto must still be reparsed and tested. If the implementation is already correct, return only meaningful regression-test changes; do not duplicate parser branches.',
            'If the miss moved to spell_seq_targeted or a required runtime behavior is absent, return a validated atomic NEEDS_PRIMITIVE demand. Do not hide the new miss, drop a clause, or force status auto.',
        ]
        parser_path = source / 'scripts/paragraph/reparse.py'
        lines = parser_path.read_text().splitlines()
        verb = measurement['shape'].removeprefix('verb_unmapped:')
        starts = [index + 1 for index, line in enumerate(lines)
                  if line == "    if verb == %r:" % verb]
        anchors = ([starts[0]] if starts else []) + ([starts[-1]] if len(starts) > 1 else [])
        source_evidence = [{'path': 'scripts/paragraph/reparse.py',
                            'anchor': '%d-%d' % (start, start + 139),
                            'sha256': digest_file(parser_path),
                            'fact': 'Current exact %s branch; inspect the complete-card probe before editing.' % verb}
                           for start in anchors]
        # Retain historical measurements/registry facts, not stale source line anchors.
        ticket['evidence'] = source_evidence + [item for item in original['evidence']
                                                if item.get('path') != 'scripts/paragraph/reparse.py']
        ticket['evidence'].append({'path': job.get('integration_receipt') if integration_failure else job['receipt'],
                                  'fact': 'Failed integration recovery; current pinned-card audit: ' + json.dumps(current, sort_keys=True)})
        if requests:
            ticket['evidence'][-1]['fact'] = 'Context-only failure retained; fresh source answers are required. Current pinned-card audit: ' + json.dumps(current, sort_keys=True)
        if repair_gate_failure:
            failures = [gate for gate in observation.get('gates', []) if gate.get('outcome') == 'failed']
            ticket['required_behavior'].append('Repair the observed failing contract without weakening it: ' + json.dumps(failures, sort_keys=True))
        return ticket
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=SOURCE)
    parser.add_argument("--ticket-dir", type=Path, default=TICKETS)
    parser.add_argument("--jobs", type=Path, default=JOBS)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--lane", choices=("all", "fresh", "conflict", "repair"), default="all",
                        help="emit fresh local work, paid repairs, or the legacy combined frontier")
    args = parser.parse_args()
    source = args.repo.resolve()
    plan_path = args.plan or source / "corpus/build-plan.jsonl"
    if not clean_source(source):
        emit("source_dirty", reason="canonical ground-truth checkout is dirty")
        return
    parser_path = source / "scripts/paragraph/reparse.py"
    sys.path.insert(0, str(parser_path.parent))
    import reparse  # noqa: E402

    if args.lane in ('all', 'conflict'):
        repair = integration_repair_candidate(source, args.ticket_dir, args.jobs, reparse)
        if repair:
            emit('ready', ticket_id=repair['id'], ticket=repair)
            return
    if not plan_path.is_file():
        emit("no_source_measurement", reason="coverage build plan is missing")
        return

    effects = registry_effects(source)
    history = production_history(args.ticket_dir, args.jobs)
    rows = [json.loads(line) for line in plan_path.read_text().splitlines() if line.strip()]
    if args.lane == "fresh":
        discovered = discover_fresh_example(source, reparse, rows, effects, history)
        if discovered:
            row, name = discovered
            if name not in row.get("examples", []):
                row.setdefault("examples", []).append(name)
    skipped = {"unsupported_item": 0, "no_live_example": 0, "already_accounted": 0}

    for row in rows:
        match = re.fullmatch(r"verb_unmapped:([a-z0-9_]+)", row.get("item", ""))
        verb = match.group(1) if match else None
        effect = VERB_EFFECT.get(verb or "")
        if not effect or effect not in effects:
            skipped["unsupported_item"] += 1
            continue
        shape = "verb_unmapped:" + verb
        for name in row.get("examples", []):
            card = card_record(source, name)
            if not isinstance(card, dict) or card.get("status") != "review":
                continue
            result = reparse.reparse_card(card)
            matches = [detail for kind, detail in result.get("misses", []) if kind == shape]
            all_shapes = sorted({kind for kind, _ in result.get("misses", [])})
            if len(matches) != 1 or all_shapes != [shape]:
                continue
            text_hash = digest_bytes((card.get("text") or "").encode())
            production_key = "build-plan:%s:%s" % (row["item"], text_hash)
            retry_parent = None
            retry_generation = 0
            retry_reason = None
            retry_receipt = None
            if production_key in history:
                if args.lane == "fresh":
                    skipped["already_accounted"] += 1
                    continue
                latest = history[production_key][-1]
                conflict_retry = (latest.get("state") == "integration_failed" and
                                  latest.get("outcome") == "candidate_conflict" and
                                  latest.get("retry_generation", 0) < 2)
                if args.lane == "conflict" and not conflict_retry:
                    skipped["already_accounted"] += 1
                    continue
                if args.lane == "repair" and conflict_retry:
                    skipped["already_accounted"] += 1
                    continue
                retryable_terminal = (conflict_retry or
                                      (latest.get("state") in ("failed", "integration_failed") and
                                       (str(latest.get("outcome", "")).startswith("infrastructure_failed") or
                                        (latest.get("outcome") == "gate_failed" and
                                         latest.get("profile") == "qwen-prepared-direct@1.0.2")) and
                                       latest.get("retry_generation", 0) < 1))
                if retryable_terminal:
                    retry_parent = latest["ticket_id"]
                    retry_generation = latest.get("retry_generation", 0) + 1
                    retry_reason = ("integration_conflict_repair" if conflict_retry else
                                    "semantic_gate_repair" if latest.get("outcome") == "gate_failed" else
                                    "infrastructure_repair")
                    retry_receipt = latest.get("receipt")
                else:
                    skipped["already_accounted"] += 1
                    continue
            elif args.lane in ("repair", "conflict"):
                # A repair lane must never consume or duplicate a fresh local
                # candidate.  The independent fresh lane keeps Qwen supplied
                # even while paid repair inventory exists earlier in the plan.
                continue

            suffix = hashlib.sha256(production_key.encode()).hexdigest()[:10]
            base = "map.plan-%s-%s-%s" % (slug(verb), slug(name), suffix)
            ticket_id = next_ticket_id(args.ticket_dir, base)
            test_path = "scripts/paragraph/test_factory_ng_%s.py" % suffix
            measurement_path = ("docs/factory-ng/measurements/build-plan-%s-v1.json" % suffix
                                if retry_generation == 0 else
                                "docs/factory-ng/measurements/build-plan-%s-retry%d.json" %
                                (suffix, retry_generation))
            measurement = {
                "schema": "factory.targeted-demand/v1",
                "shape": shape,
                "member_count": 1,
                "review_cards_scanned": 1,
                "members": [{"name": name, "oracle_text": card.get("text") or "",
                             "text_sha256": text_hash,
                             "all_miss_shapes": all_shapes, "details": matches}],
                "source": {"repository": str(source), "revision": source_revision(source),
                           "parser_sha256": digest_file(parser_path)},
                "plan": {"rank": row.get("rank"), "item": row["item"],
                         "marginal_unlock": row.get("marginal_unlock")},
            }
            registry = effects[effect]
            selected_profile = "claude-staged@1.0.0"
            selection_reason = (
                "A live sole-shape Map miss with exact Oracle text and a registered executor is bounded for the staged implementation worker."
                if retry_generation == 0 else
                "The local prepared candidate failed deterministic semantic gates; route one versioned repair with its receipt to a paid staged worker."
                if retry_reason == "semantic_gate_repair" else
                "The accepted candidate conflicted with a preceding integration; regenerate it once against the latest canonical revision."
                if retry_reason == "integration_conflict_repair" else
                "One infrastructure-only generation was exhausted; route the single versioned successor through the staged repair worker."
            )
            ticket = {
                "schema": "factory.ticket-spec/v1",
                "id": ticket_id,
                "title": "Map one proven %s class member: %s" % (row["item"], name),
                "work_type": "map",
                "lifecycle": "ready_for_observation",
                "parents": ["plan:%s" % row["item"]],
                "production": {"producer": "build-plan-continuous", "key": production_key,
                               "plan_rank": row.get("rank"),
                               "predicted_class_unlock": row.get("marginal_unlock"),
                               "retry_generation": retry_generation},
                "source": {"repository": str(source), "revision": source_revision(source), "clean": True},
                "skill": {"name": "implement-map-class", "path": str(SKILL.relative_to(OPS)),
                          "sha256": digest_file(SKILL)},
                "scope": {"allowed_paths": ["scripts/paragraph/reparse.py", test_path],
                          "forbidden_paths": ["backend/", "backend/data/",
                                              "scripts/paragraph/slotparse_oneshot.py"]},
                "evidence": [
                    {"path": measurement_path,
                     "fact": "%s is a current sole %s miss with pinned Oracle text." % (name, shape)},
                    {"path": registry["path"],
                     "fact": "The existing %s primitive is registered with executor %s and shape test %s."
                             % (effect, registry["executor"], registry["shape_test"])},
                    {"path": "scripts/paragraph/reparse.py", "sha256": digest_file(parser_path),
                     "anchor": parser_anchor(parser_path),
                     "fact": "map_atom is the bounded parser seam; Engine files are outside this ticket."},
                ],
                "required_behavior": [
                    "Map the exact current %s miss on %s through the already-registered %s primitive without losing any Oracle semantics."
                    % (shape, name, effect),
                    "The pinned card loses this miss and retains no new or silently swallowed miss.",
                    "Add a focused positive test plus an adjacent negative that must remain unmapped.",
                    "If the exact amount, recipient, filter, referent, or duration cannot execute through existing runtime behavior, return NEEDS_PRIMITIVE with one atomic CAPABILITY_JSON instead of a partial Map patch.",
                    "Do not edit Engine, converter, corpus data, or use a card-name special case.",
                ],
                "gates": [
                    "cd scripts/paragraph && python3 -m unittest %s" % Path(test_path).stem,
                    "git diff --check",
                    "git status --porcelain adds or changes only scripts/paragraph/reparse.py and %s" % test_path,
                    "python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo . --members-from /opt/development/magic-ops/%s reports zero remaining pinned members" % measurement_path,
                ],
                "execution": {
                    "mode": "isolated_clone_observation_only",
                    "selected_profile": selected_profile,
                    "compatible_profiles": (["claude-staged@1.0.0", "qwen-prepared-direct@1.0.2",
                                              "minimax-prepared-direct@1.0.0",
                                              "codex-constrained@1.0.0"] if retry_generation == 0 else
                                             ["claude-staged@1.0.0", "minimax-prepared-direct@1.0.0",
                                              "codex-constrained@1.0.0"]),
                    "selection_reason": selection_reason,
                    "parser_probes": [{"function": "reparse_card", "card": name}],
                    "effective_token_target": 200000,
                    "warning_reflection_threshold": 500000,
                    "automatic_stop": False,
                    "model_may_not_commit_push_deploy_or_mutate_live_tickets": True,
                },
                "on_failure": "Record a structured verdict. NEEDS_PRIMITIVE creates one Engine dependency; invalid or mixed premises are terminal and discovery advances to another candidate.",
            }
            if retry_parent:
                ticket["supersedes"] = retry_parent
                ticket["parents"].append(retry_parent)
                ticket["production"]["retry_reason"] = retry_reason
                if retry_receipt:
                    ticket["evidence"].append({
                        "path": retry_receipt,
                        "fact": ("The preceding accepted candidate conflicted during serialized integration; regenerate the same bounded behavior against the latest source."
                                 if retry_reason == "integration_conflict_repair" else
                                 "The previous local candidate and exact failed gates are retained for one bounded paid-profile repair."),
                    })
            emit("ready", ticket_id=ticket_id, ticket=ticket, measurement=measurement)
            return
        skipped["no_live_example"] += 1

    emit("exhausted_supported_plan", reason="no unaccounted engine-reachable sole-shape example remains",
         skipped=skipped)


if __name__ == "__main__":
    main()
