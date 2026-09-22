import json,os,subprocess,time,sys
from pathlib import Path
out=Path(__file__).resolve().parent; mode=sys.argv[1]; label=sys.argv[2] if len(sys.argv)>2 else mode
root=Path('/tmp/goose-factory-benchmark');env=os.environ.copy();env.update(GOOSE_PATH_ROOT=str(root),GOOSE_MODEL='halogen-qwen3.8-flash-next',GOOSE_PROVIDER='strix_halo',GOOSE_MODE='auto',GOOSE_MAX_TOKENS='16000',GOOSE_TEMPERATURE='0.7',GOOSE_CONTEXT_LIMIT='131072',CONTEXT_FILE_NAMES='[]')
cmd=['goose','run','--instructions',str(out/(mode+'.prompt.txt')),'--no-profile','--name','factory-benchmark-'+label,'--max-turns','25' if mode=='agentic' else '1','--output-format','stream-json','--stats']

if mode=='agentic':cmd += ['--with-builtin','developer']
t=time.monotonic();start=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
with (out/(label+'.stdout.jsonl')).open('w') as stdout,(out/(label+'.stderr.log')).open('w') as stderr:
 try: rc=subprocess.run(cmd,cwd=root/mode,env=env,stdout=stdout,stderr=stderr,timeout=1200).returncode
 except subprocess.TimeoutExpired:rc=124
result={'mode':mode,'started_at':start,'wall_seconds':round(time.monotonic()-t,3),'exit_code':rc,'command':cmd,'environment':{k:v for k,v in env.items() if k.startswith('GOOSE_') or k=='CONTEXT_FILE_NAMES'}}
(out/(label+'.timing.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result))
