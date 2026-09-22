import json, pathlib, shutil, subprocess, tempfile, re, hashlib, shlex
ops=pathlib.Path('/opt/development/magic-ops'); src=pathlib.Path('/opt/development/test/openmagic')
review=ops/'docs/factory-ng/reviews/2026-09-15-remote-full-gate'
ref=pathlib.Path('/tmp/remote-full-gate-reference-path').read_text(); receipt=json.loads((ops/ref).read_text())
shutil.copyfile(ops/ref,review/'local-reference.json')
result=receipt['source']['result_commit']
def git(*args): return subprocess.check_output(['git','-C',str(src),*args],text=True).strip()
assert git('show','-s','--format=%s',result)=='factory-ng: import fully gated corpus wave'
revision=git('rev-parse',result+'^'); expected_tree=git('rev-parse',result+'^{tree}')
stage=pathlib.Path(tempfile.mkdtemp(prefix='factory-ng-fullgate-trial-')); (stage/'ops').mkdir(); (stage/'output').mkdir(); (stage/'tmp').mkdir(); (stage/'cache').mkdir()
subprocess.run(['git','clone','--quiet','--no-hardlinks',str(src),str(stage/'source')],check=True)
subprocess.run(['git','-C',str(stage/'source'),'checkout','--quiet','--detach',revision],check=True)
shutil.copyfile(src/'corpus/AtomicCards.json.gz',stage/'source/corpus/AtomicCards.json.gz')
shutil.copytree(ops/'scripts',stage/'ops/scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc','archive'))
inputs={}
def copy_input(relative):
 path=ops/relative
 if not path.is_file(): return
 if not path.resolve().is_relative_to(ops): raise ValueError(relative)
 target=stage/'ops'/relative; target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
 inputs[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
parents=[]
for relative in receipt['parents']:
 if not relative.startswith('docs/'): continue
 copy_input(relative); parents.append(relative)
 obs=json.loads((ops/relative).read_text()); ticket=obs['ticket']['path'];copy_input(ticket)
 for match in re.findall(r'docs/factory-ng/[\w./-]+',(ops/ticket).read_text()): copy_input(match)
commands=[]
for g in receipt['gates']:
 if g['id'] in ['reparse-flip','reparse-import','go-build','game-tests','focused-go','full-sharded-suite']:
  command=shlex.split(g['command'])
  if g['id'].startswith('reparse-'): command[0]='python3'
  commands.append({'id':g['id'],'argv':command,'local_elapsed_ms':g['elapsed_ms']})
policy=json.loads((ops/'config/factory-ng-policy.json').read_text());policy['resources']={'cpu_affinity':list(range(16,24)),'nice':10};policy['integration']['automatic']=False;policy['integration']['push_when_full_gate_green']=False
(stage/'ops/config').mkdir();(stage/'ops/state').mkdir();(stage/'ops/config/factory-ng-policy.json').write_text(json.dumps(policy))
manifest={'revision':revision,'expected_result_commit':result,'expected_tree':expected_tree,'parents':parents,'commands':commands,'inputs':inputs,'corpus_sha256':hashlib.sha256((src/'corpus/AtomicCards.json.gz').read_bytes()).hexdigest(),'cpus':list(range(16,24)),'go_parallelism':4,'image':policy['verification']['remote']['image'],'reference_path':ref,'local_semantic_elapsed_ms':sum(g['elapsed_ms'] for g in receipt['gates'] if g['id'].startswith('composed-ticket-'))}
(stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');shutil.copyfile(stage/'manifest.json',review/'manifest.json');pathlib.Path('/tmp/remote-fullgate-stage').write_text(str(stage));print(stage);print(json.dumps({k:manifest[k] for k in ['revision','expected_tree','cpus','local_semantic_elapsed_ms','commands']},indent=2))
