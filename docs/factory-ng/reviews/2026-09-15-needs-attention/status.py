#!/usr/bin/env python3
"""Read-only status of every ticket in the needs-attention baseline."""
import collections
import datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPS = HERE.parents[3]
jobs = json.loads((OPS / 'state/factory-ng-jobs.json').read_text())['jobs']
baseline = json.loads((HERE / 'baseline.json').read_text())
rows = []
for original in baseline:
    key = original['ticket_id']
    job = jobs.get(key, {})
    reviewed = bool(job.get('attention_recovery'))
    visited = set()
    while job.get('superseded_by') and key not in visited:
        visited.add(key)
        key = job['superseded_by']
        job = jobs.get(key, {})
        reviewed = reviewed or bool(job.get('attention_recovery'))
    rows.append(dict(original=original['ticket_id'], current=key, state=job.get('state'),
                     outcome=job.get('outcome'), attempts=job.get('attempts'),
                     recovered=reviewed,
                     receipt=job.get('integration_receipt') or job.get('receipt'),
                     reason=job.get('waiting_reason') or job.get('reason')))
print(json.dumps({'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'states': dict(collections.Counter(r['state'] for r in rows)),
                  'reviewed_attempt_admitted': sum(r['recovered'] for r in rows),
                  'tickets': rows}, indent=2))
