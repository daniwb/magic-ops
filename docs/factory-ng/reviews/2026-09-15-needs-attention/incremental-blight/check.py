import importlib.util,json,sys,time
from pathlib import Path
ops=Path('/opt/development/magic-ops');sys.path.insert(0,str(ops/'scripts'))
spec=importlib.util.spec_from_file_location('attention_engine_runner',ops/'scripts/factory-ng-run-engine-ticket.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
review=ops/'docs/factory-ng/reviews/2026-09-15-needs-attention/incremental-blight'
ticket=json.loads((review/'ticket.json').read_text())
original_gate=m.ticket_gate
def report_gate(command,clone,ticket):
 print('RUN '+command,flush=True)
 result=original_gate(command,clone,ticket)
 print('EXIT '+str(result['exit_code']),flush=True)
 return result
m.ticket_gate=report_gate
gates,changed=m.check_candidate(ticket,Path('/tmp/factory-ng-attention-incremental'))
(review/'gates.json').write_text(json.dumps({'gates':gates,'changed':changed},indent=2)+'\n')
print(json.dumps({'gates':[{'id':g['id'],'outcome':g['outcome']} for g in gates],'changed':changed},indent=2))
sys.exit(0 if gates and all(g['outcome']=='passed' for g in gates) and len(gates)==len(ticket['gates'])+1 else 1)
