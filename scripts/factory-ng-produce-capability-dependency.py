#!/usr/bin/env python3
"""Compile validated Map capability verdicts into Engine work and Map resumes.

This is a deterministic lifecycle producer.  A Map receipt carrying a
validated ``capability_demand`` creates exactly one Engine TicketSpec.  Once
that Engine ticket is fully integrated, the producer revalidates the blocked
Map member against current ground truth and emits a revision-pinned successor.
No human queue refill or dependency transcription is required.
"""
import hashlib
import factory_ng_attention_recovery as attention_recovery
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from contextvars import ContextVar
from factory_ng_producer_cache import ProducerCache, receipt_demand
from factory_ng_safety import source_problem
from factory_ng_recovery import engine_repair_used, map_repair_history
from factory_ng_context import referenced_sources, failure_detail
from factory_ng_knowledge import search as knowledge_search, discover_capability, resolve_candidate, lookup_context


OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE

RUNS = OPS / "docs/factory-ng/runs"
TICKETS = OPS / "docs/factory-ng/tickets"
JOBS = OPS / "state/factory-ng-jobs.json"
POLICY = OPS / "config/factory-ng-policy.json"
ENGINE_SKILL = OPS / "docs/factory-ng/skills/v1/implement-engine-capability/SKILL.md"
ENGINE_ACTIVE_STATES = {"queued", "working", "awaiting_verification", "integrating", "awaiting_integration"}
CORE_PATHS = [
    "backend/game/ability_effects.go",
    "backend/game/dynamic_amount.go",
    "backend/game/effects.go",
    "backend/game/card.go",
    "backend/game/gamestate.go",
    "backend/game/targeting.go",
    "backend/cards/converter.go",
    "backend/cards/registry.go",
]


def digest_bytes(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_file(path):
    return digest_bytes(path.read_bytes())


def load_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def emit(status, **extra):
    revision = SCAN_REVISION.get()
    if status == 'ready' and revision and (source_revision() != revision or not source_clean()):
        status, extra = 'source_unavailable', {'reason': 'canonical source changed during producer scan; retry on current source'}
    print(json.dumps({"schema": "factory.ticket-production/v1", "status": status, **extra},
                     indent=2, sort_keys=True))


def engine_lane_likely_full():
    """Conservative check for whether the controller would reject a new Engine
    ticket right now.  This does not need to reproduce the controller's exact
    admission cap (which also factors in this-instant dispatch slots); it only
    needs to avoid proposing another Engine ticket when the lane is almost
    certainly saturated, so the scan below keeps going and can still surface
    an already-admissible Map resume elsewhere in the receipt list instead of
    losing the whole pass to a lane-capacity rejection on the same oldest
    Engine-type candidate every time.
    """
    queue = (load_json(POLICY, {}) or {}).get("queue", {})
    max_queued = int(queue.get("max_queued", 12))
    map_reserve = int(queue.get("map_reserve", 0))
    engine_cap = max(0, max_queued - map_reserve)
    jobs = (load_json(JOBS, {}) or {}).get("jobs", {})
    active_engine = sum(1 for job in jobs.values()
                        if job.get("work_type") == "engine" and job.get("state") in ENGINE_ACTIVE_STATES)
    return active_engine >= engine_cap


def source_revision():
    return subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()


def source_clean():
    return not source_problem(SOURCE)


SCAN_CACHE = ContextVar("producer_scan_cache", default=None)
SCAN_REVISION = ContextVar("producer_scan_revision", default=None)
SCAN_ORACLE = ContextVar("producer_scan_oracle", default=None)


def recover_valid_capability(receipt):
    """Revalidate a dependency rejected by an older, now-fixed contract bug."""
    if receipt.get("outcome") != "invalid_capability_demand":
        return None
    raw_path = next((item.get("path") for item in receipt.get("raw_artifacts", [])
                     if isinstance(item, dict) and item.get("path")), None)
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = OPS / path
    spec = importlib.util.spec_from_file_location(
        "factory_ng_capability_contract_recovery", OPS / "scripts/capability-contract.py")
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    try:
        stat = path.stat()
        stamp = '%s:%s:%s:%s' % (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size,
                                 digest_file(OPS / 'scripts/capability-contract.py'))
        cache = SCAN_CACHE.get()
        found, capability = cache.get('raw-capability-v1', path.resolve(), stamp) if cache else (False, None)
        if not found:
            raw = path.read_text(encoding='utf-8')
            replies = []
            for line in raw.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                item = event.get('item', {}) if isinstance(event, dict) else {}
                if item.get('type') == 'agent_message' and isinstance(item.get('text'), str):
                    replies.append(item['text'])
            try:
                capability = contract.extract(replies[-1] if replies else raw)
            except (ValueError, json.JSONDecodeError):
                capability = None
            if cache:
                cache.put('raw-capability-v1', path.resolve(), stamp, capability)
        if capability is None:
            return None
        records = SCAN_ORACLE.get()
        if records is None:
            records = contract.oracle_records(str(SOURCE))
            if cache:
                SCAN_ORACLE.set(records)
        contract.validate_oracle(capability, str(SOURCE), records=records)
        return capability
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "capability"


def camel(value):
    return "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", value) if part)


def engine_identity(capability):
    """Return the stable Engine ticket identity without preparing source evidence."""
    encoded = json.dumps(capability, sort_keys=True, separators=(",", ":")).encode()
    suffix = hashlib.sha256(encoded).hexdigest()[:10]
    key = slug(capability["key"])
    return "ticket:engine.auto-%s-%s/v1" % (key, suffix), encoded


def ticket_path_for_id(ticket_id):
    stem = ticket_id.removeprefix("ticket:").replace(".", "-").replace("/", "-")
    return TICKETS / (stem + ".json")


def ticket_by_id(ticket_id):
    direct = ticket_path_for_id(ticket_id)
    if direct.is_file():
        return direct, load_json(direct, {}) or {}
    for path in TICKETS.glob("*.json"):
        value = load_json(path, {}) or {}
        if value.get("id") == ticket_id:
            return path, value
    return None, None


def next_version(ticket_id, ticket_index=None):
    match = re.fullmatch(r"(ticket:[a-z0-9][a-z0-9._-]*)/v(\d+)", ticket_id)
    if not match:
        raise ValueError("blocked ticket id is not versioned")
    base = match.group(1)
    used = set()
    values = ticket_index.values() if ticket_index is not None else (
        load_json(path, {}) or {} for path in TICKETS.glob("*.json"))
    for value in values:
        found = re.fullmatch(re.escape(base) + r"/v(\d+)", value.get("id", ""))
        if found:
            used.add(int(found.group(1)))
    version = max(used or {0}) + 1
    return "%s/v%d" % (base, version)


def knowledge_hits(capability, limit=4):
    """The service owns discovery; source identities are re-resolved locally."""
    lookup = discover_capability(capability, 'capability-producer', limit=limit)
    lookups = lookup['lookups']
    if lookup['status'] == 'service_error':
        raise RuntimeError('Knowledge service unavailable; defer production: '+lookup['error'])
    result=[]
    for candidate in lookup.get('candidates',[]):
        if not candidate.get('symbol_id'): continue
        resolved=resolve_candidate(SOURCE,candidate,candidate.get('request_id',''),'capability-producer',120)
        if resolved['status'] != 'resolved': continue
        result.append({'path':resolved['path'],'sha256':resolved['sha256'],
                       'anchor':'%d-%d' % (resolved['start'],resolved['supplied_end']),
                       'symbol':candidate,'lookup_trace':lookups,
                       'fact':'Verified declaration %s in source revision %s; discovery is not proof of semantic suitability.'
                              % (resolved['qualified'],resolved['source_revision'])})
    if not result:
        # Preserve the miss for the packet; never invent a nearby code window.
        result.append({'path':'backend/game/ability_effects.go','lookup_trace':lookups,
                       'fact':'Knowledge discovery found no resolvable candidate. This is not evidence of a missing capability; verify source before proposing Engine work.'})
    return result


def source_evidence(capability):
    return knowledge_hits(capability)


def engine_ticket(parent_id, receipt_path, capability):
    ticket_id, encoded = engine_identity(capability)
    suffix = ticket_id.rsplit("-", 1)[1].removesuffix("/v1")
    # Different semantic specifications may share a human capability key.
    # Their required Go symbols must be as distinct as their ticket identities.
    test_name = "TestFactoryNG%s_%s" % (camel(capability["key"]), suffix)
    game_test = "backend/game/factory_ng_%s_test.go" % suffix
    cards_test = "backend/cards/factory_ng_%s_test.go" % suffix
    registry_file = "backend/cards/registry_factory_ng_%s.go" % suffix
    required = [capability["specification"]["required_behavior"]]
    negatives = capability["specification"].get("negative_examples", [])
    if negatives:
        required.append("Preserve these adjacent behaviors: " + "; ".join(negatives))
    required.extend([
        "Add a discriminating behavior test named %s; a compile-only assertion is insufficient." % test_name,
        "Register every new public effect using regEffect in the allowed registry_*.go file, with executor and runtime test metadata; never edit the frozen registry literal.",
        "Implement only this atomic dependency. Do not add parser patterns, corpus exceptions, or card-name special cases.",
    ])
    evidence = [{"path": str(receipt_path.relative_to(OPS)),
                 "fact": "A Map worker returned this Oracle-validated atomic capability demand.",
                 "capability": capability}]
    with lookup_context({'KB_TICKET':ticket_id,'KB_ATTEMPT':'ticket-preparation'}):
        evidence.extend(source_evidence(capability))
    return {
        "schema": "factory.ticket-spec/v1",
        "id": ticket_id,
        "title": "Implement atomic capability: " + capability["summary"],
        "work_type": "engine",
        "lifecycle": "ready_for_observation",
        "parents": [parent_id],
        "production": {"producer": "capability-dependencies",
                       "key": "capability:%s:%s" % (capability["key"], digest_bytes(encoded))},
        "capability": capability["specification"],
        "source": {"repository": str(SOURCE), "revision": source_revision(), "clean": True},
        "skill": {"name": "implement-engine-capability",
                  "path": str(ENGINE_SKILL.relative_to(OPS)), "sha256": digest_file(ENGINE_SKILL)},
        "scope": {
            "allowed_paths": list(dict.fromkeys(CORE_PATHS + [game_test, cards_test, registry_file] + [
                path for path in referenced_sources(SOURCE, capability['specification']['required_behavior'])
                if path.startswith(('backend/game/', 'backend/cards/')) and not path.endswith('_test.go')])),
            "forbidden_paths": ["backend/data/", "backend/cardfns/", "scripts/paragraph/"],
        },
        "evidence": evidence,
        "required_behavior": required,
        "gates": [
            "test -z \"$(gofmt -l $(git status --porcelain | awk '{print $2}' | grep '\\.go$'))\"",
            "cd backend && go test ./game ./cards -run '^%s$' -count=1" % test_name,
            "cd backend && go test ./game ./cards",
            "git diff --check",
        ],
        "execution": {
            "mode": "isolated_clone_observation_only",
            "selected_profile": "claude-staged@1.0.0",
            "compatible_profiles": ["claude-staged@1.0.0", "minimax-prepared-direct@1.0.0",
                                    "codex-constrained@1.0.0"],
            "selection_reason": "An Oracle-validated Map block has been compiled into one bounded Engine dependency.",
            "effective_token_target": 200000,
            "warning_reflection_threshold": 500000,
            "automatic_stop": False,
            "model_may_not_commit_push_deploy_or_mutate_live_tickets": True,
        },
        "on_failure": "Record an immutable bounded verdict; automatic discovery continues with independent work.",
    }


def receipt_verdict(job):
    """Read the actual VERDICT line out of a parked job's receipt.

    job['outcome'] is only ever the generic 'parked' for every park verdict
    (AMBIGUOUS, FRAMEWORK, SEMANTIC_GAP, NOT_A_SHAPE) — distinguishing them
    requires reading the receipt's own gate detail text.
    """
    receipt_path = job.get("receipt")
    if not receipt_path:
        return None
    path = Path(receipt_path)
    if not path.is_absolute():
        path = OPS / path
    receipt = load_json(path)
    if not isinstance(receipt, dict):
        return None
    for gate in receipt.get("gates", []):
        match = re.search(r"VERDICT:\s*([A-Z_]+)", gate.get("detail", "") or "")
        if match:
            return match.group(1)
    return None


def gate_failure_detail(job):
    """Pull the exact failing-gate text out of a gate_failed job's receipt."""
    receipt_path = job.get('integration_receipt') if job.get('state') == 'integration_failed' else job.get('receipt')
    if not receipt_path:
        return None
    path = Path(receipt_path)
    if not path.is_absolute():
        path = OPS / path
    receipt = load_json(path)
    if not isinstance(receipt, dict):
        return None
    candidate = receipt.get('excluded_candidates', {}).get(job.get('ticket_id'), {})
    failing = [gate for gate in candidate.get('gates', receipt.get("gates", [])) if gate.get("outcome") == "failed"]
    if not failing:
        return candidate.get('reason') or receipt.get('reason')
    return "; ".join("%s: %s" % (gate.get("id", "gate"), failure_detail({'stdout': gate.get('detail') or ''}, limit=1200))
                     for gate in failing)


def engine_repair(engine, job, ticket_index=None):
    """One bounded repair retry after a plain gate_failed Engine attempt.

    Mirrors the semantic_gate_repair pattern already proven on the Map side
    (factory-ng-produce-build-plan.py): a gate_failed candidate compiled/ran
    and failed a specific behavior or build gate — a near-miss bug, not an
    evidence gap — so the repair carries the exact failing-gate text instead
    of regenerating evidence from scratch.
    """
    ticket = json.loads(json.dumps(engine))
    ticket["id"] = next_version(engine["id"], ticket_index)
    ticket["title"] = "Repair after gate failure: " + engine["title"]
    ticket["supersedes"] = engine["id"]
    ticket["parents"] = list(dict.fromkeys(engine.get("parents", []) + [engine["id"]]))
    ticket["source"] = {"repository": str(SOURCE), "revision": source_revision(), "clean": True}
    ticket["production"] = dict(engine.get("production", {}))
    ticket["production"]["key"] = ticket["production"].get("key", engine["id"]) + ":gate-repair-v1"
    ticket["production"]["retry_reason"] = "semantic_gate_repair"
    detail = gate_failure_detail(job)
    receipt = job.get('integration_receipt') if job.get('state') == 'integration_failed' else job.get('receipt')
    if receipt:
        ticket["evidence"].append({
            "path": receipt,
            "fact": "The previous candidate compiled/ran and failed this exact gate: %s. Fix only this defect; do not restructure unrelated code or revisit already-passing behavior."
                    % (detail or "see receipt for the exact failing gate."),
        })
    observation = load_json(OPS / job.get('receipt', ''), {}) or {}
    execution = observation.get('execution', {})
    patch_name = execution.get('candidate_patch')
    if patch_name:
        patch_path = (OPS / patch_name).resolve()
        if (not patch_path.is_relative_to((OPS / 'docs/factory-ng/candidates').resolve())
                or not patch_path.is_file()
                or digest_file(patch_path) != execution.get('candidate_patch_sha256')):
            raise ValueError('retained candidate patch does not match its observation')
        patch_text = patch_path.read_text()
        ticket['evidence'].append({
            'path': patch_name, 'sha256': execution['candidate_patch_sha256'],
            'fact': ('Historical candidate for review/reuse, NOT applied to the current source. '
                     'Verify every hunk and test against current source and the original semantic contract.\n' +
                     patch_text[:24000] + ('\n[remaining patch omitted]' if len(patch_text) > 24000 else '')),
        })
    ticket["execution"]["selection_reason"] = "One bounded gate-failure repair: the prior candidate was substantively close but failed a specific behavior or build gate."
    ticket["on_failure"] = "Retain the terminal receipt and continue independent discovery; do not request manual source transcription."
    return ticket


def engine_successor(engine, job, ticket_index=None):
    """Version one parked Engine observation with a refreshed, index-grounded evidence pack.

    Restricted to AMBIGUOUS parks by the caller: the autopsy showed ~60% of
    parks cite a missing evidence region rather than a genuine architecture
    mismatch, and the old blind NEED-continuation retry reused the same weak
    CORE_PATHS scan that caused the miss in the first place. This regenerates
    evidence through the indexed engine symbol table instead of only adding a
    continuation note, so the retry packet is actually different.
    """
    ticket = json.loads(json.dumps(engine))
    ticket["id"] = next_version(engine["id"], ticket_index)
    ticket["title"] = "Retry with index-grounded evidence: " + engine["title"]
    ticket["supersedes"] = engine["id"]
    ticket["parents"] = list(dict.fromkeys(engine.get("parents", []) + [engine["id"]]))
    ticket["source"] = {"repository": str(SOURCE), "revision": source_revision(), "clean": True}
    ticket["production"] = dict(engine.get("production", {}))
    ticket["production"]["key"] = ticket["production"].get("key", engine["id"]) + ":evidence-refresh-v1"
    capability_key = ticket["production"].get("key", "").split(":")[1] if str(
        ticket["production"].get("key", "")).startswith("capability:") else None
    with lookup_context({'KB_TICKET':ticket['id'],'KB_ATTEMPT':'successor-preparation'}):
        refreshed = (source_evidence({"key": capability_key, "specification": engine.get("capability", {})})
                     if capability_key else [])
    if refreshed:
        refreshed_paths = {item["path"] for item in refreshed}
        ticket["evidence"] = [item for item in ticket["evidence"]
                              if item.get("path") not in refreshed_paths] + refreshed
    receipt = job.get("receipt")
    if receipt:
        ticket["evidence"].append({"path": receipt,
                                   "fact": "The previous attempt parked AMBIGUOUS because its evidence pack omitted the real seam; this retry regenerates evidence from the indexed engine symbol table."})
    ticket["execution"]["selection_reason"] = "One index-grounded evidence retry after an AMBIGUOUS park caused by an incomplete evidence pack."
    ticket["on_failure"] = "Retain the terminal receipt and continue independent discovery; do not request manual source transcription."
    return ticket


def resumed_map(parent, engine, capability, ticket_index=None):
    old_measurement_path = next((item.get("path") for item in parent.get("evidence", [])
                                 if isinstance(item, dict) and str(item.get("path", "")).endswith(".json")), None)
    if not old_measurement_path:
        raise ValueError("blocked Map ticket has no JSON measurement evidence")
    measurement = load_json(OPS / old_measurement_path)
    if not isinstance(measurement, dict):
        raise ValueError("blocked Map measurement is unavailable")
    parser_path = SOURCE / "scripts/paragraph/reparse.py"
    sys.path.insert(0, str(parser_path.parent))
    import reparse  # noqa: E402

    shape = measurement.get("shape")
    history = map_repair_history(parent, ticket_index or {parent['id']: parent})
    if history['error']:
        raise ValueError(history['error'])
    recovery = history['obligation']
    current_members = []
    for member in measurement.get("members", []):
        name = member.get("name", "")
        shard = SOURCE / "backend/data/carddb" / ((name[:1] or "_").lower() + ".json")
        card = (load_json(shard, {}) or {}).get(name)
        if not isinstance(card, dict) or card.get('status') not in ('review', 'auto'):
            raise ValueError('pinned Map member is missing or not safely measurable: ' + name)
        if digest_bytes((card.get('text') or '').encode()) != member.get('text_sha256'):
            raise ValueError('pinned Map member text changed: ' + name)
        result = reparse.reparse_card(card)
        misses = result.get("misses", [])
        details = [detail for kind, detail in misses if kind == shape]
        if not misses and result.get('eligible', True):
            # These cards can already be auto despite an incorrect mapping.
            # Landing an Engine primitive does not prove the Map uses it.
            details = ['Revalidate the complete Oracle mapping against the integrated Engine capability; parser eligibility alone does not satisfy this recovery.']
        if not details:
            details = [detail for _, detail in misses] or ['card is not fully eligible']
        current_members.append({"name": name, "oracle_text": card.get("text") or "",
                                "text_sha256": digest_bytes((card.get("text") or "").encode()),
                                "all_miss_shapes": sorted({kind for kind, _ in misses}), "details": details})
        if measurement.get('multi_miss'):
            current_members[-1]['misses'] = [{'shape': kind, 'detail': detail} for kind, detail in misses]
    if not current_members:
        return None, None

    suffix = hashlib.sha256((parent["id"] + engine["id"] + source_revision()).encode()).hexdigest()[:10]
    measurement = dict(measurement)
    measurement["members"] = current_members
    measurement["member_count"] = len(current_members)
    if measurement.get('multi_miss'):
        measurement.setdefault('initial_miss_count', measurement['miss_count'])
        measurement.setdefault('initial_miss_shapes', measurement['shapes'])
        measurement['miss_count'] = sum(len(member['misses']) for member in current_members)
        measurement['shapes'] = sorted({kind for member in current_members for kind in member['all_miss_shapes']})
    measurement["source"] = {"repository": str(SOURCE), "revision": source_revision(),
                             "parser_sha256": digest_file(parser_path)}
    measurement["dependency"] = {"ticket": engine["id"], "capability": capability["key"]}
    measurement_path = "docs/factory-ng/measurements/dependency-resume-%s.json" % suffix

    ticket = json.loads(json.dumps(parent))
    ticket["id"] = next_version(parent["id"], ticket_index)
    ticket["title"] = "Resume after %s: %s" % (capability["key"], parent["title"])
    ticket["supersedes"] = parent["id"]
    ticket["parents"] = list(dict.fromkeys(parent.get("parents", []) + [engine["id"]]))
    ticket["source"] = {"repository": str(SOURCE), "revision": source_revision(), "clean": True}
    ticket["production"] = {"producer": "capability-dependencies",
                            "retry_reason": "dependency_resume",
                            "key": "%s:after:%s" % (parent.get("production", {}).get("key", parent["id"]),
                                                      engine["id"])}
    inherit_trial(parent, ticket)
    ticket.setdefault('required_behavior', []).append(
        'The Engine dependency landing is not proof this card is fixed. Verify the complete Oracle mapping against its runtime representation, including every ability, even if parsing is already eligible.')
    runtime_capability = {'key': capability['key'], 'specification': engine.get('capability', capability.get('specification', {}))}
    with lookup_context({'KB_TICKET':ticket['id'],'KB_ATTEMPT':'dependency-handoff'}):
        ticket['evidence'].extend(source_evidence(runtime_capability))
    if recovery:
        ticket['production']['integration_repair_generation'] = history['generation']
        ticket['production']['integration_recovery_parent'] = parent['id']
        ticket['production']['retry_reason'] = 'integration_conflict_repair'
        ticket.setdefault('required_behavior', []).append(
            'The Engine dependency landing is not proof this card is fixed. Map the exact Oracle behavior to the new runtime capability and retain meaningful complete-card regression tests, even if this card already reparses as eligible.')
    for item in ticket.get("evidence", []):
        if item.get("path") == old_measurement_path:
            item["path"] = measurement_path
            item["fact"] = "The blocked member was revalidated after its Engine dependency integrated."
        elif item.get("path") == "scripts/paragraph/reparse.py":
            item["sha256"] = digest_file(parser_path)
    ticket["evidence"].append({"ticket": engine["id"],
                               "fact": "The required atomic Engine capability passed full integration gates. Runtime contract: " + str(engine.get('capability', {}).get('required_behavior', 'See linked Engine TicketSpec.'))})
    ticket["on_failure"] = "Compile any new validated atomic dependency automatically; otherwise retain the terminal verdict and advance discovery."
    return ticket, measurement


def inherit_trial(parent, child):
    """Keep dependency and repair costs in the original controlled cohort."""
    for key in ('trial_id', 'trial_card'):
        if key in parent.get('production', {}):
            child.setdefault('production', {})[key] = parent['production'][key]
    if child.get('work_type') == 'map' and parent.get('production', {}).get('multi_miss'):
        for key in ('multi_miss', 'miss_count', 'miss_shapes'):
            if key in parent['production']:
                child.setdefault('production', {})[key] = parent['production'][key]
    if parent.get('execution', {}).get('profile_policy') == 'exact':
        for key in ('profile_policy', 'selected_profile', 'compatible_profiles'):
            child.setdefault('execution', {})[key] = parent['execution'][key]


def integration_repair_candidate(jobs, tickets, resolve_ticket=None):
    """Only existing failed Engine integrations; never create new demand."""
    superseded = {t.get('supersedes') for t in tickets.values()}
    chains = {}
    for key, ticket in tickets.items():
        chains.setdefault(key.rsplit('/v', 1)[0], []).append(ticket)
    for key, job in sorted(jobs.items(), key=lambda item: (item[1].get('updated_at', ''), item[0])):
        if (job.get('work_type') != 'engine' or job.get('state') != 'integration_failed'
                or job.get('outcome') not in ('full_gate_failed', 'candidate_conflict')
                or job.get('superseded_by') or key in superseded):
            continue
        engine = tickets.get(key)
        if not engine or engine_repair_used(chains.get(key.rsplit('/v', 1)[0], [])):
            continue
        # Bind the repair to the accepted candidate and its immutable failure.
        observation = load_json(OPS / job.get('receipt', ''), {}) or {}
        receipt = load_json(OPS / job.get('integration_receipt', ''), {}) or {}
        candidate = receipt.get('excluded_candidates', {}).get(key, {})
        ticket_path = OPS / job.get('ticket_path', '')
        if (not ticket_path.is_file() or observation.get('ticket', {}).get('sha256') != digest_file(ticket_path)
                or observation.get('ticket', {}).get('id') != key
                or not str(observation.get('outcome', '')).startswith('accepted')
                or candidate.get('status') != job.get('outcome')):
            continue
        if resolve_ticket is not None:
            engine = resolve_ticket(key)
        retry = engine_repair(engine, dict(job, ticket_id=key), tickets)
        retry['title'] = 'Repair after integration failure: ' + engine['title']
        retry['production']['key'] = engine['production']['key'] + ':integration-repair-v1'
        retry['production']['integration_repair_parent'] = key
        retry['execution']['selection_reason'] = 'One bounded repair of an existing failed integration; preserve all semantic gates.'
        retry['required_behavior'] = list(retry.get('required_behavior', [])) + [
            'Preserve all required gate selectors and semantic assertions. If a named test is missing, provide it with meaningful coverage of the original behavior; do not weaken or remove the gate.',
            'Review existing current-source behavior before implementing anything. The retained candidate is evidence, not proof of correctness on this revision.'
        ]
        return retry
    return None


def prepare_engine(kind, parent_id, receipt_path, capability, parent, engine, job,
                   tickets, integration_recovery_only):
    if kind == 'new':
        ticket = engine_ticket(parent_id, receipt_path, capability)
    elif kind == 'refresh':
        ticket = engine_successor(engine, job, tickets)
    else:
        ticket = engine_repair(engine, job, tickets)
    inherit_trial(parent, ticket)
    if integration_recovery_only:
        ticket['production']['integration_recovery_parent'] = parent_id
    if kind == 'integration':
        ticket['title'] = 'Repair after integration failure: ' + engine['title']
        ticket['production']['key'] = engine['production']['key'] + ':integration-repair-v1'
        ticket['production']['integration_repair_parent'] = engine['id']
        ticket['execution']['selection_reason'] = 'One bounded repair of a composed-gate failure or candidate conflict, preserving the original tests.'
    return {'ticket_id': ticket['id'], 'ticket': ticket}


def main(integration_recovery_only=False, completed_dependencies_only=False, engine_integration_repairs_only=False, trial_id=None):
    cache = ProducerCache(OPS / 'state/factory-ng-producer-cache.sqlite3')
    token = SCAN_CACHE.set(cache)
    revision_token = SCAN_REVISION.set(None)
    oracle_token = SCAN_ORACLE.set(None)
    try:
        return produce(integration_recovery_only, completed_dependencies_only, engine_integration_repairs_only, trial_id)
    finally:
        SCAN_CACHE.reset(token)
        SCAN_REVISION.reset(revision_token)
        SCAN_ORACLE.reset(oracle_token)
        cache.close()


def ticket_lifecycle(value):
    """The scan needs lineage, not every historical evidence/knowledge packet."""
    return {key: value[key] for key in ('id', 'work_type', 'parents', 'supersedes', 'production')
            if key in value} if isinstance(value, dict) else {}


def produce(integration_recovery_only=False, completed_dependencies_only=False, engine_integration_repairs_only=False, trial_id=None):
    if not source_clean():
        emit("source_dirty", reason="canonical source checkout is dirty")
        return
    SCAN_REVISION.set(source_revision())
    jobs = (load_json(JOBS, {}) or {}).get("jobs", {})
    # This producer used to scan and parse every TicketSpec several times for
    # every capability receipt. Once the queue reached ~1,000 tickets that
    # became quadratic and exceeded the controller's 90-second boundary.
    # Build the immutable lifecycle index once per producer pass instead.
    tickets_by_id = {}
    ticket_paths = {}
    versions_by_base = {}
    successors_by_parent = {}
    for path, item in SCAN_CACHE.get().files('dependency-ticket-lifecycle-v1', TICKETS, ticket_lifecycle):
        ticket_id = item.get("id")
        if not ticket_id:
            continue
        tickets_by_id[ticket_id] = item
        ticket_paths[ticket_id] = path
        found = re.fullmatch(r"(ticket:[a-z0-9][a-z0-9._-]*)/v(\d+)", ticket_id)
        if found:
            versions_by_base.setdefault(found.group(1), []).append(item)
        if item.get("supersedes"):
            successors_by_parent.setdefault(item["supersedes"], []).append(item)
    for chain in versions_by_base.values():
        chain.sort(key=lambda item: int(item["id"].rsplit("/v", 1)[1]))

    def full_ticket(ticket_id):
        item = load_json(ticket_paths[ticket_id], {}) or {}
        if ticket_lifecycle(item) != tickets_by_id[ticket_id]:
            raise ValueError('TicketSpec lineage changed during dependency scan: ' + ticket_id)
        return item

    if engine_integration_repairs_only:
        repair = integration_repair_candidate(jobs, tickets_by_id, full_ticket)
        if repair:
            emit('ready', ticket_id=repair['id'], ticket=repair)
        else:
            emit('no_integration_repair', reason='no eligible existing Engine integration failure')
        return

    candidate_errors = []

    def report(status, **extra):
        if candidate_errors:
            extra['candidate_errors'] = candidate_errors[:10]
            extra['candidate_error_count'] = len(candidate_errors)
        emit(status, **extra)

    reviewed_roots = attention_recovery.dependency_roots(jobs)

    def prepared_engine(candidate):
        kind, parent_id, receipt_path, capability, parent, engine, job = candidate
        payload = prepare_engine(kind, parent_id, receipt_path, capability,
            full_ticket(parent_id), full_ticket(engine['id']) if engine else None,
            job, tickets_by_id, integration_recovery_only)
        return attention_recovery.promote_dependency(payload, candidate[1], reviewed_roots)

    waiting = 0
    parent_satisfied_candidate = None
    # A brand-new Engine ticket is always the earliest actionable item for an
    # untouched receipt, so a saturated Engine lane would otherwise make this
    # producer offer the exact same lane-capped candidate every single pass,
    # never reaching an already-admissible Map resume (child_state ==
    # "completed", not lane-gated) that sits later in receipt order. Defer the
    # first Engine-type candidate instead of returning immediately, keep
    # scanning for a Map resume, and only fall back to the deferred Engine
    # candidate if the rest of the pass has nothing else actionable.
    lane_full = engine_lane_likely_full() and not integration_recovery_only and not trial_id
    deferred_engine_ready = None
    for receipt_number, receipt_path in enumerate(attention_recovery.prioritized_dependency_receipts(RUNS.glob("*.json"), OPS, jobs)):
        if receipt_number % 250 == 0:
            SCAN_CACHE.get().checkpoint()
        receipt = SCAN_CACHE.get().file('receipt-demand-v1', receipt_path, receipt_demand) or {}
        parent_id = receipt.get("ticket", {}).get("id")
        parent = tickets_by_id.get(parent_id)
        if not parent:
            continue
        if trial_id and parent.get('production', {}).get('trial_id') != trial_id:
            continue
        if integration_recovery_only and not (parent.get('production', {}).get('integration_repair_generation')
                                              or parent.get('production', {}).get('integration_recovery_parent')):
            continue
        if successors_by_parent.get(parent_id):
            continue
        if jobs.get(parent_id, {}).get("outcome") == "ground_truth_satisfied_after_dependency":
            # Already durably resolved by a prior parent_satisfied pass; the
            # controller marked this parent's job completed for exactly this
            # reason. Recomputing resumed_map() every scan would only ever
            # reach the same no-op verdict and keep resurfacing it as the
            # last-resort fallback, crowding out an actually useful report.
            continue
        capability = receipt.get('capability_demand')
        if receipt.get('outcome') == 'invalid_capability_demand':
            capability = recover_valid_capability(receipt)
        if not isinstance(capability, dict):
            continue
        engine_id, _encoded = engine_identity(capability)
        existing_engine = tickets_by_id.get(engine_id)
        if not existing_engine:
            if completed_dependencies_only:
                continue
            candidate = ('new', parent_id, receipt_path, capability, parent, None, None)
            if lane_full and parent_id not in reviewed_roots:
                deferred_engine_ready = deferred_engine_ready or candidate
                waiting += 1
                continue
            report('ready', **prepared_engine(candidate))
            return
        base = engine_id.rsplit("/v", 1)[0]
        chain = versions_by_base.get(base, [existing_engine])
        current_engine = chain[-1]
        current_job = jobs.get(current_engine["id"]) or {}
        child_state = current_job.get("state")
        if completed_dependencies_only and child_state != "completed":
            continue
        if (integration_recovery_only and child_state in ENGINE_ACTIVE_STATES
                and not current_job.get('priority_recovery_parent')
                and not current_engine.get('production', {}).get('integration_recovery_parent')):
            report('recovery_dependency', ticket_id=current_engine['id'], parent_id=parent_id)
            return
        resumed = [item for item in successors_by_parent.get(parent_id, [])
                   if current_engine["id"] in item.get("parents", [])]
        if resumed:
            continue
        if child_state == "completed":
            try:
                ticket, measurement = resumed_map(full_ticket(parent_id), full_ticket(current_engine['id']), capability, tickets_by_id)
            except (ValueError, TypeError, KeyError, RuntimeError, NameError, AttributeError) as exc:
                # A failed card measurement is not an exhausted frontier and
                # must not prevent independent later dependencies from running.
                # Preserve the obligation and report evidence; never reset its
                # attempt history or admit an unmeasured successor.
                candidate_errors.append({'ticket_id': parent_id, 'stage': 'resumed_map',
                    'source_revision': SCAN_REVISION.get(), 'error_type': type(exc).__name__,
                    'reason': str(exc)[:1000]})
                continue
            if ticket is None:
                # This is a durable no-op (nothing gets written), so it must
                # not `return` here: a stale one of these permanently blocked
                # every later receipt in the scan from ever being reached,
                # starving the AMBIGUOUS/gate-repair retry lanes even while
                # hundreds of them remained eligible. Defer it and keep
                # scanning; only fall back to reporting it if nothing else in
                # this pass is actually actionable.
                if parent_satisfied_candidate is None:
                    parent_satisfied_candidate = parent_id
                continue
            payload = dict(ticket_id=ticket["id"], ticket=ticket, measurement=measurement)
            report("ready", **attention_recovery.promote_dependency(payload, parent_id, reviewed_roots))
            return
        if child_state == "parked":
            already_refreshed = any(
                str(item.get("production", {}).get("key", "")).endswith(":evidence-refresh-v1")
                for item in chain
            )
            if not already_refreshed and receipt_verdict(current_job) == "AMBIGUOUS":
                candidate = ('refresh', parent_id, receipt_path, capability, parent, current_engine, current_job)
                if lane_full and parent_id not in reviewed_roots:
                    deferred_engine_ready = deferred_engine_ready or candidate
                    waiting += 1
                    continue
                report('ready', **prepared_engine(candidate))
                return
            waiting += 1
            continue
        if child_state == "failed":
            already_repaired = any(
                str(item.get("production", {}).get("key", "")).endswith(":gate-repair-v1")
                for item in chain
            )
            if not already_repaired and current_job.get("outcome") == "gate_failed":
                candidate = ('repair', parent_id, receipt_path, capability, parent, current_engine, current_job)
                if lane_full and parent_id not in reviewed_roots:
                    deferred_engine_ready = deferred_engine_ready or candidate
                    waiting += 1
                    continue
                report('ready', **prepared_engine(candidate))
                return
            waiting += 1
            continue
        if child_state == "integration_failed":
            already_repaired = engine_repair_used(chain)
            if not already_repaired and current_job.get('outcome') in ('full_gate_failed', 'candidate_conflict'):
                candidate = ('integration', parent_id, receipt_path, capability, parent, current_engine, current_job)
                if lane_full and parent_id not in reviewed_roots:
                    deferred_engine_ready = deferred_engine_ready or candidate
                    waiting += 1
                    continue
                report('ready', **prepared_engine(candidate))
                return
            waiting += 1
            continue
        waiting += 1
    if parent_satisfied_candidate is not None:
        report("parent_satisfied", ticket_id=parent_satisfied_candidate,
             reason="current ground truth no longer contains the blocked Map member")
        return
    if deferred_engine_ready is not None:
        # The lane estimate is conservative. Prepare at most one fallback;
        # the controller still makes the exact admission decision.
        report("ready", **prepared_engine(deferred_engine_ready))
        return
    if candidate_errors:
        report('producer_error', reason='%d blocked Map measurement(s) failed; independent candidates were scanned' % len(candidate_errors))
        return
    report("awaiting_dependency" if waiting else "no_capability_demand",
         reason=("validated dependencies already have durable lifecycle state" if waiting else
                 "no uncompiled validated capability verdict exists"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--integration-recovery-only', action='store_true',
                        help='bounded recovery reserve: only dependencies of failed-integration Map repairs')
    parser.add_argument('--completed-dependencies-only', action='store_true',
                        help='emit only Map verification after a completed Engine; never create or retry Engine work')
    parser.add_argument('--engine-integration-repairs-only', action='store_true',
                        help='emit only a bounded successor of an existing failed Engine integration')
    parser.add_argument('--trial-id', help='only dependencies of the explicitly bounded cohort')
    args = parser.parse_args()
    if sum((args.integration_recovery_only, args.completed_dependencies_only, args.engine_integration_repairs_only)) > 1:
        parser.error('select only one restricted producer mode')
    main(args.integration_recovery_only, args.completed_dependencies_only, args.engine_integration_repairs_only, args.trial_id)
