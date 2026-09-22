import json,os,subprocess,time,sys,shutil
from pathlib import Path
ops=Path(__file__).resolve().parents[4];out=Path(__file__).resolve().parent
name=sys.argv[1];root=Path('/tmp/goose-database-tools')/name;root.mkdir(parents=True,exist_ok=True)
repo=root/'checkout'
if not repo.exists():
 subprocess.run(['git','clone','--quiet','--shared','--no-hardlinks',str(ops.parent/'test/openmagic'),str(repo)],check=True)
 subprocess.run(['git','remote','remove','origin'],cwd=repo,check=True)
config=root/'config';(config/'custom_providers').mkdir(parents=True,exist_ok=True)
shutil.copy2(ops/'config/goose/strix_halo.json',config/'custom_providers/strix_halo.json')
(config/'config.yaml').write_text('GOOSE_TELEMETRY_ENABLED: false\n')
env={k:v for k,v in os.environ.items() if not k.startswith('GOOSE_')}
env.update(GOOSE_PATH_ROOT=str(root),GOOSE_MODEL='halogen-qwen3.8-flash-next',GOOSE_PROVIDER='strix_halo',GOOSE_MODE='auto',GOOSE_MAX_TOKENS='6000',GOOSE_TEMPERATURE='0.2',GOOSE_CONTEXT_LIMIT='131072',CONTEXT_FILE_NAMES='[]',KB_TRACE_FILE=str(out/(name+'.kb.jsonl')),KB_TICKET='goose-database-tools-'+name,KB_ATTEMPT='1',PATH='/data/magic-stack/toolchain/go/bin:'+os.environ['PATH'],PYTHONPATH=str(ops/'scripts')+':/data/magic-stack/pydeps')
command=['goose','run','--instructions',str(out/(name+'.prompt.txt')),'--no-profile','--with-extension','card-knowledge:python3 '+str(ops/'scripts/kb-mcp-server.py'),'--name','database-tools-'+name,'--max-turns','10','--output-format','stream-json','--stats']
start=time.monotonic()
with (out/(name+'.stdout.jsonl')).open('w') as stdout,(out/(name+'.stderr.log')).open('w') as stderr:
 try:rc=subprocess.run(command,cwd=repo,env=env,stdout=stdout,stderr=stderr,timeout=1200).returncode
 except subprocess.TimeoutExpired:rc=124
result={'exit_code':rc,'wall_seconds':round(time.monotonic()-start,3),'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'checkout_status':subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True),'command':command}
(out/(name+'.timing.json')).write_text(json.dumps(result,indent=2)+'\n')
for p in (root/'state/logs').glob('llm_request*.jsonl'):shutil.copy2(p,out/(name+'.'+p.name))
print(json.dumps(result))
