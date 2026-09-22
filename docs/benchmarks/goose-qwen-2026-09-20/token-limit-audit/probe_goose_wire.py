"""Capture Goose's token field with a local fake endpoint; no model inference."""
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import json,os,subprocess,tempfile,threading,time
out=Path(__file__).resolve().parent
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append({'path':self.path,'body':payload})
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
  chunks=[{'id':'token-limit-audit','object':'chat.completion.chunk','created':int(time.time()),'model':'halogen-qwen3.8-flash-next','choices':[{'index':0,'delta':{'role':'assistant','content':'OK'},'finish_reason':None}]},{'id':'token-limit-audit','object':'chat.completion.chunk','created':int(time.time()),'model':'halogen-qwen3.8-flash-next','choices':[{'index':0,'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}]
  for chunk in chunks:self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
  self.wfile.write(b'data: [DONE]\n\n')
server=HTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
results=[]
for engine in ['ollama','openai']:
 requests=[];root=Path(tempfile.mkdtemp(prefix='goose-token-wire-'));config=root/'config';(config/'custom_providers').mkdir(parents=True)
 provider={'name':'strix_halo','engine':engine,'display_name':'Token field audit','api_key_env':'','base_url':'http://127.0.0.1:'+str(server.server_port),'models':[{'name':'halogen-qwen3.8-flash-next'}],'requires_auth':False,'supports_streaming':True}
 (config/'custom_providers/strix_halo.json').write_text(json.dumps(provider));(config/'config.yaml').write_text('GOOSE_TELEMETRY_ENABLED: false\n')
 env=dict(os.environ,GOOSE_PATH_ROOT=str(root),GOOSE_MODEL='halogen-qwen3.8-flash-next',GOOSE_PROVIDER='strix_halo',GOOSE_MAX_TOKENS='16000',CONTEXT_FILE_NAMES='[]')
 p=subprocess.run(['goose','run','--no-profile','--no-session','--max-turns','1','--text','Reply OK.','--output-format','json'],cwd=root,env=env,capture_output=True,text=True,timeout=60)
 result={'engine':engine,'exit_code':p.returncode,'requests':requests,'stdout':p.stdout,'stderr':p.stderr};(out/(engine+'-wire-probe.json')).write_text(json.dumps(result,indent=2))
 results.append({'engine':engine,'exit_code':p.returncode,'requests':[{'path':r['path'],'settings':{k:v for k,v in r['body'].items() if k not in ['messages','tools']}} for r in requests]})
server.shutdown();(out/'wire-probe-summary.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
