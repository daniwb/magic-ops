#!/usr/bin/env python3
"""Build final content manifest after all deterministic creation gates."""
import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]; OPS=pathlib.Path("/opt/development/magic-ops")
def h(p):return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def git(repo,*args):return subprocess.check_output(["git","-C",str(repo),*args],text=True).strip()
files=[]
for p in sorted(ROOT.rglob("*")):
 if p.is_file() and p.name!="manifest.json": files.append({"path":str(p.relative_to(ROOT)),"sha256":h(p),"bytes":p.stat().st_size})
before=pathlib.Path("/tmp/ticketspec-v1.before.sha256").read_text()
now=subprocess.check_output("find docs/sessions/ticketspec-v1 -type f -print0 | sort -z | xargs -0 sha256sum",shell=True,text=True,cwd=OPS)
manifest={"schema":"factory.session-manifest/v1","status":"complete","ticket_lifecycle":json.loads((ROOT/"outputs/readiness.json").read_text())["final_lifecycle"],"completed_stages":[1,2,3],"pending_stages":[4,5,6,7],"artifacts":files,"repositories":[{"path":str(x),"commit":git(x,"rev-parse","HEAD"),"dirty_state":git(x,"status","--porcelain")} for x in [OPS,pathlib.Path("/opt/development/magic-new"),pathlib.Path("/opt/development/test/openmagic")]],"rerun_commands":["cd /opt/development/magic-ops/docs/sessions/ticketspec-v1-repair && python3 compiler/compile.py","cd /opt/development/magic-ops/docs/sessions/ticketspec-v1-repair && python3 compiler/validate.py","cd /opt/development/magic-ops/docs/sessions/ticketspec-v1-repair && python3 compiler/test.py","cd /opt/development/magic-new/backend && go test ./game -run '^TestExecuteDrawEffect_TargetPlayer$' -count=1"],"no_production_mutation":{"write_allowlist":[str(ROOT)+"/**"],"original_ticketspec_v1_byte_identical":before==now,"original_tree_before_digest":"sha256:"+hashlib.sha256(before.encode()).hexdigest(),"original_tree_after_digest":"sha256:"+hashlib.sha256(now.encode()).hexdigest(),"map_fix_implemented":False,"model_route_invoked":False,"services_or_databases_mutated":False}}
(ROOT/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n")
if before!=now:raise SystemExit("E_ORIGINAL_PROTOTYPE_MUTATED")
print("OK manifest")
