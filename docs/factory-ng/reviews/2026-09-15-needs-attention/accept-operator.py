"""Publish a gated finite operator correction; never writes live job state."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
OPS=Path('/opt/development/magic-ops');sys.path.insert(0,str(OPS/'scripts'))
from factory_ng_receipts import write_receipt
review=Path(__file__).resolve().parent/sys.argv[1]
clone=Path((review/'clone.txt').read_text().strip())
ticket_path=review/'ticket.json';ticket=json.loads(ticket_path.read_text())
checks=json.loads((review/'gates.json').read_text());gates=checks['gates']
assert gates and all(g['outcome']=='passed' for g in gates), 'candidate gates not green'
assert [g['command'] for g in gates if 'command' in g]==ticket['gates'], 'original gates missing'
def git(*args):return subprocess.check_output(['git',*args],cwd=clone,text=True)
def digest(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
assert git('rev-parse','HEAD').strip()==ticket['source']['revision'], 'unexpected candidate base'
changed=[line[3:] for line in git('status','--porcelain').splitlines()]
assert set(changed)==set(checks['changed']) and set(changed)<=set(ticket['scope']['allowed_paths'])
subprocess.run(['git','diff','--check'],cwd=clone,check=True)
subprocess.run(['git','add','--',*changed],cwd=clone,check=True)
subprocess.run(['git','commit','-qm',ticket['title']],cwd=clone,check=True)
stamp=time.strftime('%Y-%m-%dT%H%M%SZ',time.gmtime());slug=ticket['id'].removeprefix('ticket:').replace('.','-').replace('/','-')
patch=OPS/'docs/factory-ng/candidates'/f'{stamp}-{slug}.patch'
with patch.open('xb') as f:f.write(subprocess.check_output(['git','format-patch','-1','--stdout','HEAD'],cwd=clone))
receipt=OPS/'docs/factory-ng/runs'/f'{stamp}-{slug}.json'
value={'schema':'factory.observation-receipt/v1','created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
 'ticket':{'id':ticket['id'],'path':str(ticket_path.relative_to(OPS)),'sha256':digest(ticket_path)},'skill':ticket['skill'],
 'model':{'profile':'codex-constrained@1.1.0','resolved_model':'operator-correction-no-worker-provider-run','worker':'operator','telemetry':{'model_calls':0}},
 'execution':{'mode':'isolated_clone_observation_only','source_revision':ticket['source']['revision'],'source_tree_changed':False,'candidate_clone':str(clone),'candidate_commit':git('rev-parse','HEAD').strip(),'candidate_patch':str(patch.relative_to(OPS)),'candidate_patch_sha256':digest(patch)},
 'raw_artifacts':[{'path':str((review/'gates.json').relative_to(OPS)),'sha256':digest(review/'gates.json'),'kind':'operator_candidate_gates'}],
 'gates':gates,'outcome':'accepted_for_dependent_observation','integration':'eligible_full_gate','operator_recovery':ticket['operator_recovery']}
write_receipt(receipt,value)
(review/'receipt.txt').write_text(str(receipt.relative_to(OPS))+'\n')
print(receipt.relative_to(OPS))
