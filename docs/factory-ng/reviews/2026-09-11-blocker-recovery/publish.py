"""Publish this finite operator correction only after every retained gate passes."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
OPS=Path('/opt/development/magic-ops');sys.path.insert(0,str(OPS/'scripts'))
from factory_ng_receipts import write_receipt
OUT=Path(__file__).resolve().parent
root=Path((OUT/'clone.txt').read_text().strip());ticket_path=OUT/'ticket.json';ticket=json.loads(ticket_path.read_text());gates=json.loads((OUT/'gates.json').read_text())
def digest(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def run(args):return subprocess.check_output(args,cwd=root,text=True).strip()
assert len(gates)==len(ticket['gates']) and all(g['outcome']=='passed' for g in gates)
assert all(g['command']==c for g,c in zip(gates,ticket['gates']))
assert not (OUT/'accepted-receipt.txt').exists(),'never republish existing accepted evidence'
for original in ticket['operator_recovery']['originals']:
 assert digest(OPS/original['ticket_path'])==original['ticket_sha256']
 assert digest(OPS/original['receipt'])==original['receipt_sha256']
changed=[line[3:] for line in subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).splitlines()]
assert set(changed)==set(ticket['scope']['allowed_paths'])
assert subprocess.check_output(['git','show','HEAD:backend/cards/registry.go'],cwd=root)==(root/'backend/cards/registry.go').read_bytes()
run(['git','diff','--check']);run(['git','add','--',*changed]);run(['git','-c','user.name=Factory NG Operator','-c','user.email=factory-ng@local','commit','-m','factory-ng: recover nine parser lineages and registry handoffs'])
stamp=time.strftime('%Y-%m-%dT%H%M%SZ',time.gmtime());patch=OPS/'docs/factory-ng/candidates'/(stamp+'-operator-registry-recovery-sep11.patch')
patch.write_text(subprocess.check_output(['git','format-patch','-1','--stdout'],cwd=root,text=True))
receipt={'schema':'factory.observation-receipt/v1','created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'ticket':{'id':ticket['id'],'path':str(ticket_path.relative_to(OPS)),'sha256':digest(ticket_path)},'skill':ticket['skill'],'outcome':'accepted_for_dependent_observation','integration':'eligible_full_gate','gates':[{'id':'scope','outcome':'passed','detail':'changed='+','.join(changed)},*gates],'operator_recovery':ticket['operator_recovery'],'model':{'profile':'codex-constrained@1.1.0','resolved_model':'operator-correction-no-worker-provider-run','worker':'operator','telemetry':{'model_calls':0}},'execution':{'mode':'isolated_clone_observation_only','source_revision':ticket['source']['revision'],'source_tree_changed':False,'candidate_commit':run(['git','rev-parse','HEAD']),'candidate_clone':str(root),'candidate_patch':str(patch.relative_to(OPS)),'candidate_patch_sha256':digest(patch)},'raw_artifacts':[]}
p=OPS/'docs/factory-ng/runs'/(stamp+'-operator-registry-recovery-sep11.json');write_receipt(p,receipt);(OUT/'accepted-receipt.txt').write_text(str(p.relative_to(OPS))+'\n')
command=[sys.executable,str(OPS/'scripts/factory-ng-integrate.py'),'--receipt',str(p)]
for original in ticket['operator_recovery']['originals']:
 command+=['--parent',original['ticket'],'--parent',original['receipt']]
(OUT/'integration-command.json').write_text(json.dumps(command,indent=2)+'\n');print(p,flush=True)
