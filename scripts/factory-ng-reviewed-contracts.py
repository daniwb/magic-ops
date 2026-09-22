#!/usr/bin/env python3
"""Admit the finite operator-reviewed September 9 contract corrections."""
import hashlib
import json
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
MANIFEST = OPS / 'docs/factory-ng/reviews/2026-09-09-capacity/contract-successors.json'
ACTIVE = {'queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating'}


def read(path):
    return json.loads(path.read_text())


def candidate(ops, manifest, jobs, tickets):
    batch = manifest['batch']
    if sum(j.get('state') in ACTIVE and not j.get('superseded_by')
           for key, j in jobs.items()
           if tickets.get(key, {}).get('production', {}).get('contract_correction_batch') == batch) >= manifest['max_active']:
        return {'status': 'reviewed_contract_reserve_full'}
    for item in manifest['tickets']:
        if any(t.get('supersedes') == item['original'] for t in tickets.values()):
            continue
        job = jobs.get(item['original'], {})
        if job.get('state') not in ('parked', 'failed') or job.get('superseded_by'):
            continue
        old_bytes = (ops / job['ticket_path']).read_bytes()
        new_bytes = (ops / item['ticket_path']).read_bytes()
        if any('sha256:' + hashlib.sha256(raw).hexdigest() != expected for raw, expected in (
                (old_bytes, item['original_sha256']), (new_bytes, item['ticket_sha256']))):
            raise ValueError('Reviewed contract changed after its audit')
        ticket = json.loads(new_bytes)
        if ticket['id'] in tickets:
            continue
        return {'status': 'ready', 'ticket_id': ticket['id'], 'ticket': ticket}
    return {'status': 'no_reviewed_contract_remaining'}


def main():
    if not MANIFEST.exists():
        print(json.dumps({'status': 'reviewed_contract_manifest_pending'})); return
    tickets = {t['id']: t for p in (OPS / 'docs/factory-ng/tickets').glob('*.json')
               if (t := read(p)).get('id')}
    print(json.dumps(candidate(OPS, read(MANIFEST), read(OPS / 'state/factory-ng-jobs.json')['jobs'], tickets)))


if __name__ == '__main__':
    main()
