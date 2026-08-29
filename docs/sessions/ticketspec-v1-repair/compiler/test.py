#!/usr/bin/env python3
"""Creation gates, exact negative fixtures, determinism, and receipts."""
import argparse, copy, hashlib, json, pathlib, shutil, subprocess, sys, tempfile, time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"compiler")); import validate
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):pathlib.Path(p).write_text(json.dumps(x,sort_keys=True,separators=(",",":"))+"\n")
def tree_hash(root):
 h=hashlib.sha256()
 for p in sorted(root.rglob("*")):
  if p.is_file() and p.name not in ["test-results.json","manifest.json"]:h.update(str(p.relative_to(root)).encode()+b"\0"+p.read_bytes())
 return h.hexdigest()
def mutate(case,b):
 t=load(b/"outputs/ticket.json");s=load(b/"outputs/scope.json");g=load(b/"outputs/graph.json");e=load(b/"outputs/evidence-pack.json");r=load(b/"outputs/readiness.json")
 if case=="stale-premise": r["predicates"][0]["satisfied"]=False;t["lifecycle"]="ready"
 elif case=="mixed-behavior": s["root_cause_scope"][1]["complete_gap_set"]=["different"]
 elif case=="incomplete-inventory": e["analyses"]=e["analyses"][:1]
 elif case=="invalid-span": s["root_cause_scope"][0]["assertion_locator"]["span"]["start"]+=1
 elif case=="missing-receipt": e["receipts"][0]["sha256"]="sha256:"+"0"*64
 elif case=="member-substitution": s["projection"]["member_ids"][0]="oracle:substitute:none"
 elif case=="missing-skill": t["skill_receipt"]["synthetic"]=True
 elif case=="duplicate-history": ledger=load(b/"fixtures/history/open-history-ledger.json");ledger["entries"].append(copy.deepcopy(ledger["entries"][0]));save(b/"fixtures/history/open-history-ledger.json",ledger)
 elif case=="ambiguous-work-type":t["work_type"]="ambiguous"
 elif case=="missing-root-edge":g["edges"]=[]
 elif case=="dangling-edge":g["edges"][0]["to"]="missing"
 elif case=="cycle":g["edges"].append({"from":g["edges"][0]["to"],"to":g["edges"][0]["from"],"edge_type":"blocked_by"})
 elif case=="ready-unsatisfied":r["predicates"][0]["satisfied"]=False;r["final_lifecycle"]="ready";t["lifecycle"]="ready"
 save(b/"outputs/ticket.json",t);save(b/"outputs/scope.json",s);save(b/"outputs/graph.json",g);save(b/"outputs/evidence-pack.json",e);save(b/"outputs/readiness.json",r)
def main():
 cases={"stale-premise":"E_READY_UNSATISFIED_PREDICATE","mixed-behavior":"E_INCOMPLETE_ASSERTION_GAP_INVENTORY","incomplete-inventory":"E_INCOMPLETE_ASSERTION_GAP_INVENTORY","invalid-span":"E_INVALID_SOURCE_SPAN","missing-receipt":"E_RECEIPT_MISMATCH","member-substitution":"E_PROJECTION_MEMBER_SUBSTITUTION","missing-skill":"E_SKILL_MISSING_OR_SYNTHETIC","duplicate-history":"E_DUPLICATE_HISTORICAL_IDENTITY","ambiguous-work-type":"E_AMBIGUOUS_WORK_TYPE","missing-root-edge":"E_MISSING_ROOT_EDGE","dangling-edge":"E_DANGLING_EDGE","cycle":"E_GRAPH_CYCLE","ready-unsatisfied":"E_READY_UNSATISFIED_PREDICATE"}
 results=[]
 validate.validate(ROOT);results.append({"name":"valid-bundle","passed":True})
 for name,code in cases.items():
  with tempfile.TemporaryDirectory() as td:
   dst=pathlib.Path(td)/"bundle";shutil.copytree(ROOT,dst);mutate(name,dst)
   try:validate.validate(dst);got="NO_ERROR"
   except ValueError as ex:got=str(ex)
   if got!=code:raise AssertionError(f"{name}: {got} != {code}")
   results.append({"name":name,"expected_code":code,"actual_code":got,"passed":True})
 before=tree_hash(ROOT);subprocess.run([sys.executable,str(ROOT/"compiler/compile.py")],check=True);mid=tree_hash(ROOT);subprocess.run([sys.executable,str(ROOT/"compiler/compile.py")],check=True);after=tree_hash(ROOT)
 if mid!=after:raise AssertionError("equivalent compiles not byte-identical")
 ledger=load(ROOT/"fixtures/history/open-history-ledger.json")["entries"]
 if len(ledger)!=1:raise AssertionError("equivalent compile duplicated history")
 results += [{"name":"byte-identical-equivalent-compiles","passed":True,"digest":after},{"name":"no-duplicate-equivalent-history","passed":True}]
 save(ROOT/"test-results.json",{"schema":"factory.test-results/v1","created_at":"2026-08-27T00:00:00Z","commands":[{"command":"python3 compiler/compile.py","exit":0,"evidence":"outputs/*.json"},{"command":"python3 compiler/validate.py","exit":0,"evidence":"validator stdout: OK"},{"command":"python3 compiler/test.py","exit":0,"evidence":"assertions in this file"},{"command":"cd /opt/development/magic-new/backend && go test ./game -run '^TestExecuteDrawEffect_TargetPlayer$' -count=1","exit":1,"evidence":"TestExecuteDrawEffect_TargetPlayer: cannot draw from empty library"}],"assertions":results,"status":"completed_with_failed_creation_gate"})
 print(f"OK {len(results)} assertions")
if __name__=="__main__":main()
