#!/usr/bin/env python3
"""Read-only status of the fourteen reviewed protocol failures."""
import collections
import datetime
import json
from pathlib import Path

review = Path(__file__).resolve().parent
ops = review.parents[3]
baseline = json.loads((review / 'baseline.json').read_text())
jobs = json.loads((ops / 'state/factory-ng-jobs.json').read_text())['jobs']
rows = []
for ticket_id in baseline:
    job = jobs[ticket_id]
    rows.append({'ticket_id': ticket_id, **{key: job.get(key) for key in
                 ('state', 'attempts', 'worker', 'model', 'outcome', 'receipt', 'integration_receipt', 'waiting_reason')},
                 'review_admitted': bool(job.get('attention_recovery'))})
print(json.dumps({'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'counts': dict(collections.Counter(row['state'] for row in rows)),
                  'jobs': rows}, indent=2))
