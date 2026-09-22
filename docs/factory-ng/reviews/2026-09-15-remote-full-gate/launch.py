from pathlib import Path
import json,subprocess,shutil,shlex,time
stage=Path('/tmp/remote-fullgate-stage').read_text();stage=Path(stage)
review=Path('/opt/development/magic-ops/docs/factory-ng/reviews/2026-09-15-remote-full-gate')
shutil.copyfile(review/'replay.py',stage/'replay.py')
remote='/data/factory-ng/trials/'+stage.name
host='dani@192.168.1.251'; options=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',host]
def ssh(args,timeout=300):return subprocess.run(options+[shlex.join(args)],check=True,timeout=timeout)
ssh(['mkdir','-p',remote])
start=time.monotonic()
subprocess.run(['rsync','-a','--timeout=60','-e','ssh -o BatchMode=yes -o ConnectTimeout=8',str(stage)+'/',host+':'+remote+'/'],check=True,timeout=300)
# A private copy prevents trial cache maintenance from touching live jobs.
ssh(['cp','-a','--reflink=auto','/data/factory-ng/build-cache/.',remote+'/cache/'])
manifest=json.loads((stage/'manifest.json').read_text()); name='factory-ng-'+stage.name
cmd=['podman','run','--rm','--name',name,'--network=none','--timeout=10800','--memory=16g','--pids-limit=512','--label=factory-ng-role=fullgate-trial',
 '-v',remote+':/trial:Z','-v',remote+'/ops:/opt/development/magic-ops:Z',
 '-v',remote+'/tmp:/tmp:Z','-v','/data/factory-ng/toolchain:/usr/local/go:ro,z',
 '-v','/data/factory-ng/gomod:/cache/gomod:z','-e','GOTOOLCHAIN=local','-e','GOMODCACHE=/cache/gomod',
 '-e','GOPROXY=off','-e','GO_CACHE_ROOT=/trial/cache','-e','GOMAXPROCS=4','-e','GOFLAGS=-p=4',
 '-w','/opt/development/magic-ops',manifest['image'],'sh','-c',
 'ln -s /usr/local/go/bin/go /usr/local/bin/go && exec python3 scripts/factory_ng_quiet.py --exec python3 /trial/replay.py']
meta={'host':host,'remote_directory':remote,'container_name':name,'prepare_seconds':round(time.monotonic()-start,3),'command':cmd,'started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
(review/'launch.json').write_text(json.dumps(meta,indent=2)+'\n')
print('Prepared',meta['prepare_seconds'],'seconds',remote,flush=True)
try:
 result=subprocess.run(options+[shlex.join(cmd)],timeout=11000)
 print('Container exit',result.returncode,flush=True)
finally:
 subprocess.run(['rsync','-a','--timeout=60','-e','ssh -o BatchMode=yes -o ConnectTimeout=8',host+':'+remote+'/output/',str(review)+'/'],check=True,timeout=180)
