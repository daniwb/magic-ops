import json,subprocess,time
from pathlib import Path
ops=Path('/opt/development/magic-ops');out=ops/'docs/factory-ng/reviews/2026-09-09-conflict-recovery'
selection=json.loads((out/'integration-selection.json').read_text())['receipts']
size=json.loads((ops/'config/factory-ng-policy.json').read_text())['integration'].get('wave_size',8)
for n,start in enumerate(range(0,len(selection),size),1):
 receipts=selection[start:start+size]
 # Do not race an automatically admitted successor.
 jobs=json.loads((ops/'state/factory-ng-jobs.json').read_text())['jobs']
 receipts=[r for r in receipts if not jobs[json.loads((ops/r).read_text())['ticket']['id']].get('superseded_by')]
 if not receipts:continue
 cmd=['python3','scripts/factory-ng-integrate.py','--reviewed-resolutions',str(out/'selected/resolutions.json')]
 for r in receipts:cmd+=['--receipt',r]
 while True:
  print('Starting reviewed wave',n,'candidates',len(receipts),flush=True)
  result=subprocess.run(cmd,cwd=ops,capture_output=True,text=True)
  if result.returncode!=75:break
  print('Existing integration owns lock; waiting 30 seconds.',flush=True);time.sleep(30)
 (out/('wave-%d-output.json'%n)).write_text(result.stdout)
 (out/('wave-%d-stderr.log'%n)).write_text(result.stderr)
 print('Wave',n,'exit',result.returncode,result.stdout[:1200],flush=True)
 if result.returncode!=0:break
