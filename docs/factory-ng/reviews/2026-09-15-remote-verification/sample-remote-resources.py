import json,subprocess,time
from pathlib import Path
samples=[]
for n in range(16):
 ids=subprocess.check_output(['podman','ps','-q','--filter','label=factory-ng-role=verification'],text=True).split()
 sample={'monotonic':time.monotonic(),'jobs':[]}
 if ids:
  result=subprocess.run(['podman','inspect',*ids],text=True,capture_output=True)
  try: info=json.loads(result.stdout)
  except ValueError: info=[]
  for row in info:
   pid=row['State']['Pid']; name=row['Name']
   try:
    group=(Path('/proc')/str(pid)/'cgroup').read_text().strip().split('::')[-1]
    root=Path('/sys/fs/cgroup'+group)
    cpu=dict(line.split() for line in (root/'cpu.stat').read_text().splitlines())
    config=json.loads((Path('/data/factory-ng/jobs')/name.removeprefix('factory-ng-')/'remote-job.json').read_text())
    sample['jobs'].append({'name':name,'slot':config.get('slot',0),'cpus':config['cpus'],
                          'cpu_usec':int(cpu['usage_usec']),
                          'memory_bytes':int((root/'memory.current').read_text()),
                          'memory_peak_bytes':int((root/'memory.peak').read_text())})
   except (OSError,KeyError,ValueError):pass
 samples.append(sample)
 if n<15:time.sleep(2)
print(json.dumps(samples,indent=2))
