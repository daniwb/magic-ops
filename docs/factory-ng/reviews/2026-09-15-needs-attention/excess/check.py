import importlib.util,json,sys,time
from pathlib import Path
ops=Path('/opt/development/magic-ops');sys.path.insert(0,str(ops/'scripts'))
spec=importlib.util.spec_from_file_location('attention_engine_runner',ops/'scripts/factory-ng-run-engine-ticket.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
review=ops/'docs/factory-ng/reviews/2026-09-15-needs-attention/excess'
ticket=json.loads((review/'ticket.json').read_text())
gates,changed=m.check_candidate(ticket,Path('/tmp/factory-ng-attention-excess'))
(review/'gates.json').write_text(json.dumps({'gates':gates,'changed':changed},indent=2)+'\n')
print(json.dumps({'gates':[{'id':g['id'],'outcome':g['outcome']} for g in gates],'changed':changed},indent=2))
sys.exit(0 if gates and all(g['outcome']=='passed' for g in gates) and len(gates)==len(ticket['gates'])+2 else 1)
