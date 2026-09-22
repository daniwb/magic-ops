"""Read-only, bounded observation of actual Codex leases and durable progress."""
import collections
import datetime as dt
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
window = json.loads((HERE / 'window.json').read_text())
end = dt.datetime.fromisoformat(window['end'].replace('Z', '+00:00')).timestamp()
workers = window['workers']

def alive(pid):
    try:
        return int(pid or 0) > 0 and Path('/proc/%s/stat' % pid).read_text().split()[2] != 'Z'
    except (OSError, IndexError, TypeError, ValueError):
        return False

while True:
    now = time.time()
    end = dt.datetime.fromisoformat(json.loads((HERE / 'window.json').read_text())['end'].replace('Z', '+00:00')).timestamp()
    try:
        jobs = json.loads((ROOT / 'state/factory-ng-jobs.json').read_text())['jobs']
        live = {k: j for k, j in jobs.items() if not j.get('superseded_by')}
        leases = {w: [{'ticket': k, 'pid': j.get('pid'), 'alive': alive(j.get('pid')),
                       'repair': bool(j.get('verification_resume')), 'model': j.get('model')}
                      for k, j in live.items() if j.get('worker') == w
                      and j.get('state') == 'working' and not j.get('verification_batch')]
                  for w in workers}
        row = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'leases': leases,
               'occupied': sum(any(j['alive'] for j in leases[w]) for w in workers),
               'states': dict(collections.Counter(j.get('state') for j in live.values())),
               'batch_verification': sum(j.get('state') == 'working' and bool(j.get('verification_batch')) for j in live.values())}
        runtime = json.loads((ROOT / 'state/factory-ng-runtime.json').read_text())
        row['controller'] = {k: runtime.get(k) for k in ('state', 'phase', 'updated_at', 'queue')}
    except Exception as exc:
        row = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'error': str(exc)}
    with (HERE / 'occupancy.jsonl').open('a') as out:
        out.write(json.dumps(row, sort_keys=True) + '\n')
        out.flush()
        os.fsync(out.fileno())
    if now >= end:
        break
    time.sleep(min(30, end - now))
