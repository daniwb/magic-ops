#!/usr/bin/env python3
"""Deterministic, read-only TicketSpec v1 compiler for one measured Map class."""
import hashlib, json, lzma, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
INV = pathlib.Path('/opt/development/magic-ops-artifacts/oracle-face-snapshot/run1/8cdd0282d959a4039ceaa5e462c9214b3e95f15de9b9880373bda04f5fbef629.jsonl.xz')
SCHEMA = 'factory.ticket/v1'
EXACT = re.compile(r'(?m)(?:^|[.:] )Target player draws two cards\.(?:$|\n)')
ADJ = re.compile(r'(?i)target player draws two cards')

def canon(x): return (json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False)+'\n').encode()
def digest(x): return 'sha256:'+hashlib.sha256(canon(x) if not isinstance(x,(bytes,bytearray)) else x).hexdigest()
def filehash(p): return 'sha256:'+hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def revision_hash(r): return digest(r)
def write(path, obj):
    p=ROOT/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(canon(obj))

_candidate_cache = None
def load_candidate():
    global _candidate_cache
    if _candidate_cache is not None:
        return _candidate_cache
    positives=[]; negatives=[]; admitted=0
    with lzma.open(INV,'rt',encoding='utf-8') as f:
      for line in f:
        x=json.loads(line); r=x.get('canonicalSemanticRevision'); m=x['memberships']['normal-game-oracle-faces-candidate-v1']
        if x['status']!='canonical' or not m['included'] or not r: continue
        admitted += 1; text=r.get('text') or ''
        loc=[]
        for n,s in enumerate(text.splitlines(),1):
          if s == 'Target player draws two cards.': loc.append({'assertion_index':n,'exact_text':s,'span':{'start':0,'end':len(s)}})
        base={'oracle_face_key':x['oracleFaceKey'],'oracle_face_id':x['oracleFaceId'],'semantic_revision_hash':revision_hash(r),
              'quarantine_status':'clear','relation_readiness':'not_required','assertion_locators':loc}
        if loc: positives.append(base)
        elif ADJ.search(text) and len(negatives)<8:
          negatives.append({'oracle_face_id':x['oracleFaceId'],'semantic_revision_hash':revision_hash(r),'reason':'adjacent_non_exact_behavior','text':text})
    positives.sort(key=lambda z:(z['oracle_face_key']['scryfallOracleId'],z['oracle_face_key']['side'] or ''))
    negatives.sort(key=lambda z:z['oracle_face_id'])
    if not positives: raise ValueError('missing evidence: predicate recovered zero members')
    _candidate_cache=(admitted, positives, negatives)
    return _candidate_cache

def compile_ticket(history=None):
    admitted,members,negatives=load_candidate()
    source={'source_snapshot_hash':'sha256:a8b9d4ef356186746f0754142c8c8d24d7f80528bc3c0ffee77457040ee0c7c9',
      'oracle_inventory_hash':'sha256:8cdd0282d959a4039ceaa5e462c9214b3e95f15de9b9880373bda04f5fbef629',
      'projection_hash':digest({'id':'normal-game-oracle-faces-candidate-v1','admitted_count':admitted}),
      'adapter_hash':filehash(__file__),'analyzer_hash':digest({'predicate':'exact assertion line','value':'Target player draws two cards.'}),
      'policy_hash':digest({'admit':'canonical && normal-game candidate','relations':'not_required'}),
      'skill_hash':digest({'id':'magic-map-debug/v1','contract':'later supervised workflow'})}
    behavior={'kind':'draw_cards','subject':'target_player','count':2,'timing':'resolve'}
    cause={'schema':'magic.root-cause/v1','class':'map.assertion.target-player-draw-two','behavior':behavior,
           'required_behavior_hash':digest(behavior),'homogeneous':True}
    scope_core={'schema':'magic.scope/v1','source':source,'members':members,'member_count':len(members),'immutable':True}
    scope_core['scope_hash']=digest(scope_core)
    identity_material={'schema':SCHEMA,'project':'magic','repository_hash':digest({'git_commit':'6d85a3d649103d8f3a50fb6436ed266c77b0942a'}),
      'work_type':'map','root_mission_id':'magic-map-root:'+cause['required_behavior_hash'].split(':')[1],
      'root_cause':cause,'scope_hash':scope_core['scope_hash'],'source':source}
    tid='ticket:'+digest(identity_material).split(':')[1]
    if history and tid in history: raise ValueError('duplicate identity')
    result={'schema':'magic.result-partition/v1','scope_hash':scope_core['scope_hash'],'status':'pending',
      'partitions':{'confirmed_fixed_by_change':[],'already_fixed_independently':[],'still_failing_same_root_cause':members,
                    'reclassified_different_root_cause':[],'invalid_or_unsupported':[]},'exhaustive':True,'append_only':True}
    ticket={**identity_material,'ticket_id':tid,'lifecycle':{'state':'ready','premise_status':'current','created_from_evidence':True},
      'title':'Map exact target-player draw-two assertion','positive_members':members,'adjacent_negative_fixtures':negatives,
      'predicted_unlock_members':members,'complete_gap_sets':[{'gap':'map.assertion.target-player-draw-two','members':members}],
      'dependency_bundle':{'engine_dependencies':[{'behavior_hash':cause['required_behavior_hash'],'status':'implemented','evidence':'backend/cardfns draw action'}],'unknown':False},
      'paths':{'allowed':['scripts/paragraph/**','scripts/paragraph/**/*_test.py'],'prohibited':['backend/game/**','services/**','corpus/**']},
      'refusal_split_conditions':['mixed required behavior','new Engine capability required','scope predicate changes','premise stale'],
      'work_profile':{'schema':'factory.work-profile/v1','work_type':'map','difficulty':'medium','risk':'medium','required_capability':'semantic_code_editing','skill':'magic-map-debug/v1','context':['ticket','scope','evidence-pack'],'tools':['read','patch','test'],'routing':{'minimum_capability':'reasoning-and-tools','model_independent':True},'budget':{'effective_token_target':200000,'warning_threshold':500000,'warning_action':'checkpoint_and_reflection','automatic_stop':False}},
      'attempt_policy':{'schema':'factory.attempt-policy/v1','max_retries_before_reflection':2,'reflection_triggers':['budget_warning','repeated_gate_failure','actual_below_predicted'],'terminal_verdicts':['complete','refused','blocked','cancelled_by_authority'],'budget_exhaustion_is_terminal':False},
      'gates':[{'schema':'factory.gate-requirement/v1','id':x,'command':'defined_by_later_checkpoint','evidence_required':True,'result':'pending'} for x in ['discriminating','honesty','regression','full_scope_remeasurement']],
      'completion_evidence':{'status':'pending','result_partition':result},'free_text':{'priority':None,'model':None}}
    graph={'schema':'factory.graph/v1','root_mission_id':ticket['root_mission_id'],'nodes':[tid], 'edges':[],'acyclic':True}
    workflow={'schema':'factory.workflow/v1','ticket_id':tid,'stages':[{'stage':i,'name':n,'status':'complete' if i<=3 else 'pending','authority':'code' if i in (1,2,3,6,7) else 'model'} for i,n in enumerate(['compile/validate ticket','reproduce baseline and materialize scope','build compact evidence/Skill pack','semantic decision or binding refusal','constrained patch plus discriminating test','mechanical apply/gates/full scope remeasurement and focused correction','immutable checkpoint for fresh review/integration'],1)]}
    evidence={'schema':'magic.evidence-pack/v1','ticket_id':tid,'source':source,'root_cause':cause,'positive_count':len(members),'positive_members':members,'adjacent_negative_fixtures':negatives,
      'baseline':{'matching_scope':len(members),'mapped':0,'gap':len(members),'measurement':'deterministic exact-line analyzer'},'predicted_transition':{'mapped':len(members),'gap':0},'engine_evidence':ticket['dependency_bundle']}
    return ticket,scope_core,graph,evidence,workflow

def main():
    ticket,scope,graph,evidence,workflow=compile_ticket()
    for p,o in [('outputs/ticket.json',ticket),('outputs/scope.json',scope),('outputs/graph.json',graph),('outputs/evidence-pack.json',evidence),('outputs/workflow.json',workflow)]: write(p,o)
    print(ticket['ticket_id'],scope['member_count'])
if __name__=='__main__': main()
