#!/usr/bin/env python3
"""Schema and cross-artifact validator with stable machine error codes."""
import argparse, hashlib, json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def canon(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(x): return "sha256:"+hashlib.sha256(canon(x)).hexdigest()
def fail(code): raise ValueError(code)
def load(p): return json.loads(pathlib.Path(p).read_text())

def validate(bundle=ROOT):
    try: import jsonschema
    except ImportError: fail("E_DEPENDENCY_JSONSCHEMA")
    names=["ticket","scope","graph","evidence-pack","workflow","readiness","result-partition"]
    docs={n:load(bundle/"outputs"/(n+".json")) for n in names}
    if docs["ticket"].get("work_type") != "map": fail("E_AMBIGUOUS_WORK_TYPE")
    if len(docs["evidence-pack"].get("analyses",[])) < len(docs["scope"].get("root_cause_scope",[])): fail("E_INCOMPLETE_ASSERTION_GAP_INVENTORY")
    if not docs["graph"].get("edges"): fail("E_MISSING_ROOT_EDGE")
    for n,d in docs.items():
        try: jsonschema.Draft202012Validator(load(ROOT/"schemas"/(n+"-v1.schema.json")),format_checker=jsonschema.FormatChecker()).validate(d)
        except jsonschema.ValidationError: fail("E_SCHEMA_"+n.upper().replace("-","_"))
    t,s,g,e,w,r,p=[docs[n] for n in names]
    embedded=[("work-profile",t["work_profile"]),("attempt-policy",t["attempt_policy"]),("finding",load(bundle/"inputs/finding.json")),("root-cause",load(bundle/"inputs/root-cause.json"))]
    embedded += [("gate",x) for x in t["gates"]]
    for n,d in embedded:
        try: jsonschema.Draft202012Validator(load(ROOT/"schemas"/(n+"-v1.schema.json")),format_checker=jsonschema.FormatChecker()).validate(d)
        except jsonschema.ValidationError: fail("E_SCHEMA_"+n.upper().replace("-","_"))
    if t["identity_digest"] != digest(load(bundle/"inputs/identity.json")): fail("E_IDENTITY_DIGEST")
    if t["ticket_id"] != "ticket:"+t["identity_digest"]: fail("E_TICKET_ID")
    ids=[m["oracle_face_id"] for m in s["root_cause_scope"]]
    if ids != s["projection"]["member_ids"]: fail("E_PROJECTION_MEMBER_SUBSTITUTION")
    analyses={a["oracle_face_id"]:a for a in e["analyses"]}
    if set(ids)!=set(analyses): fail("E_INCOMPLETE_ASSERTION_GAP_INVENTORY")
    for m in s["root_cause_scope"]:
        a=analyses[m["oracle_face_id"]]; loc=m["assertion_locator"]; raw=a["semantic_source"].encode()
        if raw[loc["span"]["start"]:loc["span"]["end"]].decode()!=loc["exact_text"]: fail("E_INVALID_SOURCE_SPAN")
        if m["complete_gap_set"]!=a["before_gap_set"]: fail("E_INCOMPLETE_ASSERTION_GAP_INVENTORY")
    receipts={x["path"]:x["sha256"] for x in e["receipts"]}
    for path,h in receipts.items():
        pth=pathlib.Path(path)
        if not pth.exists() or "sha256:"+hashlib.sha256(pth.read_bytes()).hexdigest()!=h: fail("E_RECEIPT_MISMATCH")
    skill=t["skill_receipt"]
    if skill.get("synthetic") or not (bundle/skill["path"]).exists(): fail("E_SKILL_MISSING_OR_SYNTHETIC")
    nodes={n["id"] for n in g["nodes"]}
    for edge in g["edges"]:
        if edge["from"] not in nodes or edge["to"] not in nodes: fail("E_DANGLING_EDGE")
    if not any(x["node_type"]=="main_mission" for x in g["nodes"]) or not any(x["edge_type"]=="decomposes_to" for x in g["edges"]): fail("E_MISSING_ROOT_EDGE")
    adj={n:[] for n in nodes}
    for x in g["edges"]: adj[x["from"]].append(x["to"])
    seen=set(); active=set()
    def visit(n):
        if n in active: fail("E_GRAPH_CYCLE")
        if n in seen:return
        active.add(n)
        for q in adj[n]:visit(q)
        active.remove(n);seen.add(n)
    for n in nodes:visit(n)
    if t["lifecycle"]=="ready" and (r["initial_lifecycle"]!="candidate" or not all(x["satisfied"] for x in r["predicates"])): fail("E_READY_UNSATISFIED_PREDICATE")
    if t["lifecycle"]!=r["final_lifecycle"]: fail("E_LIFECYCLE_MISMATCH")
    ledger=load(bundle/"fixtures/history/open-history-ledger.json")["entries"]
    if len([x for x in ledger if x["identity_digest"]==t["identity_digest"]])!=1: fail("E_DUPLICATE_HISTORICAL_IDENTITY")
    allp=sum(p["partitions"].values(),[])
    if sorted(x["oracle_face_id"] for x in allp)!=sorted(ids): fail("E_RESULT_PARTITION_CONSERVATION")
    return "OK"

def evaluate_readiness(predicates):
    return "ready" if predicates and all(p["satisfied"] for p in predicates) else "candidate"

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--remeasure",nargs=2);ap.add_argument("bundle",nargs="?",default=str(ROOT));a=ap.parse_args()
    try:
        if a.remeasure:
            scope,part=map(load,a.remeasure); ids=[x["oracle_face_id"] for x in scope["root_cause_scope"]]; got=[x["oracle_face_id"] for v in part["partitions"].values() for x in v]
            if sorted(ids)!=sorted(got) or len(got)!=len(set(got)):fail("E_RESULT_PARTITION_CONSERVATION")
            print("OK")
        else: print(validate(pathlib.Path(a.bundle)))
    except ValueError as ex: print(str(ex),file=sys.stderr);sys.exit(1)
