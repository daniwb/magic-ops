#!/usr/bin/env python3
"""Sole readiness and final-lifecycle writer."""
from common import ROOT, digest, load, write_json
from validate import validate_bundle, validate_gate_receipts

PREDICATES=('schemas_valid','cross_artifact_valid','history_dag_valid','quarantine_relation_clear','receipts_valid','engine_proven','creation_gates_passed')

def evaluate(root=ROOT):
    root=__import__('pathlib').Path(root)
    ticket=load(root/'outputs/ticket.json'); receipt_set=load(root/'gate-receipts/index.json')
    by_id={}
    validation_ok=True
    receipts_ok=True
    try:
        validate_bundle(root, pre_readiness=True)
        verified_set,verified=validate_gate_receipts(root,ticket)
        if verified_set['receipt_set_hash']!=receipt_set['receipt_set_hash']: raise ValueError('E_GATE_RECEIPT_SET_MISMATCH')
        by_id=verified
    except ValueError: validation_ok=False
    if not by_id: receipts_ok=False
    values={'schemas_valid':validation_ok,'cross_artifact_valid':validation_ok,'history_dag_valid':validation_ok,
      'quarantine_relation_clear':all(x['quarantine_status']=='clear' and x['relation_readiness'] in ('ready','not_required') for x in load(root/'outputs/scope.json')['root_cause_scope']),
      'receipts_valid':receipts_ok and by_id.get('receipt-verification',{}).get('result')=='passed','engine_proven':receipts_ok and by_id.get('engine-target-player-draw',{}).get('result')=='passed',
      'creation_gates_passed':set(by_id)=={x['id'] for x in ticket['gates'] if x['phase']=='creation'} and all(x['result']=='passed' for x in by_id.values())}
    predicates=[{'id':x,'satisfied':values[x],'reason_code':None if values[x] else 'E_'+x.upper()} for x in PREDICATES]
    final_lifecycle='ready' if all(values.values()) else 'candidate'
    readiness={'schema':'factory.readiness/v1','initial_lifecycle':'candidate','final_lifecycle':final_lifecycle,'predicates':predicates,
      'reason_codes':[x['reason_code'] for x in predicates if x['reason_code']],'evaluator':{'symbol':'compiler/readiness.py:evaluate','input_receipt_set_hash':receipt_set['receipt_set_hash']}}
    write_json(root/'outputs/readiness.json',readiness); ticket['lifecycle']=final_lifecycle; write_json(root/'outputs/ticket.json',ticket)

if __name__=='__main__': evaluate()
