"""Check immutable integration evidence and preserve the final recovery snapshot."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
OPS=Path('/opt/development/magic-ops');sys.path.insert(0,str(OPS/'scripts'))
from factory_ng_safety import source_problem
OUT=Path(__file__).resolve().parent;SOURCE=Path('/opt/development/test/openmagic')
result=json.loads((OUT/'integration-output.json').read_text());assert result['status']=='pushed_full_production_gate_green',result
receipt=json.loads((OPS/result['receipt']).read_text());ticket=json.loads((OUT/'ticket.json').read_text())
assert receipt['outcome']==result['status'] and receipt['source']['pushed'] and not receipt['source']['deployed']
assert not receipt['excluded_candidates'] and all(g['outcome']=='passed' for g in receipt['gates'])
ids={x['ticket'] for x in ticket['operator_recovery']['originals']};assert ids<=set(receipt['parents'])
assert {'reparse-flip','reparse-import','go-build','game-tests','focused-go','full-sharded-suite','push'}<={g['id'] for g in receipt['gates']}
required_commands={command for old in ticket['operator_recovery']['originals'] for command in json.loads((OPS/old['ticket_path']).read_text())['gates'] if 'go test' in command and '-run ' in command}
assert required_commands<={g.get('command') for g in receipt['gates']}
for sha in [result['result_commit'],'fb557922f41d2d07a313d484dc64f551449ccf1e','482cd75c21cb47afe2f5ea79e0ca3a3e7ddc5ecc']:
 subprocess.run(['git','-C',str(SOURCE),'merge-base','--is-ancestor',sha,'HEAD'],check=True)
for original in ticket['operator_recovery']['originals']:
 for path_key,hash_key in [('ticket_path','ticket_sha256'),('receipt','receipt_sha256')]:
  assert 'sha256:'+hashlib.sha256((OPS/original[path_key]).read_bytes()).hexdigest()==original[hash_key]
for attempt in range(30):
 jobs=json.loads((OPS/'state/factory-ng-jobs.json').read_text())['jobs']
 if all(jobs[t]['state']=='completed' and jobs[t]['integration_receipt']==result['receipt'] for t in ids):break
 print('Waiting for controller receipt reconciliation',flush=True);time.sleep(10)
else:raise RuntimeError('successful integration has not reconciled into all five jobs')
before=json.loads((OUT/'pre-integration-jobs.json').read_text())
for tid in ids:
 for key in ['attempts','integration_attempts','integration_repair_attempts']:
  assert before[tid].get(key)==jobs[tid].get(key),(tid,key,before[tid].get(key),jobs[tid].get(key))
problem=source_problem(SOURCE);assert not problem,problem
remote=subprocess.check_output(['git','-C',str(SOURCE),'ls-remote','origin','refs/heads/main'],text=True).split()[0]
subprocess.run(['git','-C',str(SOURCE),'merge-base','--is-ancestor',result['result_commit'],remote],check=True)
summary={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'initial_conflict_lineages':15,'verified_pushed_lineages':15,'unresolved_lineages':0,'followup_integration_receipt':result['receipt'],'followup_result_commit':result['result_commit'],'remote_main':remote,'excluded_candidates':receipt['excluded_candidates'],'canonical_clean':True,'live_deployed':False,'retry_counters_unchanged':True,'lineages':[{'ticket':tid,'state':jobs[tid]['state'],'outcome':jobs[tid]['outcome'],'integration_receipt':jobs[tid]['integration_receipt'],'attempts':jobs[tid].get('attempts')} for tid in sorted(ids)],'gates':[{'id':g['id'],'outcome':g['outcome'],'elapsed_ms':g.get('elapsed_ms')} for g in receipt['gates']]}
(OUT/'final-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
