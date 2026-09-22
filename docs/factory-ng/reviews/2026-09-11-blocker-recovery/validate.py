import importlib.util,json,sys,time
from pathlib import Path
ops=Path('/opt/development/magic-ops');sys.path.insert(0,str(ops/'scripts'))
spec=importlib.util.spec_from_file_location('runner',ops/'scripts/factory-ng-run-engine-ticket.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
out=ops/'docs/factory-ng/reviews/2026-09-11-blocker-recovery';r=Path((out/'clone.txt').read_text().strip());ticket=json.loads((out/'ticket.json').read_text());gates=[]
print('candidate validation started',flush=True)
for index,command in enumerate(ticket['gates']):
 print('gate',index,command,flush=True);result=runner.ticket_gate(command,r,ticket)
 (out/('gate-%d-output.json'%index)).write_text(json.dumps(result,indent=2)+'\n')
 g={'id':'ticket-gate-%d'%index,'command':command,'outcome':'passed' if result['exit_code']==0 else 'failed','elapsed_ms':result['elapsed_ms'],'detail':runner.failure_detail(result)};gates.append(g);(out/'gates.json').write_text(json.dumps(gates,indent=2)+'\n');print(g['outcome'],g['elapsed_ms'],flush=True)
 if result['exit_code']:
  print(g['detail'],flush=True);sys.exit(1)
print('all candidate gates passed',flush=True)
