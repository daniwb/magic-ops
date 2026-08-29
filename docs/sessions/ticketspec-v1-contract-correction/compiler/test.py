#!/usr/bin/env python3
"""One-condition adversarial tests with exact error codes."""
import copy, pathlib, shutil, tempfile
from common import ROOT, digest, file_digest, load, write_json
import validate

def save(bundle, rel, obj): write_json(pathlib.Path(bundle)/rel,obj)
def docs(b): return {n:load(b/f'outputs/{n}.json') for n in ('ticket','scope','graph','evidence-pack','workflow','readiness','result-partition')}
def sync(t,s,g,e): t['scope_hash']=digest(s);t['graph_hash']=digest(g);t['evidence_pack_hash']=digest(e)

def mutate(name,b):
    d=docs(b);t,s,g,e,r,p=(d[x] for x in ('ticket','scope','graph','evidence-pack','readiness','result-partition'))
    if name=='scope-hash':t['scope_hash']='sha256:'+'0'*64
    elif name=='graph-hash':t['graph_hash']='sha256:'+'0'*64
    elif name=='evidence-hash':t['evidence_pack_hash']='sha256:'+'0'*64
    elif name=='projection-hash':t['projection_hash']='sha256:'+'0'*64
    elif name=='identity-digest':t['identity_digest']='sha256:'+'1'*64
    elif name=='skill-receipt':t['skill_receipt']['sha256']='sha256:'+'2'*64
    elif name=='repository-receipt':e['repository_receipts'][1]['relevant_files'][0]['sha256']='sha256:'+'3'*64;sync(t,s,g,e)
    elif name=='engine-receipt':e['engine_receipt']['test_hash']='sha256:'+'4'*64;sync(t,s,g,e)
    elif name=='member-substitution':
        m=load(b/'inputs/projection-membership.json');m['member_ids'][0]='oracle:substitute:none';save(b,'inputs/projection-membership.json',m);t['projection_membership_hash']=digest(m);s['projection']['membership_hash']=digest(m);next(x for x in e['artifact_receipts'] if x['path']=='inputs/projection-membership.json')['sha256']=file_digest(b/'inputs/projection-membership.json');sync(t,s,g,e)
    elif name=='duplicate-identity':
        h=load(b/'fixtures/history/open-history-ledger.json');hit=next(x for x in h['entries'] if x['identity_digest']==t['identity_digest']);h['entries'].append(copy.deepcopy(hit));save(b,'fixtures/history/open-history-ledger.json',h)
    elif name=='stale-source-bytes':e['analyses'][0]['semantic_source']+='x';sync(t,s,g,e)
    elif name=='incomplete-inventory':e['analyses']=e['analyses'][:1];sync(t,s,g,e)
    elif name=='mixed-behavior':s['root_cause_scope'][1]['complete_gap_set']=['different'];sync(t,s,g,e)
    elif name=='invalid-span':s['root_cause_scope'][0]['assertion_locator']['span']['start']+=1;sync(t,s,g,e)
    elif name=='untyped-edge':g['edges'][0]['edge_type']='unknown';sync(t,s,g,e)
    elif name=='malformed-nested':t['work_profile']['budget']['surprise']=True
    elif name=='ambiguous-work-type':t['work_type']='ambiguous'
    elif name=='missing-skill':t['skill_receipt']['synthetic']=True
    elif name=='dangling-edge':g['edges'][0]['to']='missing';sync(t,s,g,e)
    elif name=='cycle':g['edges'].append({'from':g['edges'][0]['to'],'to':g['edges'][0]['from'],'edge_type':'blocked_by'});sync(t,s,g,e)
    elif name=='missing-root-edge':g['edges']=[];sync(t,s,g,e)
    elif name=='duplicate-result':p['partitions']['confirmed_fixed_by_change'].append(copy.deepcopy(p['partitions']['still_failing_same_root_cause'][0]))
    elif name=='missing-result':p['partitions']['still_failing_same_root_cause'].pop()
    elif name=='sole-blocker-scope':s['sole_blocker_members']=[copy.deepcopy(s['root_cause_scope'][0])];sync(t,s,g,e)
    elif name=='predicted-unlock-scope':s['predicted_whole_face_unlock_members']=[copy.deepcopy(s['root_cause_scope'][0])];sync(t,s,g,e)
    elif name=='subset-member-mismatch':s['sole_blocker_members'][0]['complete_gap_set']=['different'];sync(t,s,g,e)
    elif name=='semantic-byte-count':e['analyses'][0]['semantic_source_utf8_bytes']+=1;sync(t,s,g,e)
    elif name=='direct-promotion':t['lifecycle']='ready';r['final_lifecycle']='candidate'
    elif name=='ready-unsatisfied':r['predicates'][0]['satisfied']=False;r['predicates'][0]['reason_code']='E_TEST';r['final_lifecycle']='ready';t['lifecycle']='ready'
    elif name in ('forged-success','command-digest','changed-output'):
        idx=load(b/'gate-receipts/index.json');rec=idx['receipts'][0]
        if name=='forged-success':rec['exit_code']=9;rec['result']='passed'
        elif name=='command-digest':rec['command']['argv'].append('--forged')
        else:(b/rec['stdout']['path']).write_bytes((b/rec['stdout']['path']).read_bytes()+b'x')
        stable=[{k:x[k] for k in ('gate_id','command_digest','exit_code','result')} for x in idx['receipts']];idx['receipt_set_hash']=digest(stable);save(b,'gate-receipts/index.json',idx);r['evaluator']['input_receipt_set_hash']=idx['receipt_set_hash']
    elif name=='stale-repository':e['repository_receipts'][1]['commit']='0'*40;sync(t,s,g,e)
    else:raise KeyError(name)
    for n,obj in d.items():save(b,f'outputs/{n}.json',obj)

CASES={'scope-hash':'E_SCOPE_HASH_MISMATCH','graph-hash':'E_GRAPH_HASH_MISMATCH','evidence-hash':'E_EVIDENCE_PACK_HASH_MISMATCH','projection-hash':'E_PROJECTION_HASH_MISMATCH','identity-digest':'E_IDENTITY_DIGEST','skill-receipt':'E_SKILL_RECEIPT_MISMATCH','repository-receipt':'E_REPOSITORY_RECEIPT_MISMATCH','engine-receipt':'E_ENGINE_RECEIPT_MISMATCH','member-substitution':'E_PROJECTION_MEMBER_SUBSTITUTION','duplicate-identity':'E_DUPLICATE_HISTORICAL_IDENTITY','stale-source-bytes':'E_STALE_INPUT','incomplete-inventory':'E_INCOMPLETE_ASSERTION_GAP_INVENTORY','mixed-behavior':'E_INCOMPLETE_ASSERTION_GAP_INVENTORY','invalid-span':'E_INVALID_SOURCE_SPAN','untyped-edge':'E_SCHEMA_GRAPH','malformed-nested':'E_SCHEMA_TICKET','ambiguous-work-type':'E_AMBIGUOUS_WORK_TYPE','missing-skill':'E_SKILL_MISSING_OR_SYNTHETIC','dangling-edge':'E_DANGLING_EDGE','cycle':'E_GRAPH_CYCLE','missing-root-edge':'E_MISSING_ROOT_EDGE','duplicate-result':'E_DUPLICATE_RESULT_MEMBER','missing-result':'E_MISSING_RESULT_MEMBER','sole-blocker-scope':'E_SOLE_BLOCKER_SCOPE_MISMATCH','predicted-unlock-scope':'E_PREDICTED_UNLOCK_SCOPE_MISMATCH','subset-member-mismatch':'E_SCOPE_MEMBER_MISMATCH','semantic-byte-count':'E_STALE_INPUT','direct-promotion':'E_DIRECT_LIFECYCLE_PROMOTION','ready-unsatisfied':'E_READY_UNSATISFIED_PREDICATE','forged-success':'E_FORGED_GATE_SUCCESS','command-digest':'E_GATE_COMMAND_DIGEST_MISMATCH','changed-output':'E_GATE_OUTPUT_DIGEST_MISMATCH','stale-repository':'E_STALE_INPUT'}

def main():
    validate.validate_bundle(ROOT);results=[{'name':'valid-bundle','passed':True}]
    # Member ordering is explicitly normalized by identity/membership.
    with tempfile.TemporaryDirectory() as td:
        b=pathlib.Path(td)/'b';shutil.copytree(ROOT,b);d=docs(b);d['scope']['root_cause_scope'].reverse();d['ticket']['scope_hash']=digest(d['scope']);d['result-partition']['scope_hash']=digest(d['scope']);save(b,'outputs/scope.json',d['scope']);save(b,'outputs/ticket.json',d['ticket']);save(b,'outputs/result-partition.json',d['result-partition']);validate.validate_bundle(b);results.append({'name':'ordering-normalization','passed':True})
    for name,expected in CASES.items():
        with tempfile.TemporaryDirectory() as td:
            b=pathlib.Path(td)/'b';shutil.copytree(ROOT,b);mutate(name,b)
            try:validate.validate_bundle(b);got='NO_ERROR'
            except ValueError as ex:got=str(ex)
            if got!=expected:raise AssertionError(f'{name}: {got} != {expected}')
            results.append({'name':name,'expected_code':expected,'actual_code':got,'passed':True})
    before=load(ROOT/'outputs/readiness.json');import readiness;readiness.evaluate();after=load(ROOT/'outputs/readiness.json')
    if before!=after:raise AssertionError('unchanged receipt reevaluation changed readiness')
    results.append({'name':'deterministic-reevaluation','passed':True})
    with tempfile.TemporaryDirectory() as td:
        b=pathlib.Path(td)/'b';shutil.copytree(ROOT,b);mutate('forged-success',b);readiness.evaluate(b)
        if load(b/'outputs/readiness.json')['final_lifecycle']!='candidate':raise AssertionError('readiness accepted forged gate success')
        results.append({'name':'readiness-rejects-unverified-receipt','passed':True})
    write_json(ROOT/'test-results.json',{'schema':'factory.test-results/v1','assertions':results,'status':'passed'})
    print(f'OK {len(results)} assertions')

if __name__=='__main__':main()
