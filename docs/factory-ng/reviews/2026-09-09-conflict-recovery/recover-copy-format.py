import hashlib,importlib.util,json,subprocess,sys,tempfile,time
from pathlib import Path
ops=Path('/opt/development/magic-ops');sys.path.insert(0,str(ops/'scripts'))
spec=importlib.util.spec_from_file_location('runner',ops/'scripts/factory-ng-run-engine-ticket.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
oldpath=ops/'docs/factory-ng/runs/2026-09-09T064705Z-engine-auto-copy-triggering-referent-b4a4facffb-v2-codex.json';old=json.loads(oldpath.read_text());ticket=json.loads((ops/old['ticket']['path']).read_text())
out=ops/'docs/factory-ng/reviews/2026-09-09-conflict-recovery/copy-format';out.mkdir(exist_ok=True)
clone=Path(tempfile.mkdtemp(prefix='ng-copy-format-'))
def cmd(args):
 r=subprocess.run(args,cwd=clone,capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr;return r.stdout
cmd(['git','clone','--shared','/opt/development/test/openmagic',str(clone)]);cmd(['git','checkout','--detach',old['execution']['source_revision']])
for suffix in ('raw.json','gate-repair.raw.json'):
 path=oldpath.with_name(oldpath.name.removesuffix('.json')+'.'+suffix)
 expected=next(a['sha256'] for a in old['raw_artifacts'] if a['path']==str(path.relative_to(ops)))
 assert runner.digest(path.read_bytes())==expected
 events=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
 text=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message'][-1]
 r=subprocess.run([sys.executable,str(ops/'scripts/map-pipeline-apply.py'),'--allow-game'],cwd=clone,input=text,text=True,capture_output=True)
 assert r.returncode==0,r.stdout+r.stderr
names=[line[3:] for line in cmd(['git','status','--porcelain']).splitlines()]
assert set(names)<=set(ticket['scope']['allowed_paths'])
cmd(['/usr/local/go/bin/gofmt','-w',*[str(clone/n) for n in names if n.endswith('.go')]])
print('checking formatted replay',clone,flush=True)
gates,changed=runner.check_candidate(ticket,clone);(out/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
if any(g['outcome']!='passed' for g in gates):
 print('formatted replay rejected',[(g['id'],g.get('detail','')[-500:]) for g in gates if g['outcome']!='passed'],flush=True);sys.exit(1)
cmd(['git','add',*changed]);cmd(['git','-c','user.name=Factory NG Operator','-c','user.email=factory-ng@local','commit','-m','factory-ng: format retained copy-referent candidate'])
stamp=time.strftime('%Y-%m-%dT%H%M%SZ',time.gmtime());patch=ops/'docs/factory-ng/candidates'/(stamp+'-copy-referent-v2-operator-format.patch');patch.write_text(cmd(['git','format-patch','-1','--stdout']))
receipt={'schema':'factory.observation-receipt/v1','created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'ticket':old['ticket'],'skill':old['skill'],'outcome':'accepted_for_dependent_observation','integration':'eligible_full_gate','gates':gates,'operator_recovery':{'kind':'gofmt-retained-candidate','parent_receipt':str(oldpath.relative_to(ops)),'parent_sha256':runner.digest(oldpath.read_bytes()),'changes':'Replayed hash-verified original and gate-correction answers, then applied gofmt only. All original candidate gates rerun.','model_retry_budget_reset':False},'model':{'profile':old['model']['profile'],'resolved_model':'operator-gofmt-no-provider-call','worker':'operator','telemetry':{'model_calls':0}},'execution':{'mode':'isolated_clone_observation_only','source_revision':old['execution']['source_revision'],'source_tree_changed':False,'candidate_commit':cmd(['git','rev-parse','HEAD']).strip(),'candidate_clone':str(clone),'candidate_patch':str(patch.relative_to(ops)),'candidate_patch_sha256':runner.digest(patch.read_bytes())},'raw_artifacts':old['raw_artifacts']}
# Historical provider usage remains exclusively on the original receipt.
path=ops/'docs/factory-ng/runs'/(stamp+'-engine-auto-copy-triggering-referent-b4a4facffb-v2-operator-format.json');path.write_text(json.dumps(receipt,indent=2)+'\n');(out/'accepted-receipt.txt').write_text(str(path.relative_to(ops))+'\n');print('accepted formatted replay',path,flush=True)
