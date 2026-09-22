"""Run reviewed conflict/regression repairs and exact host-path failures through all gates."""
import json
import os
from pathlib import Path
import subprocess
import sys

review = Path(__file__).resolve().parent
ops = review.parents[3]
jobs = json.loads((ops / 'state/factory-ng-jobs.json').read_text())['jobs']
manifest = review / 'merge-resolutions.json'
resolutions = json.loads(manifest.read_text())['resolutions']
selected = []
for ticket in resolutions:
    if jobs[ticket]['state'] != 'completed':
        selected.append(jobs[ticket]['receipt'])
for job in jobs.values():
    if job.get('state') != 'integration_failed' or job.get('superseded_by'):
        continue
    receipt = json.loads((ops / job['integration_receipt']).read_text())
    if any('/usr/local/go/bin/go: No such file or directory' in gate.get('detail', '')
           for gate in receipt.get('gates', [])):
        if job['receipt'] not in selected:
            selected.append(job['receipt'])
assert selected
(review / 'wave-inputs.json').write_text(json.dumps(selected, indent=2) + '\n')
command = [sys.executable, str(ops / 'scripts/factory-ng-integrate.py'),
           '--reviewed-resolutions', str(manifest)]
for receipt in selected:
    command.extend(['--receipt', str(ops / receipt)])
env = dict(os.environ)
env['PATH'] = str(ops.parent.parent / 'toolchain/go/bin') + ':' + env.get('PATH', '')
env['PYTHONPATH'] = str(ops.parent.parent / 'pydeps') + ':' + env.get('PYTHONPATH', '')
env['FACTORY_NG_SOURCE'] = str(ops.parent / 'test/openmagic')
env['GO_CACHE_OPS_ROOT'] = str(ops)
env['GO_CACHE_ROOT'] = str(ops.parent / '.gocache-magic')
print('Running full reviewed integration for %d accepted observations' % len(selected), flush=True)
with (review / 'integration-result.json').open('w') as output, (review / 'integration.log').open('w') as log:
    result = subprocess.run(command, cwd=ops, env=env, stdout=output, stderr=log)
print((review / 'integration-result.json').read_text())
raise SystemExit(result.returncode)
