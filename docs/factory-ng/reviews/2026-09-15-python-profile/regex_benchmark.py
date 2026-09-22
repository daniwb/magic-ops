import sys,time,json,pathlib,cProfile,pstats,io
source=pathlib.Path('/opt/development/test/openmagic')
sys.path.insert(0,str(source/'scripts/paragraph'))
start=time.process_time();import reparse
print('import_cpu_seconds',round(time.process_time()-start,3),flush=True)
start=time.process_time();cards=[]
for shard in sorted((source/'backend/data/carddb').glob('*.json')):
 data=json.loads(shard.read_text()) or {};cards.extend(c for c in data.values() if isinstance(c,dict) and c.get('status')=='review')
print('load_corpus_cpu_seconds',round(time.process_time()-start,3),'review_cards',len(cards),flush=True)
sample=cards[::max(1,len(cards)//60)][:60]
import re,functools
measurements=[]
expected=[reparse.reparse_card(c) for c in sample]
for mode in ['existing','bounded_cache']:
 if mode=='bounded_cache': re._compile=functools.lru_cache(maxsize=8192)(re._compile)
 for run in range(3):
  start=time.process_time();actual=[reparse.reparse_card(c) for c in sample];elapsed=time.process_time()-start
  result={'mode':mode,'run':run,'cpu_seconds':elapsed,'cards':len(sample),'same_outputs':actual==expected}
  measurements.append(result);print(result,flush=True)
pathlib.Path('/tmp/factory-python-profile-sep15/regex-benchmark.json').write_text(json.dumps(measurements,indent=2)+'\n')
