#!/usr/bin/env python3
"""Candidate-only deterministic compiler. It cannot write a ready lifecycle."""
import json, lzma, pathlib
from adapter import analyze
from common import ROOT, OPS, MAGIC, OPENMAGIC, SNAP, digest, file_digest, load, repository_state, write_json

IDS = {'59b869b9-cb48-4152-ad91-52f582e2df5b':'Comparative Analysis','8f32ceb2-92c2-4dde-bf73-40bb79c3fcef':'Inspiration'}
MISS = 'verb_unmapped:p_draw'

def faces():
    found={}
    with lzma.open(SNAP,'rt',encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line); oid=row['oracleFaceKey']['scryfallOracleId']
            if oid in IDS: found[oid]=row
    if set(found)!=set(IDS): raise RuntimeError('E_SOURCE_MEMBER_MISSING')
    return found

def member(a):
    hit=next(x for x in a['assertions'] if x['text']=='Target player draws two cards.')
    return {'oracle_face_id':a['oracle_face_id'],'oracle_face_key':a['oracle_face_key'],'semantic_source_hash':a['semantic_source_hash'],
      'assertion_locator':{'assertion_index':hit['assertion_index'],'exact_text':hit['text'],'span':hit['span']},
      'complete_gap_set':a['before_gap_set'],'quarantine_status':'clear','relation_readiness':'not_required'}

def main():
    fs=faces(); analyses=[analyze(fs[k],IDS[k]) for k in sorted(IDS)]
    for a in analyses: write_json(ROOT/f"inputs/analysis-{a['name'].lower().replace(' ','-')}.json",a)
    members=[member(a) for a in analyses]; root=[m for m in members if MISS in m['complete_gap_set']]
    policy=load(ROOT/'inputs/policy.json')
    membership={'schema':'magic.projection-membership/v1','member_ids':sorted(m['oracle_face_id'] for m in root)}
    descriptor={'schema':'magic.projection/v1','name':policy['projection'],'source_inventory_hash':file_digest(SNAP),'rules':{'canonical_only':True,'normal_game_candidate':True,'quarantine':'exclude'}}
    write_json(ROOT/'inputs/projection-membership.json',membership); write_json(ROOT/'inputs/projection-descriptor.json',descriptor)
    scope={'schema':'magic.scope/v1','projection':{'descriptor_hash':digest(descriptor),'membership_hash':digest(membership)},'root_cause_scope':root,
      'sole_blocker_members':[m for m in root if m['complete_gap_set']==[MISS]],'predicted_whole_face_unlock_members':[m for m in root if set(m['complete_gap_set'])-{MISS}==set()]}
    write_json(ROOT/'outputs/scope.json',scope)
    behavior={'timing':'resolve','subject':'target_player','kind':'draw_cards','count':2}
    cause={'schema':'magic.root-cause/v1','class':'map.assertion.target-player-draw-two','behavior':behavior,'required_behavior_hash':digest(behavior)}
    finding={'schema':'magic.finding/v1','selected_assertion':'Target player draws two cards.','observed_gap':MISS,'homogeneous':True}
    write_json(ROOT/'inputs/root-cause.json',cause); write_json(ROOT/'inputs/finding.json',finding)
    skill={'path':'skills/implement-map-class/SKILL.md','sha256':file_digest(ROOT/'skills/implement-map-class/SKILL.md'),'resource_receipts':[],'synthetic':False}
    inspected={str(OPS):['docs/sessions/ticketspec-v1-contract-correction/compiler/adapter.py','docs/sessions/ticketspec-v1-contract-correction/compiler/compile.py','docs/sessions/ticketspec-v1-contract-correction/inputs/policy.json'],
      str(OPENMAGIC):['scripts/paragraph/classify.py','scripts/paragraph/reparse.py','scripts/paragraph/slotparse_oneshot.py'],
      str(MAGIC):['backend/game/ability_effects.go','backend/cards/converter.go','backend/cards/registry.go','backend/cardfns/lib_draw_for_player.go']}
    repos=[repository_state(pathlib.Path(repo),paths) for repo,paths in inspected.items()]
    engine={'schema':'magic.engine-receipt/v1','repository':str(MAGIC),'source_files':['backend/game/ability_effects.go','backend/cards/converter.go','backend/cardfns/lib_draw_for_player.go'],
      'symbols':[{'file':'backend/game/ability_effects.go','symbol':'func (gs *GameState) ExecuteAbilityEffect','required_fragments':['case "draw":','executeDrawEffect(controller, effectValue, targets)']},{'file':'backend/game/ability_effects.go','symbol':'func (gs *GameState) executeDrawEffect','required_fragments':['targets []Target','PlayerIdx']},{'file':'backend/cards/converter.go','symbol':'case "draw":','required_fragments':['SpellEffect{Type: "draw"']},{'file':'backend/cardfns/lib_draw_for_player.go','symbol':'func DrawForPlayer','required_fragments':['DrawCardsWithEvent(playerIdx, n)']}],
      'test_path':'tests/engine_target_player_overlay_test.go','test_hash':file_digest(ROOT/'tests/engine_target_player_overlay_test.go'),'overlay_path':'tests/engine-overlay.json','overlay_hash':file_digest(ROOT/'tests/engine-overlay.json'),
      'command_argv':['go','test','-overlay='+str(ROOT/'tests/engine-overlay.json'),'./game','-run','^TestTicketSpecTargetPlayerDrawTwo$','-count=1']}
    evidence={'schema':'factory.evidence-pack/v1','analyses':analyses,'repository_receipts':repos,'skill_receipt':skill,'engine_receipt':engine,
      'artifact_receipts':[{'path':'inputs/policy.json','sha256':file_digest(ROOT/'inputs/policy.json')},{'path':'inputs/projection-descriptor.json','sha256':file_digest(ROOT/'inputs/projection-descriptor.json')},{'path':'inputs/projection-membership.json','sha256':file_digest(ROOT/'inputs/projection-membership.json')},{'path':'compiler/adapter.py','sha256':file_digest(ROOT/'compiler/adapter.py')}]}
    write_json(ROOT/'outputs/evidence-pack.json',evidence)
    identity={'schema':'factory.ticket-identity/v1','project':'magic','work_type':'map','root_cause':cause,'required_behavior':behavior,'projection_descriptor_hash':digest(descriptor),'projection_membership_hash':digest(membership),
      'scope_member_ids':sorted(m['oracle_face_id'] for m in root),'source_inventory_hash':descriptor['source_inventory_hash'],'policy_hash':file_digest(ROOT/'inputs/policy.json'),'skill_contract_hash':skill['sha256']}
    write_json(ROOT/'inputs/identity.json',identity); ident=digest(identity); ticket_id='ticket:'+ident
    graph={'schema':'factory.graph/v1','nodes':[{'id':'mission:magic-map-target-player-draw','node_type':'main_mission'},{'id':ticket_id,'node_type':'ticket'}],'edges':[{'from':'mission:magic-map-target-player-draw','to':ticket_id,'edge_type':'decomposes_to'}]}
    write_json(ROOT/'outputs/graph.json',graph)
    gates=[{'id':'schema-cross-artifact','phase':'creation','argv':['python3','compiler/validate.py','--pre-readiness'],'cwd':str(ROOT),'environment':{},'expected_exit':0},
      {'id':'focused-reproduction','phase':'creation','argv':['python3','compiler/gate_checks.py','reproduction'],'cwd':str(ROOT),'environment':{},'expected_exit':0},
      {'id':'receipt-verification','phase':'creation','argv':['python3','compiler/gate_checks.py','receipts'],'cwd':str(ROOT),'environment':{},'expected_exit':0},
      {'id':'engine-target-player-draw','phase':'creation','argv':engine['command_argv'],'cwd':str(MAGIC/'backend'),'environment':{},'expected_exit':0}]
    patch=[{'id':x,'phase':'patch','argv':argv,'cwd':cwd,'environment':{},'expected_exit':0} for x,argv,cwd in [('positive-adjacent-negative',['python3','-m','unittest','scripts.paragraph.test_ticketspec_target_player_draw'],str(OPENMAGIC)),('honesty-engine-unchanged',['git','diff','--exit-code','--','backend/game','backend/cardfns','backend/cards'],str(MAGIC)),('parser-regression',['python3','-m','unittest','discover','-s','scripts/paragraph','-p','test_*.py'],str(OPENMAGIC)),('immutable-scope-remeasurement',['python3','compiler/validate.py','--remeasure'],str(ROOT))]]
    profile={'schema':'factory.work-profile/v1','work_type':'map','difficulty':'medium','uncertainty':'low','risk':'medium','required_capabilities':['semantic_code_editing','python_tests'],'budget':{'effective_token_target':200000,'warning_threshold':500000,'automatic_stop':False}}
    attempt={'schema':'factory.attempt-policy/v1','max_attempts':3,'verdicts':['SUCCESS','REFUSE','PARK','SPLIT','REFACTOR_FIRST','INFRASTRUCTURE_FAILURE'],'reflection':{'threshold':500000,'action':'warn_checkpoint_reflect','continue_verdict':'CONTINUE_NECESSARY'}}
    ticket={'schema':'factory.ticket/v1','ticket_id':ticket_id,'identity_digest':ident,'work_type':'map','lifecycle':'candidate','scope_hash':digest(scope),'graph_hash':digest(graph),'evidence_pack_hash':digest(evidence),
      'projection_hash':digest(descriptor),'projection_membership_hash':digest(membership),'policy_hash':file_digest(ROOT/'inputs/policy.json'),'skill_receipt':skill,'work_profile':profile,'attempt_policy':attempt,'gates':gates+patch,'readiness_path':'outputs/readiness.json'}
    write_json(ROOT/'outputs/ticket.json',ticket)
    write_json(ROOT/'outputs/result-partition.json',{'schema':'magic.result-partition/v1','scope_hash':digest(scope),'status':'pending','partitions':{'confirmed_fixed_by_change':[],'already_fixed_independently':[],'still_failing_same_root_cause':root,'reclassified_different_root_cause':[],'invalid_or_unsupported':[]}})
    write_json(ROOT/'outputs/workflow.json',{'schema':'factory.workflow/v1','stages':[{'stage':i,'authority':'code' if i in [1,2,3,6,7] else 'model','status':'complete' if i<=3 else 'pending'} for i in range(1,8)],'routing_descriptor':{'status':'pending','sequence':['deterministic_prepare','local_ai_advisory','deterministic_verify_local','capable_model_decide_implement','deterministic_gate_remeasure','local_ai_failure_capsule','capable_model_conditional_recall'],'selection_inputs':['difficulty','uncertainty','risk','required_capabilities','attempt_history']},'telemetry_dimensions':['input_tokens','output_tokens','cache_read_tokens','cache_write_tokens','reasoning_tokens','effective_total','wall_time','model','provider','attempt','stage']})
    ledger=load(ROOT/'fixtures/history/open-history-ledger.json'); matches=[x for x in ledger['entries'] if x['identity_digest']==ident]
    if not matches: ledger['entries'].append({'ticket_id':ticket_id,'identity_digest':ident,'status':'open'}); write_json(ROOT/'fixtures/history/open-history-ledger.json',ledger)
    elif len(matches)!=1 or matches[0]['ticket_id']!=ticket_id: raise RuntimeError('E_DUPLICATE_HISTORICAL_IDENTITY')
    write_json(ROOT/'outputs/readiness.json',{'schema':'factory.readiness/v1','initial_lifecycle':'candidate','final_lifecycle':'candidate','predicates':[],'reason_codes':['E_NOT_EVALUATED'],'evaluator':{'symbol':'compiler/readiness.py:evaluate','input_receipt_set_hash':None}})

if __name__=='__main__': main()
