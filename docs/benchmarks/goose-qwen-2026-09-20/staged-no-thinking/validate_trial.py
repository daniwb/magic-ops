import sys,json,time,importlib.util,subprocess,os
from pathlib import Path
out=Path(__file__).resolve().parent;ops=Path('/data/magic-stack/development/magic-ops');sys.path.insert(0,str(ops/'scripts'))
spec=importlib.util.spec_from_file_location('runner',ops/'scripts/factory-ng-run-engine-ticket.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
os.environ['PATH']='/data/magic-stack/toolchain/go/bin:'+os.environ.get('PATH','')
mode=sys.argv[1];clone=Path('/tmp/goose-factory-staged-no-thinking')/mode;ticket=json.loads((out/'ticket.json').read_text());start=time.monotonic()
result={'mode':mode,'source_revision':ticket['source']['revision']}
if mode=='staged' and '--skip-apply' not in sys.argv:
 reply=(out/'staged.reply.txt').read_text()
 applied=runner.call([sys.executable,str(ops/'scripts/map-pipeline-apply.py'),'--allow-game'],clone,stdin=reply,timeout=60);result['apply']=applied
 if applied['exit_code']:
  result['validation_seconds']=round(time.monotonic()-start,3);(out/(mode+'.validation.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result));sys.exit(0)
gates,changed=runner.check_candidate(ticket,clone);result.update(gates=gates,changed=changed,passed=all(g['outcome']=='passed' for g in gates),validation_seconds=round(time.monotonic()-start,3))
(out/(mode+'.validation.json')).write_text(json.dumps(result,indent=2))
# Include untracked files in the saved patch without committing.
if changed:subprocess.run(['git','add','--intent-to-add','--',*changed],cwd=clone,check=True)
(out/(mode+'.patch')).write_text(subprocess.check_output(['git','diff','--binary'],cwd=clone,text=True))
print(json.dumps({k:v for k,v in result.items() if k!='gates'}));print([(g['id'],g['outcome'],g.get('detail','')[-250:] if g['outcome']=='failed' else '') for g in gates])
