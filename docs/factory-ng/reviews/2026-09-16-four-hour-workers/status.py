"""Summarize the live goal without counting model-free verification as Codex work."""
import collections
import datetime as dt
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
window = json.loads((HERE / 'window.json').read_text())
jobs = json.loads((ROOT / 'state/factory-ng-jobs.json').read_text())['jobs']
live = {k: j for k, j in jobs.items() if not j.get('superseded_by')}
rows = [json.loads(line) for line in (HERE / 'occupancy.jsonl').read_text().splitlines()]
recent = rows[-20:]
model = {}
for worker in window['workers']:
    model[worker] = []
    for key, job in live.items():
        if job.get('worker') != worker or job.get('state') != 'working' or job.get('verification_batch'):
            continue
        try:
            alive = Path('/proc/%s/stat' % job.get('pid')).read_text().split()[2] != 'Z'
        except (OSError, IndexError):
            alive = False
        model[worker].append({'ticket': key, 'alive': alive, 'repair': bool(job.get('verification_resume'))})
start = window.get('stability_start', window['start'])
stable = [r for r in rows if r['at'] >= start.replace('Z', '+00:00') and 'occupied' in r]
result = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'window': window,
          'states': dict(collections.Counter(j.get('state') for j in live.values())),
          'model_leases': model,
          'recent_occupancy': [{'at': r['at'], 'occupied': r.get('occupied')} for r in recent],
          'window_sample_counts': dict(collections.Counter(r['occupied'] for r in stable)),
          'net_completed_since_request': sum(j.get('state') == 'completed' for j in live.values()) - window['baseline_states']['completed'],
          'queued': [k for k, j in live.items() if j.get('state') == 'queued']}
print(json.dumps(result, indent=2))
