#!/usr/bin/env python3
"""Generate closed Draft 2020-12 schemas used by the correction bundle."""
from common import ROOT, write_json

def obj(required, properties): return {'type':'object','required':required,'properties':properties,'additionalProperties':False}
def arr(items,min_items=0,unique=False):
    x={'type':'array','items':items,'minItems':min_items}
    if unique:x['uniqueItems']=True
    return x

H={'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}; S={'type':'string','minLength':1}; N={'type':'integer','minimum':0}
defs={
 'hash':H,
 'oracle_key':obj(['scryfallOracleId','side'],{'scryfallOracleId':{'type':'string','format':'uuid'},'side':{'type':['string','null']}}),
 'span':obj(['start','end'],{'start':N,'end':{'type':'integer','minimum':1}}),
 'locator':obj(['assertion_index','exact_text','span'],{'assertion_index':{'type':'integer','minimum':1},'exact_text':S,'span':{'$ref':'#/$defs/span'}}),
 'member':obj(['oracle_face_id','oracle_face_key','semantic_source_hash','assertion_locator','complete_gap_set','quarantine_status','relation_readiness'],{'oracle_face_id':S,'oracle_face_key':{'$ref':'#/$defs/oracle_key'},'semantic_source_hash':H,'assertion_locator':{'$ref':'#/$defs/locator'},'complete_gap_set':arr(S,1,True),'quarantine_status':{'enum':['clear','quarantined']},'relation_readiness':{'enum':['not_required','ready','blocked']}}),
 'parser_outcome':obj(['abilities','eligible','keywords','misses','name'],{'abilities':arr({},0),'eligible':{'type':'boolean'},'keywords':arr({},0),'misses':arr(arr(S,2),0),'name':S}),
 'assertion':obj(['assertion_index','text','span','parser_outcome'],{'assertion_index':{'type':'integer','minimum':1},'text':S,'span':{'$ref':'#/$defs/span'},'parser_outcome':{'$ref':'#/$defs/parser_outcome'}}),
 'analysis':obj(['schema','oracle_face_id','oracle_face_key','name','semantic_source','semantic_source_hash','semantic_source_utf8_bytes','assertions','full_parser_outcome','before_gap_set'],{'schema':{'const':'magic.parser-analysis/v1'},'oracle_face_id':S,'oracle_face_key':{'$ref':'#/$defs/oracle_key'},'name':S,'semantic_source':S,'semantic_source_hash':H,'semantic_source_utf8_bytes':N,'assertions':arr({'$ref':'#/$defs/assertion'},1),'full_parser_outcome':{'$ref':'#/$defs/parser_outcome'},'before_gap_set':arr(S,1,True)}),
 'file_receipt':obj(['path','sha256'],{'path':S,'sha256':H}),
 'repository_receipt':obj(['repository','commit','dirty_paths','relevant_files','dirty_policy'],{'repository':S,'commit':{'type':'string','pattern':'^[0-9a-f]{40}$'},'dirty_paths':arr(S,0,True),'relevant_files':arr({'$ref':'#/$defs/file_receipt'},0),'dirty_policy':S}),
 'skill_receipt':obj(['path','sha256','resource_receipts','synthetic'],{'path':S,'sha256':H,'resource_receipts':arr({'$ref':'#/$defs/file_receipt'},0,True),'synthetic':{'const':False}}),
 'engine_symbol':obj(['file','symbol','required_fragments'],{'file':S,'symbol':S,'required_fragments':arr(S,1,True)}),
 'engine_receipt':obj(['schema','repository','source_files','symbols','test_path','test_hash','overlay_path','overlay_hash','command_argv'],{'schema':{'const':'magic.engine-receipt/v1'},'repository':S,'source_files':arr(S,1,True),'symbols':arr({'$ref':'#/$defs/engine_symbol'},1),'test_path':S,'test_hash':H,'overlay_path':S,'overlay_hash':H,'command_argv':arr(S,1)}),
 'budget':obj(['effective_token_target','warning_threshold','automatic_stop'],{'effective_token_target':{'type':'integer','minimum':1},'warning_threshold':{'type':'integer','minimum':1},'automatic_stop':{'const':False}}),
 'work_profile':obj(['schema','work_type','difficulty','uncertainty','risk','required_capabilities','budget'],{'schema':{'const':'factory.work-profile/v1'},'work_type':{'const':'map'},'difficulty':{'enum':['low','medium','high']},'uncertainty':{'enum':['low','medium','high']},'risk':{'enum':['low','medium','high']},'required_capabilities':arr(S,1,True),'budget':{'$ref':'#/$defs/budget'}}),
 'reflection':obj(['threshold','action','continue_verdict'],{'threshold':{'type':'integer','minimum':1},'action':S,'continue_verdict':{'const':'CONTINUE_NECESSARY'}}),
 'attempt_policy':obj(['schema','max_attempts','verdicts','reflection'],{'schema':{'const':'factory.attempt-policy/v1'},'max_attempts':{'type':'integer','minimum':1},'verdicts':arr(S,1,True),'reflection':{'$ref':'#/$defs/reflection'}}),
 'gate':obj(['id','phase','argv','cwd','environment','expected_exit'],{'id':S,'phase':{'enum':['creation','patch']},'argv':arr(S,1),'cwd':S,'environment':obj([],{}),'expected_exit':{'type':'integer'}}),
 'graph_node':obj(['id','node_type'],{'id':S,'node_type':{'enum':['main_mission','ticket']}}),
 'graph_edge':obj(['from','to','edge_type'],{'from':S,'to':S,'edge_type':{'enum':['decomposes_to','blocked_by','discovered_by','verifies','integrates','residual_of','reflects_on']}}),
 'predicate':obj(['id','satisfied','reason_code'],{'id':S,'satisfied':{'type':'boolean'},'reason_code':{'type':['string','null']}}),
 'evaluator':obj(['symbol','input_receipt_set_hash'],{'symbol':{'const':'compiler/readiness.py:evaluate'},'input_receipt_set_hash':{'anyOf':[H,{'type':'null'}]}}),
 'stage':obj(['stage','authority','status'],{'stage':{'type':'integer','minimum':1,'maximum':7},'authority':{'enum':['code','model']},'status':{'enum':['complete','pending']}}),
 'routing':obj(['status','sequence','selection_inputs'],{'status':{'const':'pending'},'sequence':arr(S,7,True),'selection_inputs':arr(S,1,True)}),
 'partition':obj(['confirmed_fixed_by_change','already_fixed_independently','still_failing_same_root_cause','reclassified_different_root_cause','invalid_or_unsupported'],{x:arr({'$ref':'#/$defs/member'},0,True) for x in ['confirmed_fixed_by_change','already_fixed_independently','still_failing_same_root_cause','reclassified_different_root_cause','invalid_or_unsupported']}),
 'stream_evidence':obj(['path','sha256','bytes'],{'path':S,'sha256':H,'bytes':N}),
 'command':obj(['argv','cwd','environment'],{'argv':arr(S,1),'cwd':S,'environment':{'type':'object','additionalProperties':{'type':'string'}}}),
 'gate_receipt':obj(['schema','gate_id','command_digest','command','repository_state','started_at','ended_at','wall_time_ms','exit_code','stdout','stderr','result'],{'schema':{'const':'factory.gate-execution-receipt/v1'},'gate_id':S,'command_digest':H,'command':{'$ref':'#/$defs/command'},'repository_state':arr({'$ref':'#/$defs/repository_receipt'},1),'started_at':{'type':'string','format':'date-time'},'ended_at':{'type':'string','format':'date-time'},'wall_time_ms':N,'exit_code':{'type':'integer'},'stdout':{'$ref':'#/$defs/stream_evidence'},'stderr':{'$ref':'#/$defs/stream_evidence'},'result':{'enum':['passed','failed']}}),
}

schemas={
 'ticket':obj(['schema','ticket_id','identity_digest','work_type','lifecycle','scope_hash','graph_hash','evidence_pack_hash','projection_hash','projection_membership_hash','policy_hash','skill_receipt','work_profile','attempt_policy','gates','readiness_path'],{'schema':{'const':'factory.ticket/v1'},'ticket_id':{'type':'string','pattern':'^ticket:sha256:[0-9a-f]{64}$'},'identity_digest':H,'work_type':{'const':'map'},'lifecycle':{'enum':['candidate','ready','blocked']},'scope_hash':H,'graph_hash':H,'evidence_pack_hash':H,'projection_hash':H,'projection_membership_hash':H,'policy_hash':H,'skill_receipt':{'$ref':'#/$defs/skill_receipt'},'work_profile':{'$ref':'#/$defs/work_profile'},'attempt_policy':{'$ref':'#/$defs/attempt_policy'},'gates':arr({'$ref':'#/$defs/gate'},1),'readiness_path':{'const':'outputs/readiness.json'}}),
 'scope':obj(['schema','projection','root_cause_scope','sole_blocker_members','predicted_whole_face_unlock_members'],{'schema':{'const':'magic.scope/v1'},'projection':obj(['descriptor_hash','membership_hash'],{'descriptor_hash':H,'membership_hash':H}),'root_cause_scope':arr({'$ref':'#/$defs/member'},1,True),'sole_blocker_members':arr({'$ref':'#/$defs/member'},1,True),'predicted_whole_face_unlock_members':arr({'$ref':'#/$defs/member'},1,True)}),
 'graph':obj(['schema','nodes','edges'],{'schema':{'const':'factory.graph/v1'},'nodes':arr({'$ref':'#/$defs/graph_node'},2,True),'edges':arr({'$ref':'#/$defs/graph_edge'},1,True)}),
 'evidence-pack':obj(['schema','analyses','repository_receipts','skill_receipt','engine_receipt','artifact_receipts'],{'schema':{'const':'factory.evidence-pack/v1'},'analyses':arr({'$ref':'#/$defs/analysis'},2,True),'repository_receipts':arr({'$ref':'#/$defs/repository_receipt'},3,True),'skill_receipt':{'$ref':'#/$defs/skill_receipt'},'engine_receipt':{'$ref':'#/$defs/engine_receipt'},'artifact_receipts':arr({'$ref':'#/$defs/file_receipt'},1,True)}),
 'workflow':obj(['schema','stages','routing_descriptor','telemetry_dimensions'],{'schema':{'const':'factory.workflow/v1'},'stages':arr({'$ref':'#/$defs/stage'},7,True),'routing_descriptor':{'$ref':'#/$defs/routing'},'telemetry_dimensions':arr(S,1,True)}),
 'readiness':obj(['schema','initial_lifecycle','final_lifecycle','predicates','reason_codes','evaluator'],{'schema':{'const':'factory.readiness/v1'},'initial_lifecycle':{'const':'candidate'},'final_lifecycle':{'enum':['candidate','ready','blocked']},'predicates':arr({'$ref':'#/$defs/predicate'},0,True),'reason_codes':arr(S,0,True),'evaluator':{'$ref':'#/$defs/evaluator'}}),
 'result-partition':obj(['schema','scope_hash','status','partitions'],{'schema':{'const':'magic.result-partition/v1'},'scope_hash':H,'status':{'enum':['pending','complete']},'partitions':{'$ref':'#/$defs/partition'}}),
 'gate-receipt-set':obj(['schema','receipts','receipt_set_hash'],{'schema':{'const':'factory.gate-receipt-set/v1'},'receipts':arr({'$ref':'#/$defs/gate_receipt'},1,True),'receipt_set_hash':H}),
 'session-manifest':obj(['schema','status','ticket_lifecycle','completed_stages','pending_stages','artifacts','manifest_exclusions','repositories','prototype_integrity','attempt_receipt_policy','rerun_command','token_usage','no_production_mutation'],{
   'schema':{'const':'factory.session-manifest/v1'},'status':{'enum':['complete','incomplete','blocked']},'ticket_lifecycle':{'enum':['candidate','ready','blocked']},'completed_stages':arr({'type':'integer','minimum':1,'maximum':7},1,True),'pending_stages':arr({'type':'integer','minimum':1,'maximum':7},1,True),
   'artifacts':arr(obj(['path','sha256','bytes'],{'path':S,'sha256':H,'bytes':N}),1,True),'manifest_exclusions':arr(S,1,True),
   'repositories':arr(obj(['path','commit','dirty_paths'],{'path':S,'commit':{'type':'string','pattern':'^[0-9a-f]{40}$'},'dirty_paths':arr(S,0,True)}),3,True),
   'prototype_integrity':obj(['ticketspec_v1','ticketspec_v1_repair'],{'ticketspec_v1':{'const':True},'ticketspec_v1_repair':{'const':True}}),'attempt_receipt_policy':S,'rerun_command':S,
   'token_usage':obj(['status','reason'],{'status':{'const':'unavailable'},'reason':S}),'no_production_mutation':obj(['write_allowlist','map_fix_implemented','model_stages_4_7_executed','services_or_databases_mutated'],{'write_allowlist':arr(S,1,True),'map_fix_implemented':{'const':False},'model_stages_4_7_executed':{'const':False},'services_or_databases_mutated':{'const':False}})}),
}

schemas.update({
 'work-profile':{'$ref':'#/$defs/work_profile'},
 'attempt-policy':{'$ref':'#/$defs/attempt_policy'},
 'gate':{'$ref':'#/$defs/gate'},
 'finding':obj(['schema','selected_assertion','observed_gap','homogeneous'],{'schema':{'const':'magic.finding/v1'},'selected_assertion':S,'observed_gap':S,'homogeneous':{'type':'boolean'}}),
 'root-cause':obj(['schema','class','behavior','required_behavior_hash'],{'schema':{'const':'magic.root-cause/v1'},'class':S,'behavior':obj(['timing','subject','kind','count'],{'timing':S,'subject':S,'kind':S,'count':{'type':'integer','minimum':1}}),'required_behavior_hash':H}),
 'engine-receipt':{'$ref':'#/$defs/engine_receipt'},
 'parser-analysis':{'$ref':'#/$defs/analysis'},
 'repository-receipt':{'$ref':'#/$defs/repository_receipt'},
})

for name,body in schemas.items():
    body={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':f'https://openmagic.example/schemas/{name}-v1.schema.json','$defs':defs,**body}
    write_json(ROOT/f'schemas/{name}-v1.schema.json',body)

if __name__=='__main__': print('OK schemas')
