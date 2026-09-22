#!/usr/bin/env python3
"""Bounded five-card cohort producer and receipt report; no model or push authority."""
import argparse
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE
DIRECTORY = OPS / 'docs/factory-ng/reviews/2026-09-08-throughput/staged-five-card-trial'
MANIFEST = DIRECTORY / 'manifest.json'
PROFILE = 'claude-staged@1.0.0'
ACTIVE = {'queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating'}
COUNTERS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens')


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def sha(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def index():
    return {t['id']: t for p in (OPS / 'docs/factory-ng/tickets').glob('*.json')
            if isinstance(t := read(p), dict) and 'id' in t}


def trial_execution(ticket):
    ticket['execution'].update(selected_profile=PROFILE, compatible_profiles=[PROFILE],
                               profile_policy='exact', selection_reason='Controlled five-card staged cohort; no automatic adapter fallback.')


def prepare_map(card, manifest, tickets):
    spec = importlib.util.spec_from_file_location('trial_dependency', OPS / 'scripts/factory-ng-produce-capability-dependency.py')
    dep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dep)
    parent = tickets[card['root']]
    # Both completed dependencies and audited reuse get a fresh measurement.
    # For reuse, replace the generic completed-dependency assertion below.
    dependency = tickets[card['dependency']]
    capability = {'key': card['capability'], 'specification': dependency['capability']}
    ticket, measurement = dep.resumed_map(parent, dependency, capability, tickets)
    ticket['title'] = 'Staged card trial: ' + card['name']
    ticket['production'].update(producer='staged-five-card-trial', trial_id=manifest['id'],
                                trial_card=card['name'], key=manifest['id'] + ':map:' + card['slug'])
    trial_execution(ticket)
    if card['dependency_status'] != 'completed':
        ticket['evidence'] = [e for e in ticket['evidence'] if e.get('ticket') != dependency['id']]
        ticket['evidence'].append({'path': 'docs/factory-ng/reviews/2026-09-08-throughput/fts5-miss-audit.md',
                                  'fact': 'This historical dependency did NOT complete. The audit found reusable runtime behavior. Verify that behavior; do not assume the failed/parked patch is present. ' + card['reuse']})
        measurement['dependency']['status'] = 'audited_reuse_not_completed'
    ticket['required_behavior'].extend(['Complete-card acceptance obligation (later runtime verification is separate): ' + item
                                        for item in card['acceptance']])
    measurement_path = next(e['path'] for e in ticket['evidence'] if str(e.get('path', '')).endswith('.json'))
    old_path = next(e['path'] for e in parent['evidence'] if str(e.get('path', '')).endswith('.json'))
    ticket['gates'] = [g.replace(old_path, measurement_path) for g in ticket['gates']]
    return {'status': 'ready', 'ticket_id': ticket['id'], 'ticket': ticket, 'measurement': measurement}


def verification(card, manifest, parent):
    revision = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    skill = OPS / 'docs/factory-ng/skills/v1/verify-card-behavior/SKILL.md'
    name = 'TestShape_StagedTrial_' + card['slug'].replace('-', '_')
    test_file = 'backend/cards/shape_staged_trial_' + card['slug'].replace('-', '_') + '_test.go'
    ticket_id = 'ticket:engine.staged-trial-verify-' + card['slug'] + '/v1'
    required = ['Write a test-only full-card proof for ' + card['name'] + '. Load the real corpus card, freshly reparse it with Python reparse_card, merge parser output into CardDefinition, call ToGameCard, then exercise public game actions and resolution. No handcrafted replacement abilities, skipped cases or weakened expectations.',
                'Add the exact named test ' + name + ' in ' + test_file + '.',
                *card['acceptance']]
    evidence = [{'path': str(MANIFEST.relative_to(OPS)), 'fact': 'Frozen Oracle text and complete-card checklist; all cases are required.'},
                {'path': 'backend/cards/converter.go', 'anchor': '1-100', 'fact': 'CardDefinition.ToGameCard is the real converter entry point.'},
                {'path': 'backend/cards/types.go', 'anchor': '216-300', 'fact': 'JSON CardDefinition includes the fresh abilities and keywords.'},
                {'path': str(skill.relative_to(OPS)), 'fact': skill.read_text()}]
    for path in card['fixtures']:
        file = SOURCE / path
        if file.is_file():
            evidence.append({'path': path, 'anchor': '1-180', 'sha256': sha(file),
                             'fact': 'Existing API and game setup example; primitive tests do not replace the complete-card checklist.'})
    ticket = {'schema': 'factory.ticket-spec/v1', 'id': ticket_id, 'title': 'Verify complete card: ' + card['name'],
              'work_type': 'engine', 'lifecycle': 'ready_for_observation', 'parents': [parent['id']],
              'production': {'producer': 'staged-five-card-trial', 'key': manifest['id'] + ':verify:' + card['slug'],
                             'trial_id': manifest['id'], 'trial_card': card['name'], 'trial_phase': 'verification'},
              'source': {'repository': str(SOURCE), 'revision': revision, 'clean': True},
              'skill': {'name': 'verify-card-behavior', 'path': str(skill.relative_to(OPS)), 'sha256': sha(skill)},
              'scope': {'allowed_paths': [test_file], 'forbidden_paths': ['backend/data/', 'scripts/paragraph/']},
              'evidence': evidence, 'required_behavior': required,
              'capability': {'required_behavior': '\n'.join(required), 'source_misses': [{'card': card['name'], 'paragraph': card['oracle_text']}]},
              'gates': ["cd backend && go test ./cards -run '^" + name + "$' -count=1", 'cd backend && go test ./game ./cards',
                        'test -z "$(gofmt -l ' + test_file + ')"', 'git diff --check'],
              'execution': copy.deepcopy(parent['execution']),
              'on_failure': 'Retain the behavioral failure and its token cost. A parser-success or accepted candidate is not a completed card.'}
    ticket['execution'].pop('parser_probes', None)
    trial_execution(ticket)
    return {'status': 'ready', 'ticket_id': ticket_id, 'ticket': ticket}


def receipt_rows(tickets):
    rows = []
    for path in (OPS / 'docs/factory-ng/runs').glob('*.json'):
        r = read(path, {})
        if not isinstance(r, dict) or r.get('schema') != 'factory.observation-receipt/v1':
            continue
        ticket_id = r.get('ticket', {}).get('id')
        if ticket_id not in tickets:
            continue
        model = r.get('model', {})
        telemetry = model.get('telemetry', {})
        values = [telemetry.get(k) for k in COUNTERS]
        profile = model.get('profile', '')
        raw = sum(values) if profile.startswith('claude-') and all(type(v) is int for v in values) else None
        rows.append({'ticket_id': ticket_id, 'receipt': str(path.relative_to(OPS)), 'profile': profile,
                     'outcome': r.get('outcome'), 'raw_claude_tokens': raw,
                     'model_elapsed_ms': telemetry.get('elapsed_ms'),
                     'candidate_patch': r.get('execution', {}).get('candidate_patch')})
        patch = r.get('execution', {}).get('candidate_patch')
        rows[-1]['changed_files'] = []
        if patch and (OPS / patch).is_file():
            lines = (OPS / patch).read_text().splitlines()
            rows[-1]['changed_files'] = sorted({line.split(' b/', 1)[1] for line in lines
                                                if line.startswith('diff --git a/') and ' b/' in line})
    return rows


def verification_context_successor(ticket, job, tickets):
    """Use the existing single Engine evidence refresh for a proven cohort gap."""
    if (ticket.get('production', {}).get('trial_phase') != 'verification'
            or job.get('state') not in ('parked', 'failed', 'queued')
            or job.get('outcome') not in ('parked', 'infrastructure_failed_model_protocol')
            or job.get('superseded_by') or not job.get('receipt')):
        return None
    chain = [t for t in tickets.values() if t['id'].rsplit('/v', 1)[0] == ticket['id'].rsplit('/v', 1)[0]]
    if any(':evidence-refresh-v1' in t.get('production', {}).get('key', '') for t in chain):
        return None
    receipt = read(OPS / job['receipt'], {})
    from factory_ng_context_recovery import context_repair_requests
    requests = context_repair_requests(OPS, receipt, ticket, {'ancestors': [t['id'] for t in chain]}, tickets)
    if (receipt.get('ticket', {}).get('id') != ticket['id']
            or receipt.get('ticket', {}).get('sha256') != sha(OPS / job['ticket_path'])
            or receipt.get('model', {}).get('profile') != PROFILE
            or not (receipt.get('evidence_failure') or requests)
            or receipt.get('execution', {}).get('candidate_patch')):
        return None
    spec = importlib.util.spec_from_file_location('trial_evidence_refresh', OPS / 'scripts/factory-ng-produce-capability-dependency.py')
    dep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dep)
    successor = dep.engine_successor(ticket, job)
    successor['execution']['context_requests'] = [
        'scripts/paragraph/reparse.py: load_card reparse_card',
        'backend/cards/types.go: CardDefinition',
        'backend/cards/shape_tap_and_put_counter_test.go',
    ]
    successor['production']['verification_context_version'] = 'pinned-fixtures-v1'
    return successor


def report(manifest, tickets, jobs):
    rows = receipt_rows(tickets)
    cards = []
    for card in manifest['cards']:
        ids = {k for k, t in tickets.items() if t.get('production', {}).get('trial_id') == manifest['id']
               and t['production'].get('trial_card') == card['name']}
        attempts = [r for r in rows if r['ticket_id'] in ids]
        baseline = [r for r in rows if r['ticket_id'] in card['baseline_tickets']]
        verifiers = [k for k in ids if tickets[k].get('production', {}).get('trial_phase') == 'verification']
        verified = any(jobs.get(k, {}).get('state') == 'completed' and
                       jobs.get(k, {}).get('integration_receipt') for k in verifiers)
        cards.append({'name': card['name'], 'complete': bool(verified),
                      'trial_known_raw_claude_tokens': sum(r['raw_claude_tokens'] or 0 for r in attempts),
                      'trial_unknown_or_non_claude_attempts': sum(r['raw_claude_tokens'] is None for r in attempts),
                      'historical_known_raw_claude_tokens': sum(r['raw_claude_tokens'] or 0 for r in baseline),
                      'historical_unknown_or_non_claude_attempts': sum(r['raw_claude_tokens'] is None for r in baseline),
                      'trial_known_model_elapsed_ms': sum(r['model_elapsed_ms'] for r in attempts if type(r['model_elapsed_ms']) is int),
                      'trial_changed_files': sorted({f for r in attempts for f in r['changed_files']}),
                      'trial_engine_tickets': sorted(k for k in ids if tickets[k].get('work_type') == 'engine'),
                      'exceeds_500k': sum(r['raw_claude_tokens'] or 0 for r in attempts) > 500000,
                      'jobs': {k: {f: jobs.get(k, {}).get(f) for f in ('state', 'outcome', 'waiting_reason', 'repair_blocker', 'superseded_by')} for k in sorted(ids)},
                      'attempts': attempts, 'historical_attempts': baseline})
    result = {'trial_id': manifest['id'], 'updated_at': datetime.now(timezone.utc).isoformat(),
              'cards_complete': sum(c['complete'] for c in cards), 'cards': cards,
              'accounting': 'Raw Claude input + output + cache read + cache write; not quota or dollars. Historical costs are separate and shared dependencies may appear for multiple cards. Unknown counters are never zero-cost proof.',
              'decision': 'Ordinary Claude staged-first routing is user-authorized. This unassisted cohort still needs complete-card evidence; no token target is yet proven.'}
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=DIRECTORY, prefix='status-', suffix='.tmp', delete=False) as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
        temporary = Path(stream.name)
    temporary.replace(DIRECTORY / 'status.json')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', action='store_true')
    args = parser.parse_args()
    manifest = read(MANIFEST)
    if not manifest or not manifest.get('enabled'):
        print(json.dumps({'status': 'disabled'})); return
    tickets = index()
    jobs = read(OPS / 'state/factory-ng-jobs.json', {}).get('jobs', {})
    status = report(manifest, tickets, jobs)
    if args.report:
        print(json.dumps(status, indent=2)); return
    from factory_ng_safety import source_problem
    problem = source_problem(SOURCE)
    if problem:
        print(json.dumps({'status': 'source_unavailable', 'reason': problem})); return
    active = [k for k,t in tickets.items() if t.get('production', {}).get('trial_id') == manifest['id']
              and not jobs.get(k, {}).get('superseded_by') and jobs.get(k, {}).get('state', 'queued') in ACTIVE]
    if len(active) >= 2:
        print(json.dumps({'status': 'trial_reserve_full'})); return
    for ticket in tickets.values():
        if ticket.get('production', {}).get('trial_id') != manifest['id']:
            continue
        successor = verification_context_successor(ticket, jobs.get(ticket['id'], {}), tickets)
        if successor:
            print(json.dumps({'status': 'ready', 'ticket_id': successor['id'], 'ticket': successor})); return
    for card in manifest['cards']:
        cohort = [t for t in tickets.values() if t.get('production', {}).get('trial_id') == manifest['id']
                  and t['production'].get('trial_card') == card['name']]
        if not cohort:
            # Never branch an existing live successor or reopen completed work.
            if any(t.get('supersedes') == card['root'] for t in tickets.values()):
                continue
            if jobs.get(card['root'], {}).get('state') != 'blocked':
                continue
            print(json.dumps(prepare_map(card, manifest, tickets))); return
        maps = [t for t in cohort if t['work_type'] == 'map' and not jobs.get(t['id'], {}).get('superseded_by')]
        for parent in maps:
            if jobs.get(parent['id'], {}).get('state') == 'completed' and not any(t.get('production', {}).get('trial_phase') == 'verification' for t in cohort):
                print(json.dumps(verification(card, manifest, parent))); return
    # Failed trial resumes need the same bounded repair path as ordinary
    # integration obligations, without waiting behind unrelated old repairs.
    spec = importlib.util.spec_from_file_location('trial_repair', OPS / 'scripts/factory-ng-produce-build-plan.py')
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)
    sys.path.insert(0, str(SOURCE / 'scripts/paragraph'))
    import reparse
    candidate = repair.integration_repair_candidate(SOURCE, OPS / 'docs/factory-ng/tickets',
                                                    OPS / 'state/factory-ng-jobs.json', reparse,
                                                    trial_id=manifest['id'])
    if candidate:
        print(json.dumps({'status': 'ready', 'ticket_id': candidate['id'], 'ticket': candidate})); return
    # A bounded trial dependency must not sit behind the historical Engine
    # backlog. This mode can inspect only this cohort's Map receipts, and
    # inherits the same exact adapter restriction and existing repair limits.
    produced = subprocess.run(['python3', str(OPS / 'scripts/factory-ng-produce-capability-dependency.py'),
                               '--trial-id', manifest['id']], capture_output=True, text=True, timeout=120)
    if produced.returncode:
        raise RuntimeError(produced.stderr[-1000:])
    print(produced.stdout)


if __name__ == '__main__':
    main()
