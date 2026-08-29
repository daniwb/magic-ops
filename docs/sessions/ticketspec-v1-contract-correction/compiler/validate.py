#!/usr/bin/env python3
"""Closed-schema and end-to-end content-binding validator."""
import argparse, pathlib, sys
from common import ROOT, MAGIC, SNAP, digest, file_digest, git, load

def fail(code): raise ValueError(code)
def schema_check(name, doc):
    try: import jsonschema
    except ImportError: fail('E_DEPENDENCY_JSONSCHEMA')
    try: jsonschema.Draft202012Validator(load(ROOT/f'schemas/{name}-v1.schema.json'),format_checker=jsonschema.FormatChecker()).validate(doc)
    except jsonschema.ValidationError: fail('E_SCHEMA_'+name.upper().replace('-','_'))

def validate_gate_receipts(bundle, ticket):
    """Validate executed creation receipts before readiness may consume them."""
    bundle=pathlib.Path(bundle); receipt_set=load(bundle/'gate-receipts/index.json'); schema_check('gate-receipt-set',receipt_set)
    stable=[{k:x[k] for k in ('gate_id','command_digest','exit_code','result')} for x in receipt_set['receipts']]
    if receipt_set['receipt_set_hash']!=digest(stable): fail('E_GATE_RECEIPT_SET_MISMATCH')
    declared={x['id']:x for x in ticket['gates'] if x['phase']=='creation'}; actual={x['gate_id']:x for x in receipt_set['receipts']}
    if set(declared)!=set(actual): fail('E_GATE_RECEIPT_MISSING')
    for gate_id,rec in actual.items():
        if rec['command_digest']!=digest(rec['command']): fail('E_GATE_COMMAND_DIGEST_MISMATCH')
        expected=declared[gate_id]
        if rec['command']['argv']!=expected['argv'] or rec['command']['cwd']!=expected['cwd']: fail('E_GATE_COMMAND_DIGEST_MISMATCH')
        for stream in ('stdout','stderr'):
            ev=rec[stream]
            if file_digest(bundle/ev['path'])!=ev['sha256'] or (bundle/ev['path']).stat().st_size!=ev['bytes']: fail('E_GATE_OUTPUT_DIGEST_MISMATCH')
        derived='passed' if rec['exit_code']==expected['expected_exit'] else 'failed'
        if rec['result']!=derived: fail('E_FORGED_GATE_SUCCESS')
    return receipt_set,actual

def validate_bundle(bundle=ROOT, pre_readiness=False):
    bundle=pathlib.Path(bundle); names=('ticket','scope','graph','evidence-pack','workflow','readiness','result-partition')
    docs={x:load(bundle/f'outputs/{x}.json') for x in names}; t,s,g,e,w,r,p=(docs[x] for x in names)
    if t.get('work_type')!='map': fail('E_AMBIGUOUS_WORK_TYPE')
    if not g.get('edges'): fail('E_MISSING_ROOT_EDGE')
    if t.get('skill_receipt',{}).get('synthetic') or not t.get('skill_receipt',{}).get('path'): fail('E_SKILL_MISSING_OR_SYNTHETIC')
    if len(e.get('analyses',[]))<len(s.get('root_cause_scope',[])): fail('E_INCOMPLETE_ASSERTION_GAP_INVENTORY')
    for name,doc in docs.items(): schema_check(name,doc)
    if t['scope_hash']!=digest(s): fail('E_SCOPE_HASH_MISMATCH')
    if t['graph_hash']!=digest(g): fail('E_GRAPH_HASH_MISMATCH')
    if t['evidence_pack_hash']!=digest(e): fail('E_EVIDENCE_PACK_HASH_MISMATCH')
    descriptor=load(bundle/'inputs/projection-descriptor.json'); membership=load(bundle/'inputs/projection-membership.json')
    if t['projection_hash']!=digest(descriptor) or s['projection']['descriptor_hash']!=digest(descriptor): fail('E_PROJECTION_HASH_MISMATCH')
    if t['projection_membership_hash']!=digest(membership) or s['projection']['membership_hash']!=digest(membership): fail('E_PROJECTION_HASH_MISMATCH')
    if t['policy_hash']!=file_digest(bundle/'inputs/policy.json'): fail('E_POLICY_HASH_MISMATCH')
    identity=load(bundle/'inputs/identity.json')
    if t['identity_digest']!=digest(identity): fail('E_IDENTITY_DIGEST')
    if t['ticket_id']!='ticket:'+t['identity_digest']: fail('E_TICKET_ID')
    skill=t['skill_receipt']
    if skill['synthetic'] or file_digest(bundle/skill['path'])!=skill['sha256'] or skill!=e['skill_receipt']: fail('E_SKILL_RECEIPT_MISMATCH')
    for rec in e['artifact_receipts']:
        if file_digest(bundle/rec['path'])!=rec['sha256']: fail('E_REPOSITORY_RECEIPT_MISMATCH')
    for repo in e['repository_receipts']:
        base=pathlib.Path(repo['repository'])
        if git(base,'rev-parse','HEAD')!=repo['commit']: fail('E_STALE_INPUT')
        for item in repo['relevant_files']:
            if file_digest(base/item['path'])!=item['sha256']: fail('E_REPOSITORY_RECEIPT_MISMATCH')
    eng=e['engine_receipt']
    if file_digest(bundle/eng['test_path'])!=eng['test_hash'] or file_digest(bundle/eng['overlay_path'])!=eng['overlay_hash']: fail('E_ENGINE_RECEIPT_MISMATCH')
    for symbol in eng['symbols']:
        text=(MAGIC/symbol['file']).read_text()
        if symbol['symbol'] not in text or any(fragment not in text for fragment in symbol['required_fragments']): fail('E_ENGINE_RECEIPT_MISMATCH')
    if file_digest(SNAP)!=load(bundle/'inputs/projection-descriptor.json')['source_inventory_hash']: fail('E_STALE_INPUT')
    ids=[x['oracle_face_id'] for x in s['root_cause_scope']]
    if len(ids)!=len(set(ids)): fail('E_DUPLICATE_SCOPE_MEMBER')
    if sorted(ids)!=membership['member_ids']: fail('E_PROJECTION_MEMBER_SUBSTITUTION')
    analyses={x['oracle_face_id']:x for x in e['analyses']}
    if set(ids)!=set(analyses): fail('E_INCOMPLETE_ASSERTION_GAP_INVENTORY')
    for m in s['root_cause_scope']:
        a=analyses[m['oracle_face_id']]; loc=m['assertion_locator']; raw=a['semantic_source'].encode()
        if a['semantic_source_utf8_bytes']!=len(raw): fail('E_STALE_INPUT')
        if digest(raw)!=m['semantic_source_hash'] or digest(raw)!=a['semantic_source_hash']: fail('E_STALE_INPUT')
        if raw[loc['span']['start']:loc['span']['end']].decode()!=loc['exact_text']: fail('E_INVALID_SOURCE_SPAN')
        if m['complete_gap_set']!=a['before_gap_set']: fail('E_INCOMPLETE_ASSERTION_GAP_INVENTORY')
    finding=load(bundle/'inputs/finding.json'); miss=finding['observed_gap']
    if not all(miss in x['complete_gap_set'] for x in s['root_cause_scope']): fail('E_MIXED_ROOT_CAUSE_SCOPE')
    expected_sole=sorted(x['oracle_face_id'] for x in s['root_cause_scope'] if x['complete_gap_set']==[miss])
    actual_sole=sorted(x['oracle_face_id'] for x in s['sole_blocker_members'])
    if actual_sole!=expected_sole: fail('E_SOLE_BLOCKER_SCOPE_MISMATCH')
    expected_unlock=sorted(x['oracle_face_id'] for x in s['root_cause_scope'] if not set(x['complete_gap_set'])-{miss})
    actual_unlock=sorted(x['oracle_face_id'] for x in s['predicted_whole_face_unlock_members'])
    if actual_unlock!=expected_unlock: fail('E_PREDICTED_UNLOCK_SCOPE_MISMATCH')
    root_by_id={x['oracle_face_id']:x for x in s['root_cause_scope']}
    for subset in ('sole_blocker_members','predicted_whole_face_unlock_members'):
        if any(x!=root_by_id.get(x['oracle_face_id']) for x in s[subset]): fail('E_SCOPE_MEMBER_MISMATCH')
    nodes=[x['id'] for x in g['nodes']]
    if len(nodes)!=len(set(nodes)): fail('E_DUPLICATE_GRAPH_NODE')
    if not any(x['node_type']=='main_mission' for x in g['nodes']) or not any(x['edge_type']=='decomposes_to' for x in g['edges']): fail('E_MISSING_ROOT_EDGE')
    if any(x['from'] not in nodes or x['to'] not in nodes for x in g['edges']): fail('E_DANGLING_EDGE')
    adj={x:[] for x in nodes}
    for edge in g['edges']: adj[edge['from']].append(edge['to'])
    done=set(); active=set()
    def visit(node):
        if node in active: fail('E_GRAPH_CYCLE')
        if node in done:return
        active.add(node)
        for target in adj[node]:visit(target)
        active.remove(node); done.add(node)
    for node in nodes: visit(node)
    ledger=load(bundle/'fixtures/history/open-history-ledger.json')['entries']; matches=[x for x in ledger if x['identity_digest']==t['identity_digest']]
    if len(matches)!=1: fail('E_DUPLICATE_HISTORICAL_IDENTITY')
    members=[x['oracle_face_id'] for values in p['partitions'].values() for x in values]
    if len(members)!=len(set(members)): fail('E_DUPLICATE_RESULT_MEMBER')
    if set(members)!=set(ids): fail('E_MISSING_RESULT_MEMBER')
    if p['scope_hash']!=digest(s): fail('E_SCOPE_HASH_MISMATCH')
    if pre_readiness:return 'OK'
    receipt_set,actual=validate_gate_receipts(bundle,t)
    if r['evaluator']['input_receipt_set_hash']!=receipt_set['receipt_set_hash']: fail('E_READINESS_RECEIPT_MISMATCH')
    if r['final_lifecycle']=='ready' and (not r['predicates'] or not all(x['satisfied'] for x in r['predicates'])): fail('E_READY_UNSATISFIED_PREDICATE')
    if t['lifecycle']!=r['final_lifecycle']: fail('E_DIRECT_LIFECYCLE_PROMOTION')
    if r['final_lifecycle']=='ready' and any(x['result']!='passed' for x in actual.values()): fail('E_FORGED_GATE_SUCCESS')
    return 'OK'

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('bundle',nargs='?',default=str(ROOT)); ap.add_argument('--pre-readiness',action='store_true'); ap.add_argument('--remeasure',action='store_true'); args=ap.parse_args()
    try:
        if args.remeasure:
            s=load(ROOT/'outputs/scope.json'); p=load(ROOT/'outputs/result-partition.json'); ids=[x['oracle_face_id'] for x in s['root_cause_scope']]; got=[x['oracle_face_id'] for v in p['partitions'].values() for x in v]
            if len(got)!=len(set(got)):fail('E_DUPLICATE_RESULT_MEMBER')
            if set(got)!=set(ids):fail('E_MISSING_RESULT_MEMBER')
            print('OK')
        else: print(validate_bundle(pathlib.Path(args.bundle),args.pre_readiness))
    except ValueError as ex: print(ex,file=sys.stderr); raise SystemExit(1)
