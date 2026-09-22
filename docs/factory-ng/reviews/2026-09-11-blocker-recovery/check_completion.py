"""Read-only post-integration audit; writes review evidence only."""
import json, subprocess, datetime
from pathlib import Path
OPS=Path('/opt/development/magic-ops'); REVIEW=Path(__file__).resolve().parent
SOURCE=Path('/opt/development/test/openmagic')
result=json.loads((REVIEW/'integration-output.json').read_text())
receipt=json.loads((OPS/result['receipt']).read_text())
originals=json.loads((REVIEW/'selected-originals.json').read_text())
before=json.loads((REVIEW/'jobs-before.json').read_text())
after=json.loads((OPS/'state/factory-ng-jobs.json').read_text())['jobs']
before=before.get('jobs',before)
names={'Sage of the Skies','Dong Zhou, the Tyrant','Skullcage','Sphere of Annihilation','Retrieve','Promise of Tomorrow','Tideforce Elemental','Word of Binding','Crown of Empires'}
cards={};auto=0
for p in (SOURCE/'backend/data/carddb').glob('*.json'):
 data=json.loads(p.read_text())
 if not isinstance(data,dict): continue
 for name,value in data.items():
  if not isinstance(value,dict):continue
  auto+=value.get('status')=='auto'
  if name in names:cards[name]={'status':value.get('status'),'path':str(p.relative_to(SOURCE))}
ids=[x['ticket'] for x in originals]
ids.append('ticket:map.plan-gain-control-crown-of-empires-70becf7c9a/v4')
ids.append('ticket:map.plan-damage-by-dong-zhou-the-tyrant-845ba13507/v4')
fields=['state','superseded_by','attempts','integration_attempts','receipt','integration_receipt','reason']
jobs={k:{'before':{f:before.get(k,{}).get(f) for f in fields},'after':{f:after.get(k,{}).get(f) for f in fields}} for k in dict.fromkeys(ids)}
def git(*args):return subprocess.check_output(['git','-C',str(SOURCE),*args],text=True).strip()
evidence={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'integration':result,'source':receipt['source'],'gate_outcomes':[(g['id'],g['outcome']) for g in receipt['gates']],'excluded_candidates':receipt.get('excluded_candidates'), 'cards':cards,'auto_cards':auto,'jobs':jobs,'canonical_status':git('status','--porcelain'),'head':git('rev-parse','HEAD'),'origin_main':git('rev-parse','origin/main')}
(REVIEW/'completion-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({k:v for k,v in evidence.items() if k not in ['jobs','gate_outcomes']},indent=2))
print('job states', {k:v['after']['state'] for k,v in jobs.items()})
print('counter changes',{k:{f:(v['before'][f],v['after'][f]) for f in ['attempts','integration_attempts'] if v['before'][f]!=v['after'][f]} for k,v in jobs.items() if any(v['before'][f]!=v['after'][f] for f in ['attempts','integration_attempts'])})
