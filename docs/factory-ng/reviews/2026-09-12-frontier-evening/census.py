import sys,json,collections,hashlib,subprocess,time
from pathlib import Path
sys.path.insert(0,'/opt/development/magic-ops/scripts')
import importlib.util
spec=importlib.util.spec_from_file_location('producer','/opt/development/magic-ops/scripts/factory-ng-produce-build-plan.py'); p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
repo=Path('/tmp/factory-frontier-sep12-evening');sys.path.insert(0,str(repo/'scripts/paragraph'));import reparse
history=p.production_history(p.TICKETS,p.JOBS); rows=[];counts=collections.Counter();start=time.monotonic()
for shard in sorted((repo/'backend/data/carddb').glob('*.json')):
 for name,card in (json.loads(shard.read_text()) or {}).items():
  if not isinstance(card,dict) or card.get('status')!='review':continue
  misses=reparse.reparse_card(card).get('misses',[]);counts[len(misses)]+=1
  if len(misses)>2:continue
  shapes=sorted({k for k,d in misses});key='build-plan:%s:%s'%(shapes[0] if shapes else '',p.digest_bytes((card.get('text') or '').encode()))
  rows.append(dict(name=name,misses=misses,text=card.get('text'),accounted=key in history))
out=dict(revision=p.source_revision(repo),seconds=time.monotonic()-start,miss_counts=dict(counts),cards=rows)
Path('/opt/development/magic-ops/docs/factory-ng/reviews/2026-09-12-frontier-evening/census.json').write_text(json.dumps(out,indent=2)+'\n')
print('DONE',out['revision'],out['seconds'],out['miss_counts'])
