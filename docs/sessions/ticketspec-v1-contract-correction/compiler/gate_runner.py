#!/usr/bin/env python3
"""The only creation-gate executor and receipt writer."""
import datetime, os, pathlib, subprocess, time
from common import ROOT, OPS, MAGIC, OPENMAGIC, digest, load, repository_state, write_json

ALLOW_ENV=('PATH','HOME','GOCACHE','GOMODCACHE','GOPATH','GOFLAGS')

def main():
    ticket=load(ROOT/'outputs/ticket.json'); receipts=[]
    for gate in ticket['gates']:
        if gate['phase']!='creation': continue
        started=datetime.datetime.now(datetime.timezone.utc); mono=time.monotonic()
        proc=subprocess.run(gate['argv'],cwd=gate['cwd'],env=os.environ.copy(),capture_output=True)
        ended=datetime.datetime.now(datetime.timezone.utc)
        out_rel=f"gate-receipts/{gate['id']}.stdout"; err_rel=f"gate-receipts/{gate['id']}.stderr"
        (ROOT/out_rel).write_bytes(proc.stdout[-65536:]); (ROOT/err_rel).write_bytes(proc.stderr[-65536:])
        command={'argv':gate['argv'],'cwd':gate['cwd'],'environment':{k:os.environ[k] for k in ALLOW_ENV if k in os.environ}}
        receipt={'schema':'factory.gate-execution-receipt/v1','gate_id':gate['id'],'command_digest':digest(command),'command':command,
          'repository_state':[repository_state(OPS,[]),repository_state(MAGIC,[]),repository_state(OPENMAGIC,[])],
          'started_at':started.isoformat(),'ended_at':ended.isoformat(),'wall_time_ms':int((time.monotonic()-mono)*1000),'exit_code':proc.returncode,
          'stdout':{'path':out_rel,'sha256':digest((ROOT/out_rel).read_bytes()),'bytes':(ROOT/out_rel).stat().st_size},
          'stderr':{'path':err_rel,'sha256':digest((ROOT/err_rel).read_bytes()),'bytes':(ROOT/err_rel).stat().st_size},
          'result':'passed' if proc.returncode==gate['expected_exit'] else 'failed'}
        write_json(ROOT/f"gate-receipts/{gate['id']}.json",receipt); receipts.append(receipt)
    stable=[{k:x[k] for k in ('gate_id','command_digest','exit_code','result')} for x in receipts]
    write_json(ROOT/'gate-receipts/index.json',{'schema':'factory.gate-receipt-set/v1','receipts':receipts,'receipt_set_hash':digest(stable)})
    if any(x['result']!='passed' for x in receipts): raise SystemExit(1)

if __name__=='__main__': main()
