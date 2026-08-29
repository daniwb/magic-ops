#!/usr/bin/env python3
"""Write the manifest last; only manifest.json is excluded from its inventory."""
import pathlib, subprocess
from common import ROOT, OPS, MAGIC, OPENMAGIC, file_digest, git, load, write_json

def listing(path):
    return subprocess.check_output("find . -type f -not -path '*/__pycache__/*' -not -path '*/.cache/*' -print0 | sort -z | xargs -0 sha256sum",shell=True,cwd=path,text=True).replace('  ./','  docs/sessions/'+path.name+'/')

def main():
    expected1=(ROOT/'inputs/pinned/ticketspec-v1.sha256').read_text(); expected2=(ROOT/'inputs/pinned/ticketspec-v1-repair.sha256').read_text()
    actual1=listing(OPS/'docs/sessions/ticketspec-v1');actual2=listing(OPS/'docs/sessions/ticketspec-v1-repair')
    if actual1!=expected1:raise SystemExit('E_ORIGINAL_PROTOTYPE_MUTATED')
    if actual2!=expected2:raise SystemExit('E_REPAIR_PROTOTYPE_MUTATED')
    artifacts=[]
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT).as_posix()
        if path.is_file() and rel!='manifest.json' and '__pycache__' not in rel and not rel.endswith('.pyc'):
            artifacts.append({'path':rel,'sha256':file_digest(path),'bytes':path.stat().st_size})
    readiness=load(ROOT/'outputs/readiness.json')
    manifest={'schema':'factory.session-manifest/v1','status':'complete','ticket_lifecycle':readiness['final_lifecycle'],'completed_stages':[1,2,3],'pending_stages':[4,5,6,7],
      'artifacts':artifacts,'manifest_exclusions':['manifest.json'],
      'repositories':[{'path':str(x),'commit':git(x,'rev-parse','HEAD'),'dirty_paths':sorted(y for y in git(x,'status','--porcelain').splitlines() if y)} for x in (OPS,MAGIC,OPENMAGIC)],
      'prototype_integrity':{'ticketspec_v1':True,'ticketspec_v1_repair':True},'attempt_receipt_policy':'latest bounded gate-receipts paths are replaced by a newly executed receipt set on every run; normative identity excludes timestamps and output timing',
      'rerun_command':'cd /opt/development/magic-ops/docs/sessions/ticketspec-v1-contract-correction && python3 compiler/run_pipeline.py',
      'token_usage':{'status':'unavailable','reason':'environment exposes no authoritative Codex session token counter'},
      'no_production_mutation':{'write_allowlist':[str(ROOT)+'/**'],'map_fix_implemented':False,'model_stages_4_7_executed':False,'services_or_databases_mutated':False}}
    write_json(ROOT/'manifest.json',manifest);print('OK manifest')

if __name__=='__main__':main()
