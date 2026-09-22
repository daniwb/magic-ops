from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import sys,json,tempfile,threading,time
sys.path.insert(0,'scripts')
import goose_staged as goose
requests=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append({'path':self.path,'body':payload})
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
  for delta,finish in [({'role':'assistant','content':'PATCH_SENTINEL'},None),({},'stop')]:
   chunk={'id':'adapter-wire-check','object':'chat.completion.chunk','created':int(time.time()),'model':'halogen-qwen3.8-flash-next','choices':[{'index':0,'delta':delta,'finish_reason':finish}]}
   if finish:chunk['usage']={'prompt_tokens':42,'completion_tokens':7,'total_tokens':49}
   self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
  self.wfile.write(b'data: [DONE]\n\n')
server=HTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory() as directory:
 provider=json.loads(goose.PROVIDER.read_text());provider['base_url']='http://127.0.0.1:'+str(server.server_port)
 goose.PROVIDER=Path(directory)/'provider.json';goose.PROVIDER.write_text(json.dumps(provider))
 artifact=goose.run('Whole packet sentinel\n## Relevant code regions\nCONTRACT_AND_REPAIR_SENTINEL', 'halogen-qwen3.8-flash-next')
 text,usage=goose.decode_events(artifact['events'])
 assert text=='PATCH_SENTINEL',text
 assert len(requests)==1,len(requests)
 body=requests[0]['body'];assert body['max_tokens']==32000
 assert not body.get('tools'),body.get('tools')
 assert body.get('enable_thinking') is not False
 assert 'CONTRACT_AND_REPAIR_SENTINEL' in json.dumps(body['messages'])
 assert usage['input_tokens']==42 and usage['output_tokens']==7,usage
 out=Path('docs/benchmarks/goose-qwen-2026-09-20/ceiling-32000/production-adapter-wire-check.json')
 out.write_text(json.dumps({'passed':True,'request_count':len(requests),'settings':{k:v for k,v in body.items() if k!='messages'},'complete_packet':True,'usage':usage,'answer':text},indent=2)+'\n')
 print(out.read_text())
server.shutdown()
