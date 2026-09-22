"""Replay the finite reviewed conflict snapshot; never touches canonical source."""
import hashlib,json,re,subprocess,tempfile
from pathlib import Path
OPS=Path('/opt/development/magic-ops'); REVIEW=Path(__file__).resolve().parent
OUT=REVIEW/'selected';OUT.mkdir(exist_ok=True)
if (OUT/'resolutions.json').exists():raise SystemExit('Reviewed artifacts already exist; preserve their hashes and use a new review directory.')
rows=json.loads((REVIEW/'audit-diff3.json').read_text())
selected_receipts=set(json.loads((REVIEW/'integration-selection.json').read_text())['receipts'])
clone=Path(tempfile.mkdtemp(prefix='ng-reviewed-resolutions-'))
def git(*args):
 return subprocess.run(['git','-C',str(clone),*args],capture_output=True,text=True)
def must(*args):
 r=git(*args);assert not r.returncode,r.stderr;return r.stdout
base=rows[0]['base']
must('clone','--shared','/opt/development/test/openmagic',str(clone))
must('checkout','--detach',base);must('config','merge.conflictStyle','diff3')
must('config','user.name','Factory NG Operator');must('config','user.email','factory-ng@local')
manifest={'schema':'factory.reviewed-merge-resolutions/v1','resolutions':{},'deferred':[]}
def digest(p):return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
pattern=re.compile(r'^<<<<<<< [^\n]*\n(.*?)^\|\|\|\|\|\|\| [^\n]*\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]*\n',re.M|re.S)
for row in rows:
 key=row['ticket']
 if row['receipt'] not in selected_receipts:continue
 if any(code in key for code in ('9e24f96767','a737105295')):
  manifest['deferred'].append({'ticket':key,'reason': 'Self-pump default contradicts the untargeted-all negative assertion for the same no-target input; needs an explicit self discriminator.' if '9e24' in key else 'Value is recorded before successful exile and only cleared on consumption; needs resolution-scoped state and a failed-exile regression.'});continue
 obs=json.loads((OPS/row['receipt']).read_text()); original=OPS/row['patch']
 assert digest(original)==obs['execution']['candidate_patch_sha256']
 r=git('am','--3way',str(original));assert r.returncode!=0
 files=must('diff','--name-only','--diff-filter=U').splitlines();assert set(files)==set(row['conflicts'])
 for f in files:
  p=clone/f;s=p.read_text()
  def resolve(m):
   # Require the exact reviewed hunk, not a generic automatic union policy.
   ours,ancestor,theirs=m.groups()
   reviewed=[pattern.match(block+'\n').groups() for block in row['conflicts'][f]]
   assert any(ancestor==b and theirs==t for o,b,t in reviewed), 'candidate side differs from reviewed hunk'
   (OUT/(key.split('/')[-2].replace(':','-')+'-composed-conflict.txt')).write_text(s)
   if ancestor=='':
    # Keep comments immediately adjacent to the function they document.
    if 'e7617de98a' in key:return theirs+ours
    return ours+theirs
   assert '36523aeef0' in key and ancestor=='\t\t\treturn nil\n'
   return '\t\t\tgroup, _ := effectValue["group_filter"].(string)\n\t\t\tall, _ := effectValue["all"].(bool)\n\t\t\tif group == "" && !all {\n\t\t\t\treturn nil\n\t\t\t}\n'
  s,n=pattern.subn(resolve,s);assert n==len(row['conflicts'][f]);p.write_text(s);must('add',f)
 if 'd32bfbcd7a' in key:
  p=clone/'backend/game/ability_effects.go'
  text=p.read_text();old='gs.destroyAllMatching(controller, filter, "", false, "", false)'
  assert text.count(old)==1
  p.write_text(text.replace(old,'gs.destroyAllMatching(controller, filter, "", false, "", false, "")'))
  must('add','backend/game/ability_effects.go')
 changed=must('diff','--cached','--name-only').splitlines()
 old_paths=set(re.findall(r'^diff --git a/(\S+) b/',original.read_text(),re.M))
 assert set(changed)<=old_paths,(key,changed,old_paths)
 gos=[str(clone/f) for f in changed if f.endswith('.go')]
 r=subprocess.run(['/usr/local/go/bin/gofmt','-w',*gos],capture_output=True,text=True);assert not r.returncode,r.stderr
 must('add',*changed);must('diff','--cached','--check');must('am','--continue')
 slug=key.removeprefix('ticket:').replace('/','-')
 patch=OUT/(slug+'.patch');patch.write_text(must('format-patch','-1','--stdout'))
 manifest['resolutions'][key]={'ticket_sha256':obs['ticket']['sha256'],'original_patch_sha256':digest(original),'patch':str(patch.relative_to(OPS)),'patch_sha256':digest(patch),'source_revision':base,'reason':'Operator reviewed exact diff3 hunk: preserve both independent additions, with no removed semantic gates.' if '36523aeef0' not in key else 'Preserve both explicit group_filter and all=true exceptions; absent target with neither flag remains a no-op. Original tests retained.','original_receipt':row['receipt'],'changed_paths':changed}
 # Retain the composed prefix so each resolved patch builds on the previous one.
(OUT/'resolutions.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Prepared',len(manifest['resolutions']),'resolved patches;',len(manifest['deferred']),'semantic deferrals; clone',clone,flush=True)
