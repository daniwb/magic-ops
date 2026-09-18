#!/usr/bin/env python3
"""Finite, hash-bound successors for reviewed failures before semantic tests."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

from factory_ng_context import preparation_problems
from factory_ng_safety import source_problem
from factory_ng_producer_cache import ProducerCache

OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE
MANIFEST = OPS / 'docs/factory-ng/reviews/2026-09-16-four-hour-workers/harness-recovery.json'
ACTIVE = {'queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating'}


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def failure_kind(receipt):
    if receipt.get('outcome') != 'gate_failed':
        return None
    # A later formatting error must not hide an earlier behavioral failure.
    for stage in receipt.get('attempt_history', []):
        for gate in stage.get('gates', []):
            if (gate.get('outcome') == 'failed' and gate.get('id', '').startswith('ticket-gate-')
                    and not (gate['id'] == 'ticket-gate-0'
                             and gate.get('command', '').startswith('test -z "$(gofmt -l '))):
                return None
    failed = [g for g in receipt.get('gates', [])
              if g.get('outcome') == 'failed' and g.get('id') != 'initial-patch-apply']
    if len(failed) != 1:
        return None
    gate = failed[0]
    if gate.get('id') == 'ticket-gate-0' and gate.get('command', '').startswith('test -z "$(gofmt -l '):
        return 'formatting'
    if gate.get('id') == 'patch-apply' and any(text in gate.get('detail', '').lower()
            for text in ('search', 'malformed', 'duplicate', 'no edit blocks')):
        return 'patch_protocol'
    return None


def successor(original, item, revision, batch, tickets):
    ticket = copy.deepcopy(original)
    base = original['id'].rsplit('/v', 1)[0]
    versions = [int(m[1]) for key in tickets if (m := re.fullmatch(re.escape(base) + r'/v(\d+)', key))]
    ticket['id'] = base + '/v' + str(max(versions or [0]) + 1)
    ticket['supersedes'] = original['id']
    ticket['parents'] = list(dict.fromkeys(original.get('parents', []) + [original['id']]))
    ticket['title'] = 'Recover after harness correction: ' + original['title']
    ticket['source'] = dict(original['source'], revision=revision, clean=True)
    ticket.setdefault('production', {}).update(harness_recovery_batch=batch,
        harness_recovery_parent=original['id'], harness_recovery_kind=item['kind'])
    ticket['production']['key'] = original.get('production', {}).get('key', original['id']) + ':harness-recovery-sep16'
    ticket.setdefault('evidence', []).append({'path': item['receipt'], 'sha256': item['receipt_sha256'],
        'fact': 'Operator-reviewed failure before semantic verification (%s). The harness now provides exact rejected SEARCH context, canonical delimiter handling, and scoped deterministic gofmt. Historical code is not current source authority.' % item['kind']})
    ticket.setdefault('execution', {})['selection_reason'] = (
        'One finite reviewed successor after a demonstrated harness correction. Read current source; '
        'preserve the original capability, scope, required behavior and every gate.')
    execution = ticket['execution']
    compatible = execution.get('compatible_profiles', [])
    if execution.get('profile_policy') != 'exact' and any(p in compatible for p in
            ('codex-constrained@1.0.0', 'codex-constrained@1.1.0')):
        # User requested sustained Codex operation. Keep existing compatible
        # fallback profiles, but fill the four requested leases first.
        execution['selected_profile'] = 'codex-constrained@1.1.0'
        execution['compatible_profiles'] = list(dict.fromkeys(['codex-constrained@1.1.0', *compatible]))
    return ticket


def candidate(ops, manifest, jobs, tickets, revision, validate=None):
    batch = manifest['batch']
    if manifest.get('schema') != 'factory.reviewed-harness-recovery/v1':
        raise ValueError('invalid harness recovery manifest')
    if sum(j.get('state') in ACTIVE and not j.get('superseded_by')
           and j.get('production', {}).get('harness_recovery_batch') == batch
           for j in jobs.values()) >= min(24, manifest['max_active']):
        return {'status': 'reviewed_harness_reserve_full'}
    superseded = {t.get('supersedes') for t in tickets.values()}
    skipped = []
    for item in manifest['tickets']:
        key = item['ticket_id']; job = jobs.get(key, {})
        if key in superseded or job.get('superseded_by') or job.get('state') != 'failed':
            continue
        if job.get('receipt') != item['receipt'] or job.get('attempts') != item['attempts']:
            continue
        path = ops / job['ticket_path']; receipt = ops / item['receipt']
        if digest(path) != item['ticket_sha256'] or digest(receipt) != item['receipt_sha256']:
            raise ValueError('reviewed harness failure changed after audit: ' + key)
        original = json.loads(path.read_text())
        if (original.get('work_type') != 'engine' or original.get('production', {}).get('harness_recovery_batch')
                or failure_kind(json.loads(receipt.read_text())) != item['kind']):
            raise ValueError('reviewed failure is not an eligible pre-semantic Engine failure')
        if not any(parent.startswith('ticket:map.') and jobs.get(parent, {}).get('state') == 'blocked'
                   and not jobs.get(parent, {}).get('superseded_by') for parent in original.get('parents', [])):
            continue
        ticket = successor(original, item, revision, batch, tickets)
        if validate:
            reason = validate(ticket)
            if reason:
                skipped.append({'ticket_id': key, 'reason': reason})
                continue
        return {'status': 'ready', 'ticket_id': ticket['id'], 'ticket': ticket}
    return {'status': 'no_reviewed_harness_remaining', 'skipped': skipped}


def main():
    if not MANIFEST.exists():
        print(json.dumps({'status': 'reviewed_harness_manifest_pending'})); return
    problem = source_problem(SOURCE)
    if problem:
        print(json.dumps({'status': 'source_unavailable', 'reason': problem})); return
    revision = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    spec = importlib.util.spec_from_file_location('capability_contract', OPS / 'scripts/capability-contract.py')
    contract = importlib.util.module_from_spec(spec); spec.loader.exec_module(contract)
    records = contract.oracle_records(str(SOURCE))
    def validate(ticket):
        try:
            contract.validate_oracle({'specification': ticket['capability']}, str(SOURCE), records=records)
        except (KeyError, ValueError) as exc:
            return 'current Oracle validation: ' + str(exc)
        problems = preparation_problems(ticket, SOURCE)
        return str(problems) if problems else None
    # Only lineage/version metadata is needed for other tickets. The existing
    # disposable cache stats every file (including inode/ctime) before reuse;
    # the reviewed original itself is still reread and hash-checked below.
    cache = ProducerCache(OPS / 'state/factory-ng-harness-recovery-cache.sqlite3')
    try:
        rows = cache.files('harness-ticket-lineage-v1', OPS / 'docs/factory-ng/tickets',
                           lambda t: {k: t[k] for k in ('id', 'supersedes') if k in t})
        tickets = {t['id']: t for _, t in rows if t.get('id')}
    finally:
        cache.close()
    result = candidate(OPS, json.loads(MANIFEST.read_text()),
                       json.loads((OPS / 'state/factory-ng-jobs.json').read_text())['jobs'],
                       tickets, revision, validate)
    if source_problem(SOURCE) or subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() != revision:
        result = {'status': 'source_unavailable', 'reason': 'source changed during reviewed production'}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
