import hashlib,json,re,subprocess,tempfile
from pathlib import Path
ops=Path('/opt/development/magic-ops');out=ops/'docs/factory-ng/reviews/2026-09-09-conflict-recovery/counter';out.mkdir(exist_ok=True)
if (out/'resolutions.json').exists():raise SystemExit('Preserve existing reviewed artifacts; use a new output directory.')
row=next(r for r in json.loads((out.parent/'audit-diff3.json').read_text()) if '82dee1907b' in r['ticket'])
obs=json.loads((ops/row['receipt']).read_text());clone=Path(tempfile.mkdtemp(prefix='ng-counter-resolution-'))
def git(*args):return subprocess.run(['git','-C',str(clone),*args],capture_output=True,text=True)
def must(*args):
 r=git(*args);assert not r.returncode,r.stderr;return r.stdout
must('clone','--shared','/opt/development/test/openmagic',str(clone));base=must('rev-parse','HEAD').strip()
must('config','merge.conflictStyle','diff3');must('config','user.name','Factory NG Operator');must('config','user.email','factory-ng@local')
r=git('am','--3way',str(ops/row['patch']))
if r.returncode:
 files=must('diff','--name-only','--diff-filter=U').splitlines();assert files==['backend/game/ability_effects.go']
 p=clone/files[0];text=p.read_text();pattern=re.compile(r'^<<<<<<< [^\n]*\n(.*?)^\|\|\|\|\|\|\| [^\n]*\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]*\n',re.M|re.S)
 def resolve(m):
  ours,base,theirs=m.groups();assert base=='' and 'func (gs *GameState) DealDamageEqualToCounterCount(' in theirs
  return ours+theirs
 text,n=pattern.subn(resolve,text);assert n==1;p.write_text(text);must('add',files[0]);must('am','--continue')
p=clone/'backend/game/ability_effects.go';text=p.read_text()
old='gs.ProcessTriggeredAbilities(CreateDamageEvent(source, targetCard, amount, controller))\n\treturn amount, nil\n}'
assert text.count(old)==1
text=text.replace(old,'if err := gs.executeDamageEffect(controller, source, map[string]interface{}{"amount": amount}, []Target{target}); err != nil {\n\t\treturn 0, err\n\t}\n\treturn amount, nil\n}')
text=text.replace('Returns\n// the resolved amount alongside dispatching the damage event so callers\n// can observe exactly what got dealt.','Returns\n// the resolved counter amount after using the ordinary damage pipeline,\n// including prevention, replacement effects and damage event dispatch.')
p.write_text(text)
p=clone/'backend/game/factory_ng_82dee1907b_test.go';text=p.read_text();needle='\tamount, err = gs.DealDamageEqualToCounterCount(src, 0, target, src, CounterType("charge"))'
assert needle in text
text=text.replace(needle,'\tif victim.Damage != 3 {\n\t\tt.Fatalf("damage must reach the creature, got %d want 3", victim.Damage)\n\t}\n\n'+needle)
p.write_text(text)
subprocess.run(['/usr/local/go/bin/gofmt','-w',str(p),str(clone/'backend/game/ability_effects.go')],check=True)
must('add','backend/game/ability_effects.go','backend/game/factory_ng_82dee1907b_test.go');must('diff','--cached','--check');must('commit','--amend','--no-edit')
patch=out/'damage-counter-resolved.patch';patch.write_text(must('format-patch','-1','--stdout'))
def digest(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'schema':'factory.reviewed-merge-resolutions/v1','resolutions':{row['ticket']:{'ticket_sha256':obs['ticket']['sha256'],'original_patch_sha256':obs['execution']['candidate_patch_sha256'],'patch':str(patch.relative_to(ops)),'patch_sha256':digest(patch),'source_revision':base,'reason':'Operator repaired proven event-only damage defect by delegating to executeDamageEffect; original named test now also asserts actual marked damage. No model retry or counter reset.','original_receipt':row['receipt']}}}
(out/'resolutions.json').write_text(json.dumps(manifest,indent=2)+'\n');(out/'clone.txt').write_text(str(clone)+'\n')
print(clone,flush=True)
with (out/'focused.log').open('w') as f:
 r=subprocess.run([str(ops/'scripts/go-cache-run.sh'),'test','./game','-run','^TestFactoryNGDamageAmountCounterCount$','-count=1'],cwd=clone/'backend',stdout=f,stderr=subprocess.STDOUT)
print('counter focused exit',r.returncode,flush=True)
