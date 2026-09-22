import sys,time,json,pathlib,hashlib
source=pathlib.Path('/tmp/factory-python-opt-sep15/source')
sys.path.insert(0,str(source/'scripts/paragraph'))
import reparse
from factory_ng_producer_cache import ProducerCache
from factory_ng_parser_runtime import prepare_parser
cards=[]
for path in sorted((source/'backend/data/carddb').glob('*.json')):
 data=json.loads(path.read_text())
 if isinstance(data,dict):cards.extend((n,c) for n,c in sorted(data.items()) if isinstance(c,dict))
# Compare the complete emitted representation, not just eligibility or miss count.
def result(c):
 try:return {'value':reparse.reparse_card(c)}
 except Exception as e:return {'error':[type(e).__name__,str(e)]}
original=[];metrics={};exceptions=[]
for mode in ['original','optimized']:
 if mode=='optimized':
  cache=ProducerCache('/tmp/factory-python-opt-sep15/equivalence-cache.sqlite3')
  prepare_parser(source,reparse,cache)
 cpu=time.process_time();wall=time.monotonic();mismatches=[]
 for i,(name,card) in enumerate(cards):
  value=result(card);raw=json.dumps(value,sort_keys=True,ensure_ascii=False);h=hashlib.sha256(raw.encode()).hexdigest()
  if mode=='original':
   original.append(h)
   if 'error' in value:exceptions.append([name,value['error']])
  elif h!=original[i]:mismatches.append(name)
  if (i+1)%2000==0:print(mode,i+1,'cpu',round(time.process_time()-cpu,1),flush=True)
 metrics[mode]={'cards':len(cards),'cpu_seconds':time.process_time()-cpu,'wall_seconds':time.monotonic()-wall,'mismatches':mismatches}
 print(mode,metrics[mode],flush=True)
 if mode=='optimized':cache.close()
metrics['baseline_exceptions']=exceptions
pathlib.Path('/tmp/factory-python-opt-sep15/equivalence.json').write_text(json.dumps(metrics,indent=2)+'\n')
if metrics['optimized']['mismatches']:raise SystemExit(1)
