import json
from pathlib import Path
out=Path(__file__).resolve().parent
rows=[]
for name in ('compile','protocol'):
 trial=out/name
 replay=json.loads((trial/'replay.json').read_text())
 receipts=[]
 for p in (trial/'runs').glob('*.json'):
  try:r=json.loads(p.read_text())
  except ValueError:continue
  if isinstance(r,dict) and r.get('schema')=='factory.observation-receipt/v1':receipts.append((p,r))
 assert len(receipts)==1,receipts
 path,receipt=receipts[0]
 new=[]
 for p in (trial/'runs').glob('*repair.raw.json'):
  raw=json.loads(p.read_text());usage={}
  for line in raw.get('events','').splitlines():
   try:event=json.loads(line)
   except ValueError:continue
   if event.get('type')=='complete':usage=event
  new.append({'artifact':str(p.relative_to(out)),'usage':usage,'exit_code':raw.get('exit_code')})
 assert len(replay['model_calls'])==3
 assert [c['historical_replay'] for c in replay['model_calls']]==[True,True,False]
 row={'test':name,'outcome':receipt['outcome'],'receipt':str(path.relative_to(out)),
      'replay':replay,'actual_new_model_calls':new,
      'gates':[{'id':g['id'],'outcome':g['outcome'],'detail':g.get('detail','')[-1800:] if g['outcome']=='failed' else ''} for g in receipt['gates']]}
 rows.append(row)
(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
for row in rows:print(row['test'],row['outcome'],row['replay']['elapsed_seconds'],[(g['id'],g['outcome']) for g in row['gates']])
