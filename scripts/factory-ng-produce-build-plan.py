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
import time
from factory_ng_producer_cache import ProducerCache, digest
from factory_ng_parser_runtime import prepare_parser
from pathlib import Path
from factory_ng_safety import source_problem
from factory_ng_recovery import map_repair_history, MAP_REPAIR_LIMIT


OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE
TICKETS = OPS / "docs/factory-ng/tickets"
JOBS = OPS / "state/factory-ng-jobs.json"
SKILL = OPS / "docs/factory-ng/skills/v1/implement-map-class/SKILL.md"

# Coverage-plan labels are parser categories, while the registry contains the
# typed effect names.  Keep this map explicit: a fuzzy name match is not proof
# that the runtime behavior exists.
VERB_EFFECT = {
    "draw": "draw",
    "p_draw": "draw",
    "draw_eq": "draw",
    "gain_life": "life_gain",
    "lose_life": "life_loss",
    "discard": "discard",
    "p_discard": "discard",
    "p_discard_hand": "discard",
    "mill": "mill",
    "damage": "damage",
    "damage_by": "damage",
    "fight": "fight",
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
    "p_sacrifice": "edict_sacrifice",
    "prevent": "prevent_damage_this_turn_scoped",
    "token_copy": "token_copy",
    "add_mana": "add_mana",
    "regenerate": "regenerate",
    "remove_counter": "remove_counter",
    "goad": "goad",
}

VERB_REQUIREMENTS = {
    'draw_eq': 'Evaluate the exact live count at resolution, preserving its owner, zone, filters and variable/referent binding. A guessed or fixed draw amount is not equivalent.',
    'p_discard_hand': 'Discard the specified player\'s entire hand using that player\'s current hand size, preserving each-player scope and sequence timing; never substitute the controller\'s or one opponent\'s hand count for another player.',
    'p_sacrifice': 'Preserve the sacrificing player, their choice, permanent filter, count and any greatest/least/fraction constraint. Sacrifice is not destruction, and the caster must not choose the opponent\'s permanents. Unsupported selectors require an Engine dependency.',
    'token_copy': 'Preserve the copied object\'s identity, controller, copyable characteristics and all stated exceptions, token count, entry state and duration. Copying a spell or creating a generic token is not equivalent. Linked delayed exile/sacrifice requires executable referent binding.',
    'add_mana': 'Preserve colors, amount, who chooses colors, any-combination versus one-color choice, spending restrictions and mana lifetime. Preserve whether the ability uses the stack and is a mana ability. Unsupported payment or choice behavior requires an Engine dependency.',
    'regenerate': 'The regenerate effect is self-only; use the separately registered regenerate_target effect for explicit targets. Preserve controller/type restrictions and shield lifetime. Group/referent shapes require an Engine dependency if unsupported; regeneration is not indestructibility.',
    'remove_counter': 'The documented remove_counter executor is self-only. Preserve counter type, amount, chosen object/player and whether removal is an effect or a cost; never substitute source counters for target counters. Unsupported target/choice shapes require an Engine dependency.',
    'goad': 'Preserve each chosen creature, controller restrictions, duration, must-attack and attack-another-player behavior. Never replace goad with haste or an unconditional forced attack; unsupported filters or duration require an Engine dependency.',
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
    # Go syntax is required: an executor description can itself contain `})`,
    # and comments/unused functions are not runtime registrations.
    from factory_ng_vocabulary import vocabulary
    entries = vocabulary(source)['metadata']
    for entry in entries.values():
        entry['path'] = str(Path(entry['path']).relative_to(source))
    return entries


def card_record(source, name):
    shard = source / "backend/data/carddb" / (name[0].lower() + ".json")
    return (load_json(shard, {}) or {}).get(name)


class ScanPending(Exception):
    pass


class ProductionHistory(dict):
    """Index card ownership across shape changes and dependency resumes."""
    def __init__(self):
        super().__init__()
        self.text_hashes = set()
        self.multi_text_hashes = set()
        self.versions = {}


def production_text_hash(key):
    match = re.search(r'sha256:[a-f0-9]{64}', key) if key.startswith('build-plan:') else None
    return match.group(0) if match else None


def owned_texts(history, multi_only=False):
    indexed = getattr(history, 'multi_text_hashes' if multi_only else 'text_hashes', None)
    if indexed is not None:
        return indexed
    return {value for key in history
            if (not multi_only or key.startswith('build-plan:multi:'))
            and (value := production_text_hash(key))}


def eligible_shapes(misses, effects, miss_count=1, max_misses=None):
    shapes = sorted({kind for kind, _ in misses})
    if max_misses is None:
        if len(misses) != miss_count or len(shapes) != 1:
            return []
    elif not 2 <= len(misses) <= max_misses:
        return []
    for shape in shapes:
        match = re.fullmatch(r'verb_unmapped:([a-z0-9_]+)', shape)
        if not match or VERB_EFFECT.get(match.group(1)) not in effects:
            return []
    return shapes


def candidate_retry(history, production_key, lane):
    """Share admission rules between full-corpus discovery and ticket emission.

    Age alone never grants another attempt. Only the existing bounded repair
    classes qualify, and a successor with a different production key still
    owns its ancestor's work.
    """
    if lane in ('fresh', 'all'):
        # Widening admission never grants fresh attempts to an existing card.
        # Conversely a multi-miss card cannot reappear in the single-miss lane
        # after a dependency reduces its remaining misses or changes family.
        multi = production_key.startswith('build-plan:multi:')
        text_hash = production_text_hash(production_key)
        if text_hash and text_hash in owned_texts(history, multi_only=not multi):
            return None
    chain = history.get(production_key, [])
    if not chain:
        return {} if lane in ('fresh', 'all') else None
    if lane == 'fresh':
        return None
    if any(item.get('dedicated_recovery') for item in chain):
        # Integration obligations and controlled cohorts have their own
        # producers/contracts. Never replace those with a generic Map retry.
        return None
    latest = chain[-1]
    if latest.get('superseded'):
        return None
    generation = max(item.get('retry_generation', 0) for item in chain)
    conflict = (latest.get('state') == 'integration_failed'
                and latest.get('outcome') == 'candidate_conflict' and generation < 2)
    if (lane == 'conflict' and not conflict) or (lane == 'repair' and conflict):
        return None
    repair = (latest.get('state') in ('failed', 'integration_failed') and generation < 1
              and (str(latest.get('outcome', '')).startswith('infrastructure_failed')
                   or latest.get('outcome') == 'gate_failed'
                   and latest.get('profile') == 'qwen-prepared-direct@1.0.2'))
    if not (conflict or repair):
        return None
    return {'parent': latest['ticket_id'], 'generation': generation + 1,
            'reason': ('integration_conflict_repair' if conflict else
                       'semantic_gate_repair' if latest.get('outcome') == 'gate_failed' else
                       'infrastructure_repair'), 'receipt': latest.get('receipt')}


def discover_fresh_example(source, reparse, rows, effects, history, cache=None, revision=None, budget_seconds=15, miss_count=1, lane='fresh', max_misses=None, snapshot=None, parser_stamp=None):
    """Find a current eligible member anywhere in the corpus, including repairs."""
    by_shape = {}
    for row in rows:
        match = re.fullmatch(r"verb_unmapped:([a-z0-9_]+)", row.get("item", ""))
        verb = match.group(1) if match else None
        effect = VERB_EFFECT.get(verb or "")
        if effect and effect in effects:
            by_shape[row["item"]] = row
    cards = snapshot
    if cards is None:
        cards = []
        for shard in sorted((source / "backend/data/carddb").glob("*.json")):
            data = load_json(shard, {}) or {}
            if isinstance(data, dict):
                cards.extend((name, card) for name, card in sorted(data.items())
                             if isinstance(card, dict) and card.get('status') == 'review')
    scan_key = str(source.resolve()) + ":miss-count=" + str(miss_count)
    cursor_key = scan_key if lane == 'fresh' else scan_key + ':lane=' + lane
    if max_misses is not None:
        cursor_key = str(source.resolve()) + ':multi-miss:2-' + str(max_misses)
    cursor = 0
    if cache:
        found, previous = cache.get('fresh-cursor-v1', cursor_key, 'position')
        if found:
            cursor = next((i for i, (name, _) in enumerate(cards) if name > previous), 0)
    repair_texts = ({production_text_hash(key) for key in history
                     if candidate_retry(history, key, lane) is not None}
                    if lane in ('repair', 'conflict') else None)
    started = time.monotonic()
    ordered = cards[cursor:] + cards[:cursor]
    for number, (name, card) in enumerate(ordered):
        if repair_texts is not None and digest_bytes((card.get('text') or '').encode()) not in repair_texts:
            continue  # A card with no eligible repair lineage cannot emit work in this lane.
        key = scan_key + ':' + name
        stamp = str(parser_stamp if parser_stamp is not None else revision) + ':' + digest(card)
        found, result = cache.get('fresh-parse-v1', key, stamp) if cache else (False, None)
        if not found:
            result = {'misses': reparse.reparse_card(card).get('misses', [])}
            if cache:
                cache.put('fresh-parse-v1', key, stamp, result)
        shapes = eligible_shapes(result['misses'], effects, miss_count, max_misses)
        if cache:
            cache.put('fresh-cursor-v1', cursor_key, 'position', name)
            if number % 50 == 0:
                cache.checkpoint()
        if shapes and all(shape in by_shape for shape in shapes):
            row = by_shape[shapes[0]]
            details = [detail for kind, detail in result['misses'] if kind == shapes[0]]
            text_hash = digest_bytes((card.get('text') or '').encode())
            production_key = 'build-plan:%s:%s' % ('multi' if max_misses is not None else row['item'], text_hash)
            if candidate_retry(history, production_key, lane) is not None:
                # Cache selects candidates only. The caller reparses the exact
                # card and verifies source identity before publishing a ticket.
                return row, name
        if cache and time.monotonic() - started >= budget_seconds:
            cache.checkpoint()
            raise ScanPending('bounded fresh scan will resume after ' + name)

    return None


def slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:54] or "work"


def ticket_catalog(ticket_dir, cache=None):
    def project(value):
        return {k: value[k] for k in ('id', 'supersedes', 'production', 'work_type') if k in value} if isinstance(value, dict) else {}
    if cache:
        return cache.files('build-plan-history-v2', ticket_dir, project)
    return [(path, load_json(path, {}) or {}) for path in sorted(ticket_dir.glob('*.json'))]


def next_ticket_id(ticket_dir, base, history=None, cache=None):
    if history is not None:
        return "ticket:%s/v%d" % (base, history.versions.get(base, 0) + 1)
    used = set()
    for path, value in ticket_catalog(ticket_dir, cache):
        ticket_id = value.get("id", "")
        match = re.fullmatch(r"ticket:" + re.escape(base) + r"/v(\d+)", str(ticket_id))
        if match:
            used.add(int(match.group(1)))
    version = max(used, default=0) + 1
    return "ticket:%s/v%d" % (base, version)


def production_history(ticket_dir, jobs_path, cache=None):
    jobs = (load_json(jobs_path, {}) or {}).get("jobs", {})
    tickets = [value for _, value in ticket_catalog(ticket_dir, cache)]
    superseded = {ticket.get('supersedes') for ticket in tickets if ticket.get('supersedes')}
    # Numeric version order is durable; copying or restoring a file must not
    # make an old failed version look like the latest lifecycle state.
    def version(ticket):
        match = re.search(r'/v(\d+)$', str(ticket.get('id', '')))
        return int(match.group(1)) if match else 0
    tickets.sort(key=version)
    result = ProductionHistory()
    for value in tickets:
        match = re.fullmatch(r'ticket:(.+)/v(\d+)', str(value.get('id', '')))
        if match:
            result.versions[match[1]] = max(result.versions.get(match[1], 0), int(match[2]))
        key = value.get("production", {}).get("key")
        if not key:
            continue
        text_hash = production_text_hash(key)
        if text_hash:
            result.text_hashes.add(text_hash)
            if key.startswith('build-plan:multi:'):
                result.multi_text_hashes.add(text_hash)
        state = (jobs.get(value.get("id"), {}) or {}).get("state")
        job = jobs.get(value.get("id"), {}) or {}
        result.setdefault(key, []).append({"ticket_id": value.get("id"), "state": state,
                                           "superseded": value.get('id') in superseded or bool(job.get('superseded_by')),
                                           "dedicated_recovery": bool(
                                               value.get('production', {}).get('producer') not in (None, 'build-plan-continuous')
                                               or value.get('production', {}).get('integration_repair_generation')
                                               or value.get('production', {}).get('integration_recovery_parent')
                                               or value.get('production', {}).get('trial_id')
                                               or value.get('production', {}).get('retry_batch')),
                                           "outcome": job.get("outcome"),
                                           "profile": job.get("dispatch_profile", job.get("profile")),
                                           "receipt": (job.get("integration_receipt")
                                                       if job.get("state") == "integration_failed"
                                                       else job.get("receipt")),
                                           "retry_generation": int(value.get("production", {}).get("retry_generation", 0))})
    if cache:
        cache.checkpoint()
    return result


def parser_anchor(parser_path):
    for number, line in enumerate(parser_path.read_text().splitlines(), 1):
        if line.startswith("def map_atom("):
            return "%d-%d" % (number, number + 339)
    raise ValueError("map_atom not found")


def emit(status, **extra):
    print(json.dumps({"schema": "factory.ticket-production/v1", "status": status, **extra},
                     indent=2, sort_keys=True))


def integration_repair_candidate(source, ticket_dir, jobs_path, reparse, trial_id=None, only_ids=None, cache=None):
    """Repair accepted Map work independently of the changing discovery frontier.

    Already-auto cards and misses that moved to another parser stage disappear
    from the sole-shape plan, but their failed integration is still owed a
    truthful disposition. Keep the original gates/scope and issue a fresh,
    bounded revision with current parser evidence; never replay stale hunks.
    """
    jobs = (load_json(jobs_path, {}) or {}).get('jobs', {})
    catalog = ticket_catalog(ticket_dir, cache)
    if cache:
        cache.checkpoint()
    specs = [ticket for _, ticket in catalog]
    paths = {ticket['id']: path for path, ticket in catalog if ticket.get('id')}
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
        original = ticket_index.get(job.get('ticket_id'))
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
        if cache:
            original = load_json(paths[original['id']], {}) or {}
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
        ticket['id'] = next_ticket_id(ticket_dir, original['id'].removeprefix('ticket:').rsplit('/v', 1)[0], cache=cache)
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


def add_verb_contract(ticket, verb, effects, name):
    if verb in VERB_REQUIREMENTS:
        ticket['required_behavior'].append(VERB_REQUIREMENTS[verb])
    if verb == 'regenerate' and 'regenerate_target' in effects:
        ticket['required_behavior'][0] = (
            'Map the exact current regenerate miss on %s through regenerate for self or regenerate_target for an explicit target, only where the documented runtime supports the complete Oracle semantics.' % name)
        target_registry = effects['regenerate_target']
        ticket['evidence'].append({
            'path': target_registry['path'],
            'fact': 'The separate regenerate_target effect has executor %s and shape test %s; use it only for its supported explicit-target shapes.' %
                    (target_registry['executor'], target_registry['shape_test'])})
    if verb in ('draw', 'p_draw', 'draw_eq', 'gain_life', 'lose_life', 'discard', 'p_discard', 'p_discard_hand', 'mill'):
        ticket['required_behavior'].append(
            'Preserve the exact player (controller, opponent, chosen target or each player), quantity, variable binding and choice timing. Discard choice versus random discard and mill destination must remain exact. Registry membership alone does not prove these argument shapes; request an atomic Engine dependency when the public resolution/choice path is missing.')
    if verb == 'prevent':
        ticket['required_behavior'].append(
            'Distinguish the damage source filter from the protected recipient, combat-only from all damage, and unlimited prevention from a next-N shield. The scoped primitive proves only its documented shapes; other prevention semantics require an Engine dependency.')
    if verb in ('fight', 'damage_by'):
        ticket['required_behavior'].append(
            'Preserve both participant identities, controller restrictions, damage source, live power/toughness and targeting choices. Fight deals damage in both directions; damage_by is one-way. If the existing runtime cannot express the exact source/recipient pair or choice, return NEEDS_PRIMITIVE; never replace it with damage from this spell or its controller.')


def add_multi_contract(ticket, measurement, misses, effects, name, primary_verb):
    """Bind every unresolved clause to the unchanged complete-card gates."""
    shapes = sorted({kind for kind, _ in misses})
    verbs = [shape.split(':', 1)[1] for shape in shapes]
    for verb in verbs:
        if verb == primary_verb:
            continue
        effect = VERB_EFFECT[verb]
        registry = effects[effect]
        ticket['evidence'].append({
            'path': registry['path'],
            'fact': 'The %s family uses registered effect %s, executor %s, shape test %s. Exact arguments still require runtime proof.' %
                    (verb, effect, registry['executor'], registry['shape_test'])})
        add_verb_contract(ticket, verb, effects, name)
    count = len(misses)
    ticket['title'] = 'Map complete card with %d unresolved clauses: %s' % (count, name)
    ticket['parents'] = ['plan:' + shape for shape in shapes]
    ticket['production'].update(multi_miss=True, miss_count=count, miss_shapes=shapes,
                                predicted_class_unlock=1)
    measurement.update(shapes=shapes, miss_count=count, multi_miss=True)
    measurement['plan'].update(items=shapes, marginal_unlock=1)
    measurement['members'][0]['misses'] = [{'shape': kind, 'detail': detail} for kind, detail in misses]
    ticket['evidence'][0]['fact'] = (
        '%s has %d current unresolved clauses across %s. The measurement pins every miss and the complete Oracle text.' %
        (name, count, ', '.join(shapes)))
    ticket['required_behavior'][:2] = [
        'Implement the complete Oracle behavior of %s, covering all %d pinned misses across %s and preserving every already-parsed ability.' %
        (name, count, ', '.join(shapes)),
        'The card must become fully eligible with zero remaining misses of ANY family. Clearing only the measurement headline shape, dropping an ability, or moving a miss to another category is failure.',
    ]
    ticket['required_behavior'].extend([
        'Tests must cover every pinned clause, its runtime representation, and their combined ordering, targets, quantities, choices, controller ownership, durations and linked referents. Include adjacent negative cases. Separate misses are not necessarily independent abilities.',
        'When runtime support is missing, return one Oracle-validated atomic NEEDS_PRIMITIVE demand. Its Engine dependency will be built separately; the resumed Map retains this complete-card contract and can request the next missing dependency. Do not return a partially working Map patch.',
    ])
    ticket['execution']['selection_reason'] = 'One complete card with two or more measured misses in explicitly supported runtime families; atomic Engine dependencies use the existing dependency/resume pipeline.'
    ticket['execution']['compatible_profiles'] = ['claude-staged@1.0.0', 'codex-constrained@1.0.0']
    ticket['on_failure'] = 'Compile one validated atomic dependency and resume this whole card after integration. Retain terminal failures and advance independent discovery; never mark a partially fixed card complete.'


def coverage_rows(plan_path):
    rows = [json.loads(line) for line in plan_path.read_text().splitlines() if line.strip()]
    # A historical top-N plan is ranking evidence, not the enabled-family list.
    # Every explicitly supported family must remain discoverable.
    measured = {row.get('item') for row in rows}
    rows.extend({'item': 'verb_unmapped:' + verb, 'rank': None,
                 'marginal_unlock': None, 'examples': []}
                for verb in VERB_EFFECT if 'verb_unmapped:' + verb not in measured)
    return rows


def produce(cache):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=SOURCE)
    parser.add_argument("--ticket-dir", type=Path, default=TICKETS)
    parser.add_argument("--jobs", type=Path, default=JOBS)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--lane", choices=("all", "fresh", "conflict", "repair"), default="all",
                        help="emit fresh local work, paid repairs, or the legacy combined frontier")
    parser.add_argument("--miss-count", type=int, choices=(1, 2), default=1,
                        help="exact remaining miss count; two is restricted to one verb family in the fresh lane")
    parser.add_argument("--max-active", type=int,
                        help="bound active fresh tickets admitted with this miss count")
    parser.add_argument('--max-misses', type=int,
                        help='fresh multi-miss lane: two through this many misses, including mixed supported families')
    args = parser.parse_args()
    if args.miss_count != 1 and args.lane != "fresh":
        parser.error("--miss-count 2 requires --lane fresh")
    if args.max_misses is not None and (args.lane != 'fresh' or args.miss_count != 1
                                       or args.max_misses < 2 or args.max_active is not None):
        parser.error('--max-misses requires --lane fresh, a bound >= 2, and no --miss-count/--max-active override; the controller bounds runnable admission')
    if args.max_active is not None and args.max_active < 1:
        parser.error("--max-active must be positive")
    if args.max_active is not None:
        jobs = (load_json(args.jobs, {}) or {}).get('jobs', {})
        active = sum(
            1 for path in args.ticket_dir.glob('*.json')
            if (ticket := load_json(path, {}) or {}).get('production', {}).get('producer') == 'build-plan-continuous'
            and ticket.get('production', {}).get('miss_count', 1) == args.miss_count
            and jobs.get(ticket.get('id'), {}).get('state') in (ACTIVE_STATES | {'blocked'}))
        if active >= args.max_active:
            emit('active_frontier_limit', reason='bounded miss-count frontier already has %d active tickets' % active)
            return
    source = args.repo.resolve()
    plan_path = args.plan or source / "corpus/build-plan.jsonl"
    if not clean_source(source):
        emit("source_dirty", reason="canonical ground-truth checkout is dirty")
        return
    scan_revision = source_revision(source)
    parser_path = source / "scripts/paragraph/reparse.py"
    sys.path.insert(0, str(parser_path.parent))
    import reparse  # noqa: E402
    snapshot, parser_stamp, _ = prepare_parser(source, reparse, cache)
    if source_revision(source) != scan_revision or not clean_source(source):
        # No cached parser output from a mixed checkout may survive this run.
        cache.db.execute("DELETE FROM cache WHERE namespace='parser-vocabulary-v1' AND key=?", (str(source),))
        emit('source_unavailable', reason='canonical source changed during parser preparation')
        return

    if args.lane in ('all', 'conflict'):
        repair = integration_repair_candidate(source, args.ticket_dir, args.jobs, reparse, cache=cache)
        if repair:
            if source_revision(source) != scan_revision or not clean_source(source):
                emit('source_unavailable', reason='canonical source changed during repair preparation')
                return
            emit('ready', ticket_id=repair['id'], ticket=repair)
            return
    if not plan_path.is_file():
        emit("no_source_measurement", reason="coverage build plan is missing")
        return

    effects = registry_effects(source)
    history = production_history(args.ticket_dir, args.jobs, cache)
    rows = coverage_rows(plan_path)
    if args.lane in ('fresh', 'repair', 'conflict'):
        try:
            discovered = discover_fresh_example(source, reparse, rows, effects, history,
                                                cache, scan_revision, miss_count=args.miss_count, lane=args.lane,
                                                max_misses=args.max_misses, snapshot=snapshot, parser_stamp=parser_stamp)
        except ScanPending as exc:
            emit('scan_pending', reason=str(exc))
            return
        finally:
            if source_revision(source) != scan_revision:
                cache.db.execute("DELETE FROM cache WHERE namespace='fresh-parse-v1' AND stamp LIKE ?", (parser_stamp + ':%',))
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
            misses = result.get('misses', [])
            all_shapes = eligible_shapes(misses, effects, args.miss_count, args.max_misses)
            if not all_shapes or shape not in all_shapes:
                continue
            matches = [detail for kind, detail in misses if args.max_misses is not None or kind == shape]
            text_hash = digest_bytes((card.get("text") or "").encode())
            production_key = "build-plan:%s:%s" % ('multi' if args.max_misses is not None else row['item'], text_hash)
            retry = candidate_retry(history, production_key, args.lane)
            if retry is None:
                skipped['already_accounted'] += 1
                continue
            retry_parent = retry.get('parent')
            retry_generation = retry.get('generation', 0)
            retry_reason = retry.get('reason')
            retry_receipt = retry.get('receipt')

            suffix = hashlib.sha256(production_key.encode()).hexdigest()[:10]
            base = "map.plan-%s-%s-%s" % ('multi' if args.max_misses is not None else slug(verb), slug(name), suffix)
            ticket_id = next_ticket_id(args.ticket_dir, base, history)
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
                "A live single-family Map member with exact Oracle text and a registered executor is bounded for the staged implementation worker."
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
                               "retry_generation": retry_generation, "miss_count": args.miss_count},
                "source": {"repository": str(source), "revision": source_revision(source), "clean": True},
                "skill": {"name": "implement-map-class", "path": str(SKILL.relative_to(OPS)),
                          "sha256": digest_file(SKILL)},
                "scope": {"allowed_paths": ["scripts/paragraph/reparse.py", test_path],
                          "forbidden_paths": ["backend/", "backend/data/",
                                              "scripts/paragraph/slotparse_oneshot.py"]},
                "evidence": [
                    {"path": measurement_path,
                     "fact": "%s has exactly %d current %s misses and no other miss family, with pinned Oracle text." % (name, args.miss_count, shape)},
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
                    "The pinned card loses all %d misses of this family and becomes eligible with no new or silently swallowed miss." % args.miss_count,
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
            add_verb_contract(ticket, verb, effects, name)
            if args.miss_count == 2:
                ticket['required_behavior'].append(
                    'Both pinned misses are one bounded verb-family task. Cover both occurrences in focused tests, preserving their separate targets, amounts, timing and ordering. A patch fixing only one occurrence is incomplete and must fail the whole-card pinned gate.')
            if args.max_misses is not None:
                add_multi_contract(ticket, measurement, misses, effects, name, verb)
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
            if source_revision(source) != scan_revision or not clean_source(source):
                emit('source_unavailable', reason='canonical source changed during producer scan; retry on current source')
                return
            emit("ready", ticket_id=ticket_id, ticket=ticket, measurement=measurement)
            return
        skipped["no_live_example"] += 1

    reason = ('no unaccounted card with 2..%d misses entirely in supported runtime families remains' % args.max_misses
              if args.max_misses is not None else
              'no unaccounted engine-reachable single-family example with exactly %d misses remains' % args.miss_count)
    emit("exhausted_supported_plan", reason=reason,
         skipped=skipped)


def main():
    cache = ProducerCache(OPS / 'state/factory-ng-producer-cache.sqlite3')
    try:
        produce(cache)
    finally:
        cache.close()


if __name__ == "__main__":
    main()
