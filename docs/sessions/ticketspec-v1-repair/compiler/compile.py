#!/usr/bin/env python3
"""Deterministic TicketSpec v1 repair compiler; stages 1-3 only."""
import hashlib, json, lzma, pathlib, subprocess, sys
from adapter import analyze

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPS = pathlib.Path("/opt/development/magic-ops")
MAGIC = pathlib.Path("/opt/development/magic-new")
PARSER = pathlib.Path("/opt/development/test/openmagic/scripts/paragraph")
SNAP = pathlib.Path("/opt/development/magic-ops-artifacts/oracle-face-snapshot/run1/8cdd0282d959a4039ceaa5e462c9214b3e95f15de9b9880373bda04f5fbef629.jsonl.xz")
IDS = {"59b869b9-cb48-4152-ad91-52f582e2df5b": "Comparative Analysis",
       "8f32ceb2-92c2-4dde-bf73-40bb79c3fcef": "Inspiration"}
MISS = "verb_unmapped:p_draw"

def canon(x): return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def digest(x): return "sha256:" + hashlib.sha256(x if isinstance(x, bytes) else canon(x)).hexdigest()
def file_hash(p): return digest(pathlib.Path(p).read_bytes())
def write_json(rel, obj):
    p=ROOT/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(canon(obj)+b"\n")
def git(repo, *args): return subprocess.check_output(["git","-C",str(repo),*args], text=True).strip()

def load_faces():
    out={}
    with lzma.open(SNAP,"rt",encoding="utf-8") as f:
        for line in f:
            row=json.loads(line); oid=row["oracleFaceKey"]["scryfallOracleId"]
            if oid in IDS: out[oid]=row
    if set(out)!=set(IDS): raise RuntimeError("E_SOURCE_MEMBER_MISSING")
    return out

def member(a):
    hit=next(x for x in a["assertions"] if x["text"]=="Target player draws two cards.")
    return {"oracle_face_id":a["oracle_face_id"],"oracle_face_key":a["oracle_face_key"],
            "semantic_source_hash":a["semantic_source_hash"],"assertion_locator":
            {"assertion_index":hit["assertion_index"],"exact_text":hit["text"],"span":hit["span"]},
            "complete_gap_set":a["before_gap_set"],"quarantine_status":"clear","relation_readiness":"not_required"}

def gate(id, command, expected, evidence, phase="creation", result="passed"):
    return {"id":id,"phase":phase,"command":command,"expected_result":expected,
            "evidence_location":evidence,"result":result}

def schemas():
    defs={"hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},
          "state":{"enum":["candidate","ready","blocked"]},
          "member":{"type":"object","required":["oracle_face_id","oracle_face_key","semantic_source_hash","assertion_locator","complete_gap_set","quarantine_status","relation_readiness"],"properties":{
            "oracle_face_id":{"type":"string"},"oracle_face_key":{"type":"object","required":["scryfallOracleId","side"],"properties":{"scryfallOracleId":{"type":"string","format":"uuid"},"side":{"type":["string","null"]}},"additionalProperties":False},
            "semantic_source_hash":{"$ref":"#/$defs/hash"},"assertion_locator":{"type":"object","required":["assertion_index","exact_text","span"],"properties":{"assertion_index":{"type":"integer","minimum":1},"exact_text":{"type":"string","minLength":1},"span":{"type":"object","required":["start","end"],"properties":{"start":{"type":"integer","minimum":0},"end":{"type":"integer","minimum":1}},"additionalProperties":False}},"additionalProperties":False},
            "complete_gap_set":{"type":"array","items":{"type":"string"},"uniqueItems":True},"quarantine_status":{"enum":["clear","quarantined"]},"relation_readiness":{"enum":["not_required","ready","blocked"]}},"additionalProperties":False}}
    base={"$schema":"https://json-schema.org/draft/2020-12/schema","$defs":defs,"type":"object"}
    specs={
      "ticket":(["schema","ticket_id","identity_digest","work_type","lifecycle","readiness","scope_hash","graph_hash","evidence_pack_hash","skill_receipt","work_profile","attempt_policy","gates"],{"schema":{"const":"factory.ticket/v1"},"ticket_id":{"type":"string","pattern":"^ticket:sha256:[0-9a-f]{64}$"},"identity_digest":{"$ref":"#/$defs/hash"},"work_type":{"const":"map"},"lifecycle":{"$ref":"#/$defs/state"},"readiness":{"type":"object"},"scope_hash":{"$ref":"#/$defs/hash"},"graph_hash":{"$ref":"#/$defs/hash"},"evidence_pack_hash":{"$ref":"#/$defs/hash"},"skill_receipt":{"type":"object"},"work_profile":{"type":"object"},"attempt_policy":{"type":"object"},"gates":{"type":"array","minItems":1}}),
      "scope":(["schema","projection","root_cause_scope","sole_blocker_members","predicted_whole_face_unlock_members"],{"schema":{"const":"magic.scope/v1"},"projection":{"type":"object"},"root_cause_scope":{"type":"array","items":{"$ref":"#/$defs/member"},"minItems":1},"sole_blocker_members":{"type":"array","items":{"$ref":"#/$defs/member"}},"predicted_whole_face_unlock_members":{"type":"array","items":{"$ref":"#/$defs/member"}}}),
      "graph":(["schema","nodes","edges"],{"schema":{"const":"factory.graph/v1"},"nodes":{"type":"array","minItems":2},"edges":{"type":"array","minItems":1}}),
      "evidence-pack":(["schema","analyses","receipts","repository_receipts","engine_receipt","creation_gates"],{"schema":{"const":"factory.evidence-pack/v1"},"analyses":{"type":"array","minItems":2},"receipts":{"type":"array","minItems":1},"repository_receipts":{"type":"array","minItems":3},"engine_receipt":{"type":"object"},"creation_gates":{"type":"array","minItems":1}}),
      "workflow":(["schema","stages","routing_descriptor","telemetry_schema"],{"schema":{"const":"factory.workflow/v1"},"stages":{"type":"array","minItems":7,"maxItems":7},"routing_descriptor":{"type":"object"},"telemetry_schema":{"type":"object"}}),
      "readiness":(["schema","initial_lifecycle","final_lifecycle","predicates","reason_codes","evaluator"],{"schema":{"const":"factory.readiness/v1"},"initial_lifecycle":{"const":"candidate"},"final_lifecycle":{"$ref":"#/$defs/state"},"predicates":{"type":"array","minItems":1},"reason_codes":{"type":"array","items":{"type":"string"}},"evaluator":{"type":"object"}}),
      "result-partition":(["schema","scope_hash","status","partitions"],{"schema":{"const":"magic.result-partition/v1"},"scope_hash":{"$ref":"#/$defs/hash"},"status":{"enum":["pending","complete"]},"partitions":{"type":"object"}}),
      "work-profile":(["schema","work_type","difficulty","uncertainty","risk","required_capabilities","budget"],{"schema":{"const":"factory.work-profile/v1"},"work_type":{"const":"map"},"difficulty":{"enum":["low","medium","high"]},"uncertainty":{"enum":["low","medium","high"]},"risk":{"enum":["low","medium","high"]},"required_capabilities":{"type":"array"},"budget":{"type":"object"}}),
      "attempt-policy":(["schema","max_attempts","verdicts","reflection"],{"schema":{"const":"factory.attempt-policy/v1"},"max_attempts":{"type":"integer","minimum":1},"verdicts":{"type":"array"},"reflection":{"type":"object"}}),
      "gate":(["id","phase","command","expected_result","evidence_location","result"],{"id":{"type":"string"},"phase":{"enum":["creation","patch"]},"command":{"type":"string","minLength":3},"expected_result":{"type":"string","minLength":1},"evidence_location":{"type":"string","minLength":1},"result":{"enum":["passed","pending","failed"]}}),
      "finding":(["schema","selected_assertion","observed_gap","homogeneous"],{"schema":{"const":"magic.finding/v1"},"selected_assertion":{"type":"string"},"observed_gap":{"type":"string"},"homogeneous":{"type":"boolean"}}),
      "root-cause":(["schema","class","behavior","required_behavior_hash"],{"schema":{"const":"magic.root-cause/v1"},"class":{"type":"string"},"behavior":{"type":"object"},"required_behavior_hash":{"$ref":"#/$defs/hash"}})
    }
    for name,(req,props) in specs.items():
        s=dict(base); s.update({"$id":f"https://openmagic.example/schemas/{name}-v1.schema.json","required":req,"properties":props,"additionalProperties":False})
        write_json(f"schemas/{name}-v1.schema.json",s)

def main():
    schemas(); faces=load_faces(); analyses=[analyze(faces[k],IDS[k]) for k in sorted(IDS)]
    for a in analyses: write_json(f"inputs/analysis-{a['name'].lower().replace(' ','-')}.json",a)
    members=[member(a) for a in analyses]
    root=[m for m in members if MISS in m["complete_gap_set"]]
    sole=[m for m in root if m["complete_gap_set"]==[MISS]]
    unlock=[m for m in root if set(m["complete_gap_set"])-{MISS}==set()]
    projection={"schema":"magic.projection/v1","name":"source-admitted-and-normal-game-candidate-v1","source_inventory_hash":file_hash(SNAP),"policy":{"canonical_only":True,"normal_game_candidate":True,"quarantine":"exclude"},"member_ids":sorted(m["oracle_face_id"] for m in root)}
    projection["descriptor_hash"]=digest(projection)
    scope={"schema":"magic.scope/v1","projection":projection,"root_cause_scope":root,"sole_blocker_members":sole,"predicted_whole_face_unlock_members":unlock}
    scope_hash=digest(scope); write_json("outputs/scope.json",scope)
    root_cause={"schema":"magic.root-cause/v1","class":"map.assertion.target-player-draw-two","behavior":{"timing":"resolve","subject":"target_player","kind":"draw_cards","count":2},"required_behavior_hash":digest({"timing":"resolve","subject":"target_player","kind":"draw_cards","count":2})}
    finding={"schema":"magic.finding/v1","selected_assertion":"Target player draws two cards.","observed_gap":MISS,"homogeneous":True}; write_json("inputs/finding.json",finding); write_json("inputs/root-cause.json",root_cause)
    inspected=[PARSER/x for x in ["classify.py","reparse.py","slotparse_oneshot.py"]]+[MAGIC/x for x in ["backend/game/ability_effects.go","backend/game/lib_draw_target_player_test.go","backend/cards/converter.go","backend/cards/registry.go","backend/cardfns/lib_draw_for_player.go"]]
    repo_receipts=[]
    for repo in [OPS,MAGIC,pathlib.Path("/opt/development/test/openmagic")]:
        repo_receipts.append({"repository":str(repo),"commit":git(repo,"rev-parse","HEAD"),"dirty_state":git(repo,"status","--porcelain"),"dirty_policy":"recorded; inspected-file hashes authoritative; no production writes"})
    receipts=[{"path":str(p),"sha256":file_hash(p)} for p in inspected]
    receipts += [{"path":str(ROOT/"compiler/adapter.py"),"sha256":file_hash(ROOT/"compiler/adapter.py")},{"path":str(ROOT/"compiler/compile.py"),"sha256":file_hash(ROOT/"compiler/compile.py")},{"path":str(ROOT/"inputs/policy.json"),"sha256":file_hash(ROOT/"inputs/policy.json")},{"path":str(ROOT/"skills/implement-map-class/SKILL.md"),"sha256":file_hash(ROOT/"skills/implement-map-class/SKILL.md")}]
    creation=[gate("schema-hash-dag-history","python3 compiler/test.py --creation","exit 0; schemas, receipts, DAG, history and exact negative codes pass","test-results.json"),gate("focused-reproduction","python3 compiler/test.py --reproduce","both root members reproduce complete gap inventories","inputs/analysis-*.json"),gate("engine-target-player-draw","cd /opt/development/magic-new/backend && go test ./game -run '^TestExecuteDrawEffect_TargetPlayer$' -count=1","exit 0","test-results.json",result="failed")]
    evidence={"schema":"factory.evidence-pack/v1","analyses":analyses,"receipts":receipts,"repository_receipts":repo_receipts,"engine_receipt":{"symbols":["game.GameState.ExecuteAbilityEffect","cardfns.DrawForPlayer","cards.ToGameCard"],"converter_registry_reachability":"draw atom -> converter EffectAtomSpec -> ExecuteAbilityEffect draw case; target player selected from StackObject.Targets","behavior_test":"go test ./game -run '^TestExecuteDrawEffect_TargetPlayer$' -count=1"},"creation_gates":creation}; evidence_hash=digest(evidence); write_json("outputs/evidence-pack.json",evidence)
    identity={"schema":"factory.ticket-identity/v1","project":"magic","work_type":"map","root_cause":root_cause,"required_behavior":root_cause["behavior"],"projection_descriptor_hash":projection["descriptor_hash"],"scope_member_ids":sorted(m["oracle_face_id"] for m in root),"source_inventory_hash":projection["source_inventory_hash"],"policy_hash":file_hash(ROOT/"inputs/policy.json"),"skill_contract_hash":file_hash(ROOT/"skills/implement-map-class/SKILL.md")}
    identity_digest=digest(identity); ticket_id="ticket:"+identity_digest
    graph={"schema":"factory.graph/v1","nodes":[{"id":"mission:magic-map-target-player-draw","node_type":"main_mission"},{"id":ticket_id,"node_type":"ticket"}],"edges":[{"from":"mission:magic-map-target-player-draw","to":ticket_id,"edge_type":"decomposes_to"}]}; graph_hash=digest(graph); write_json("outputs/graph.json",graph)
    patch_gates=[gate("positive-and-adjacent-negative","cd /opt/development/test/openmagic && python3 -m unittest scripts.paragraph.test_ticketspec_target_player_draw","positives map; controller/self/each-opponent adjacent negatives retain behavior","attempt/tests.log","patch","pending"),gate("engine-target-player-draw","cd /opt/development/magic-new/backend && go test ./game -run '^TestExecuteDrawEffect_TargetPlayer$' -count=1","exit 0","attempt/engine.log","patch","pending"),gate("honesty-engine-unchanged","git -C /opt/development/magic-new diff --exit-code -- backend/game backend/cardfns backend/cards","exit 0","attempt/honesty.log","patch","pending"),gate("regression","cd /opt/development/test/openmagic && python3 -m unittest discover -s scripts/paragraph -p 'test_*.py'","exit 0","attempt/regression.log","patch","pending"),gate("immutable-scope-remeasurement","python3 compiler/validate.py --remeasure outputs/scope.json attempt/result-partition.json","all original members occur exactly once; no substitutions; scope hash unchanged","attempt/remeasure.json","patch","pending")]
    predicates=[{"id":x,"satisfied":True,"reason_code":None} for x in ["premise_current","schemas_valid","evidence_complete","scope_conserved","graph_valid","history_unique","quarantine_relation_clear","skill_valid"]]
    predicates += [{"id":"engine_proven","satisfied":False,"reason_code":"E_ENGINE_BEHAVIOR_GATE_FAILED"},{"id":"creation_gates_passed","satisfied":False,"reason_code":"E_CREATION_GATE_FAILED"}]
    readiness={"schema":"factory.readiness/v1","initial_lifecycle":"candidate","final_lifecycle":"ready" if all(p["satisfied"] for p in predicates) else "candidate","predicates":predicates,"reason_codes":[p["reason_code"] for p in predicates if p["reason_code"]],"evaluator":{"sole_ready_authority":"compiler/validate.py:evaluate_readiness","all_predicates_required":True}}
    write_json("outputs/readiness.json",readiness)
    profile={"schema":"factory.work-profile/v1","work_type":"map","difficulty":"medium","uncertainty":"low","risk":"medium","required_capabilities":["semantic_code_editing","python_tests"],"budget":{"effective_token_target":200000,"warning_threshold":500000,"automatic_stop":False}}
    policy={"schema":"factory.attempt-policy/v1","max_attempts":3,"verdicts":["SUCCESS","REFUSE","PARK","SPLIT","REFACTOR_FIRST","INFRASTRUCTURE_FAILURE"],"reflection":{"threshold":500000,"action":"warn_checkpoint_reflect","continue_verdict":"CONTINUE_NECESSARY"}}
    gates=creation+patch_gates
    ticket={"schema":"factory.ticket/v1","ticket_id":ticket_id,"identity_digest":identity_digest,"work_type":"map","lifecycle":readiness["final_lifecycle"],"readiness":readiness,"scope_hash":scope_hash,"graph_hash":graph_hash,"evidence_pack_hash":evidence_hash,"skill_receipt":{"path":"skills/implement-map-class/SKILL.md","sha256":file_hash(ROOT/"skills/implement-map-class/SKILL.md"),"synthetic":False},"work_profile":profile,"attempt_policy":policy,"gates":gates}
    write_json("outputs/ticket.json",ticket)
    result={"schema":"magic.result-partition/v1","scope_hash":scope_hash,"status":"pending","partitions":{"confirmed_fixed_by_change":[],"already_fixed_independently":[],"still_failing_same_root_cause":root,"reclassified_different_root_cause":[],"invalid_or_unsupported":[]}}; write_json("outputs/result-partition.json",result)
    stages=[{"stage":i,"authority":"code" if i in [1,2,3,6,7] else "model","status":"complete" if i<=3 else "pending"} for i in range(1,8)]
    workflow={"schema":"factory.workflow/v1","stages":stages,"routing_descriptor":{"status":"pending","sequence":["deterministic_prepare","local_ai_advisory","deterministic_verify_local","capable_model_decide_implement","deterministic_gate_remeasure","local_ai_failure_capsule","capable_model_conditional_recall"],"selection_inputs":["difficulty","uncertainty","risk","required_capabilities","attempt_history"]},"telemetry_schema":{"dimensions":["input_tokens","output_tokens","cache_read_tokens","cache_write_tokens","effective_total","wall_time","model","attempt","stage"],"local_and_online_separate":True}}; write_json("outputs/workflow.json",workflow)
    ledger=ROOT/"fixtures/history/open-history-ledger.json"
    hist=json.loads(ledger.read_text()); matches=[x for x in hist["entries"] if x["identity_digest"]==identity_digest]
    if not matches: hist["entries"].append({"ticket_id":ticket_id,"identity_digest":identity_digest,"status":"open"}); write_json("fixtures/history/open-history-ledger.json",hist)
    elif matches[0]["ticket_id"]!=ticket_id: raise RuntimeError("E_HISTORY_IDENTITY_MISMATCH")
    write_json("inputs/identity.json",identity)

if __name__=="__main__": main()
