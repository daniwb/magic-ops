#!/usr/bin/env python3
import pathlib, sys
from common import ROOT, MAGIC, SNAP, canonical, digest, file_digest, git, load
from compile import IDS, faces
from adapter import analyze

def fail(code): raise ValueError(code)

def reproduction():
    evidence=load(ROOT/'outputs/evidence-pack.json'); scope=load(ROOT/'outputs/scope.json')
    analyses={x['oracle_face_id']:x for x in evidence['analyses']}
    current_faces=faces()
    current={row['oracleFaceId']:analyze(row,IDS[oid]) for oid,row in current_faces.items()}
    if canonical(analyses)!=canonical(current): fail('E_STALE_PARSER_ANALYSIS')
    for member in scope['root_cause_scope']:
        a=analyses.get(member['oracle_face_id'])
        if not a or member['complete_gap_set']!=a['before_gap_set']: fail('E_INCOMPLETE_ASSERTION_GAP_INVENTORY')
        loc=member['assertion_locator']; raw=a['semantic_source'].encode('utf-8')
        if raw[loc['span']['start']:loc['span']['end']].decode('utf-8')!=loc['exact_text']: fail('E_INVALID_SOURCE_SPAN')

def receipts():
    e=load(ROOT/'outputs/evidence-pack.json')
    for rec in e['artifact_receipts']:
        if file_digest(ROOT/rec['path'])!=rec['sha256']: fail('E_REPOSITORY_RECEIPT_MISMATCH')
    skill=e['skill_receipt']
    if skill['synthetic'] or file_digest(ROOT/skill['path'])!=skill['sha256']: fail('E_SKILL_RECEIPT_MISMATCH')
    for repo in e['repository_receipts']:
        base=pathlib.Path(repo['repository'])
        if git(base,'rev-parse','HEAD')!=repo['commit']: fail('E_STALE_INPUT')
        for item in repo['relevant_files']:
            if file_digest(base/item['path'])!=item['sha256']: fail('E_REPOSITORY_RECEIPT_MISMATCH')
    eng=e['engine_receipt']
    if file_digest(ROOT/eng['test_path'])!=eng['test_hash'] or file_digest(ROOT/eng['overlay_path'])!=eng['overlay_hash']: fail('E_ENGINE_RECEIPT_MISMATCH')
    for symbol in eng['symbols']:
        text=(MAGIC/symbol['file']).read_text()
        if symbol['symbol'] not in text or any(x not in text for x in symbol['required_fragments']): fail('E_ENGINE_RECEIPT_MISMATCH')
    if file_digest(SNAP)!=load(ROOT/'inputs/projection-descriptor.json')['source_inventory_hash']: fail('E_STALE_INPUT')

if __name__=='__main__':
    try:
        {'reproduction':reproduction,'receipts':receipts}[sys.argv[1]](); print('OK')
    except ValueError as ex: print(ex,file=sys.stderr); raise SystemExit(1)
