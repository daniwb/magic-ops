"""Check tool/source evidence independently of the model's success claims."""
import hashlib,json,sqlite3,subprocess
from pathlib import Path
out=Path(__file__).resolve().parent
results=[]
for name in ('engine','primitive','engine-refined'):
 root=Path('/tmp/goose-database-tools')/name;repo=root/'checkout'
 timing=json.loads((out/(name+'.timing.json')).read_text())
 db=sqlite3.connect(root/'data/sessions/sessions.db');db.row_factory=sqlite3.Row
 usage=[dict(r) for r in db.execute('select * from usage_ledger')]
 messages=[dict(r) for r in db.execute('select * from messages order by rowid')]
 (out/(name+'.messages.json')).write_text(json.dumps(messages,indent=2)+'\n')
 (out/(name+'.usage.json')).write_text(json.dumps(usage,indent=2)+'\n')
 texts=[];calls=[]
 for m in messages:
  blocks=json.loads(m['content_json'])
  if m['role']=='assistant':
   t=''.join(b.get('text','') for b in blocks if b.get('type')=='text')
   if t:texts.append(t)
  for b in blocks:
   if b.get('type')=='toolRequest':calls.append(b)
 final=texts[-1] if texts else ''
 (out/(name+'.answer.txt')).write_text(final)
 traces=[json.loads(x) for x in (out/(name+'.kb.jsonl')).read_text().splitlines()]
 resolutions=[r['resolution'] for r in traces if 'resolution' in r]
 verified=[]
 for r in resolutions:
  if r['status']!='resolved':continue
  text=(repo/r['path']).read_text()
  expected='\n'.join('%5d %s'%(i+1,l) for i,l in enumerate(text.splitlines()) if r['start']<=i+1<=r['supplied_end'])
  assert r['excerpt']==expected,(name,r['path'],'excerpt mismatch')
  assert r['sha256']=='sha256:'+hashlib.sha256(text.encode()).hexdigest()
  assert r['source_revision']==timing['revision']
  verified.append({k:r[k] for k in ('symbol_id','path','start','supplied_end','source_revision','truncated')})
 wiretools=set()
 for p in out.glob(name+'.llm_request*.jsonl'):
  for line in p.read_text().splitlines():
   r=json.loads(line)
   for t in r.get('input',{}).get('tools',[]):wiretools.add(t['function']['name'])
 allowed={'card-knowledge__'+n for n in ('find_capability','similar_handlers','check_capability','read_source')}
 assert wiretools==allowed,wiretools
 assert subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)==''
     # Every structured source citation must refer to a declaration actually read.
 parsed=json.loads(final.strip().removeprefix('```json').removesuffix('```').strip())
 citations=[]
 def visit(value):
  if isinstance(value,dict):
   if 'symbol_id' in value and 'source_revision' in value:
    match=next((v for v in verified if v['symbol_id']==value['symbol_id']),None)
    assert match is not None,(name,'uncited source',value['symbol_id'])
    assert match['path']==value['path'] and match['source_revision']==value['source_revision']
    assert match['start']==value['start_line'],(name,'wrong source line',value)
    citations.append(value['symbol_id'])
   for v in value.values():visit(v)
  elif isinstance(value,list):
   for v in value:visit(v)
 visit(parsed)
 result={'verified_answer_citations':citations,'trial':name,'timing':timing,'input_tokens':sum(r['input_tokens'] or 0 for r in usage),'output_tokens':sum(r['output_tokens'] or 0 for r in usage),'cache_read_tokens':sum(r['cache_read_tokens'] or 0 for r in usage),'model_requests':len(usage),'tool_calls':len(calls),'tools_used':sorted({c['toolCall']['value']['name'] for c in calls}),'verified_source':verified,'only_read_only_tools':True,'checkout_clean':True,'final_answer_present':bool(final)}
 results.append(result)
(out/'verified-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
