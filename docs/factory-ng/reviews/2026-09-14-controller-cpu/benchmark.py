import copy,importlib.util,json,time
from pathlib import Path
from unittest.mock import patch
root=Path('/opt/development/magic-ops')
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 for key,relative in {'OPS':'.','TICKETS':'docs/factory-ng/tickets','RUNS':'docs/factory-ng/runs','WORKERS':'config/factory-ng-workers.json','POLICY':'config/factory-ng-policy.json','JOBS':'state/factory-ng-jobs.json','WORKER_PAUSES':'state/factory-ng-worker-pauses.json'}.items():setattr(m,key,root/relative)
 return m
old=module('before','/tmp/factory-cpu-sep14/controller.before.py');new=module('after',root/'scripts/factory-ng-controller.py')
jobs=new.load_jobs(); workers=new.load_json(new.WORKERS); policy=new.policy()
results={}; outputs={}
for label,m in [('before',old),('after',new)]:
 with patch.object(m,'save_jobs'),patch.object(m,'save_worker_pauses'),patch.object(m,'now',return_value='fixed'),patch.object(m,'load_jobs',side_effect=lambda:copy.deepcopy(jobs)),patch.object(m,'policy',return_value=policy):
  m.sync_jobs()
  wall=time.monotonic();cpu=time.process_time();output,_=m.sync_jobs()
  results[label]={'wall_seconds':time.monotonic()-wall,'cpu_seconds':time.process_time()-cpu,'jobs':len(output['jobs'])}
  outputs[label]=output
  print(label,results[label],flush=True)
# Ignore new tickets created between the two runs, but compare every existing job.
different=[key for key in outputs['before']['jobs'] if outputs['before']['jobs'][key]!=outputs['after']['jobs'].get(key)]
results['different_existing_jobs']=different
Path('/tmp/factory-cpu-sep14/benchmark.json').write_text(json.dumps(results,indent=2)+'\n')
print('different existing jobs',different,flush=True)
