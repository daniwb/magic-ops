import collections, datetime, json
from pathlib import Path
root=Path(__file__).resolve().parents[4]
here=Path(__file__).resolve().parent
jobs={k:v for k,v in json.loads((root/'state/factory-ng-jobs.json').read_text())['jobs'].items() if not v.get('superseded_by')}
runtime=json.loads((root/'state/factory-ng-runtime.json').read_text())
active={}
for key,job in jobs.items():
 if job.get('state')=='working' and not job.get('verification_batch'):
  try: live=Path('/proc/%s/stat'%job.get('pid')).read_text().split()[2]!='Z'
  except (OSError,IndexError): live=False
  active[job.get('worker')]={'ticket':key,'live':live}
new=[k for k,j in jobs.items() if j.get('created_at','')>'2026-09-17T12:25']
row={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active':active,
 'queued':[k for k,j in jobs.items() if j.get('state')=='queued'],
 'new_ticket_count':len(new),'new_completed_count':sum(jobs[k]['state']=='completed' for k in new),
 'states':dict(collections.Counter(j.get('state') for j in jobs.values())),
 'runtime':{k:runtime.get(k) for k in ['updated_at','phase','queue']},'recent_results':runtime.get('results',[])[-3:]}
with (here/'live.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
print(json.dumps(row,indent=2))
