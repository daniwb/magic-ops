"""Record that the newer parked contract is already satisfied by the gated recovery."""
import datetime, hashlib, importlib.util, json, subprocess, sys
from pathlib import Path
OPS=Path('/opt/development/magic-ops'); REVIEW=Path(__file__).resolve().parent; SOURCE=Path('/opt/development/test/openmagic')
sys.path.insert(0,str(OPS/'scripts'))
from factory_ng_receipts import write_receipt
result=json.loads((REVIEW/'integration-output.json').read_text()); full_path=OPS/result['receipt']; full=json.loads(full_path.read_text())
ticket_path=OPS/'docs/factory-ng/tickets/map-plan-damage-by-dong-zhou-the-tyrant-845ba13507-v4.json'; ticket=json.loads(ticket_path.read_text())
def digest(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(SOURCE),*args],text=True).strip()
revision=git('rev-parse','HEAD')
assert revision==full['source']['result_commit'] and full['source']['pushed']
assert full['outcome']=='pushed_full_production_gate_green' and not git('status','--porcelain')
commands=[g for g in ticket['gates'] if 'python' in g or 'go test' in g]
for command in commands:assert any(g.get('command')==command and g['outcome']=='passed' for g in full['gates']),command
spec=importlib.util.spec_from_file_location('runner',OPS/'scripts/factory-ng-run-map-ticket.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
gates=[]
for command in commands+['git diff --check']:
 run=runner.run_ticket_gate(command,SOURCE,ticket)
 gates.append({'id':'current-ground-truth','command':command,'outcome':'passed' if run['exit_code']==0 else 'failed','elapsed_ms':run['elapsed_ms'],'detail':(run['stdout']+'\n'+run['stderr'])[-2000:]})
 assert run['exit_code']==0,run
assert git('rev-parse','HEAD')==revision and not git('status','--porcelain')
gates.append({'id':'scope','outcome':'passed','detail':'Read-only verification; no paths changed.'})
now=datetime.datetime.now(datetime.timezone.utc)
path=OPS/'docs/factory-ng/runs'/f'{now:%Y-%m-%dT%H%M%SZ}-operator-dong-zhou-already-satisfied.json'
value={'schema':'factory.observation-receipt/v1','created_at':now.strftime('%Y-%m-%dT%H:%M:%SZ'),'ticket':{'id':ticket['id'],'path':str(ticket_path.relative_to(OPS)),'sha256':digest(ticket_path)},'outcome':'accepted_ground_truth_satisfied','integration':'already_verified_by_full_gate','parents':[ticket['id'],str(full_path.relative_to(OPS))],'operator_review':{'reason':'The newer parked contract has exactly the same semantic gates as the recovered predecessor; all passed on this exact pushed revision. Historical failures remain unchanged.','full_gate_receipt':str(full_path.relative_to(OPS)),'full_gate_receipt_sha256':digest(full_path)},'execution':{'mode':'read_only_ground_truth_verification','source_revision':revision,'source_tree_changed':False},'gates':gates,'usage':{'model_calls':0},'worker':'operator'}
write_receipt(path,value);(REVIEW/'dong-closure-receipt.txt').write_text(str(path.relative_to(OPS))+'\n');print(path)
