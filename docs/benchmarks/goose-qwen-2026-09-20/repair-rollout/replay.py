"""Replay two historical responses, then make one real Goose correction call.

Uses the real runner, frozen original ticket revision and original gates, with
receipts/candidates isolated from the Factory intake directories.
"""
import importlib.util,json,os,sys,time
from pathlib import Path
ops=Path(__file__).resolve().parents[4];out=Path(__file__).resolve().parent
sys.path.insert(0,str(ops/'scripts'))
from goose_staged import decode_events
spec=importlib.util.spec_from_file_location('runner',ops/'scripts/factory-ng-run-engine-ticket.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
name=sys.argv[1];cohort=json.loads((out.parent/'production-comparison/results.json').read_text())['qwen']['details']
needle={'compile':'attacker-owner-choice-library-placement','protocol':'referent-object-to-library-top'}[name]
version='/v2' if name=='compile' else '/v1'
d=next(d for d in cohort if needle in d['ticket'] and d['ticket'].endswith(version));receipt=json.loads((ops/d['last_receipt']).read_text())
artifacts=receipt['raw_artifacts'];initial=next(a for a in artifacts if not a.get('kind'));continued=next(a for a in artifacts if a.get('kind')=='need_continuation')
replays=[]
for a in (initial,continued):
 raw=json.loads((ops/a['path']).read_text());text,usage=decode_events(raw['events'])
 replays.append((text,usage,raw))
trial=out/name;trial.mkdir(exist_ok=True)
runner.RUNS=trial/'runs';runner.CANDIDATES=trial/'candidates'
original=runner.call;calls=[]
def call(command,cwd,stdin=None,**kwargs):
 if any(str(c).endswith('model_call.py') for c in command):
  n=len(calls);(trial/('prompt-%d.txt'%n)).write_text(stdin)
  calls.append({'index':n,'historical_replay':n<2})
  if n<2:
   text,usage,raw=replays[n];Path(kwargs['env']['PIPE_RAW_ARTIFACT']).write_text(json.dumps(raw))
   return {'exit_code':0,'stdout':text,'stderr':'tokens: in=%d out=%d cache_r=0 cache_w=0'%(usage['input_tokens'],usage['output_tokens']),'elapsed_ms':0}
  if n>2:raise RuntimeError('Unexpected extra model call')
 return original(command,cwd,stdin=stdin,**kwargs)
runner.call=call
sys.argv=['runner','--ticket',str(ops/receipt['ticket']['path']),'--worker','goose-repair-benchmark','--profile','qwen-goose-staged@1.0.0','--model','halogen-qwen3.8-flash-next']
start=time.monotonic()
try:runner.main()
finally:(trial/'replay.json').write_text(json.dumps({'ticket':d['ticket'],'historical_receipt':d['last_receipt'],'model_calls':calls,'elapsed_seconds':round(time.monotonic()-start,3)},indent=2)+'\n')
