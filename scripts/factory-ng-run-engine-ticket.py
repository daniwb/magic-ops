#!/usr/bin/env python3
"""Run one bounded Map or Engine TicketSpec through Claude or Codex in a clone.

The adapter is read-only; only this harness applies strict edit blocks and
runs the TicketSpec's declared gates.  It records an observation receipt and
never touches the canonical checkout, pushes, or integrates a candidate.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
SOURCE = Path('/opt/development/test/openmagic')
RUNS = OPS / 'docs/factory-ng/runs'
CANDIDATES = OPS / 'docs/factory-ng/candidates'

def digest(value): return 'sha256:' + hashlib.sha256(value).hexdigest()
def file_digest(path): return digest(Path(path).read_bytes())
def stamp(): return time.strftime('%Y-%m-%dT%H%M%SZ', time.gmtime())

def call(command, cwd, stdin=None, timeout=1200, env=None):
    start = time.monotonic()
    try:
        p = subprocess.run(command, cwd=cwd, input=stdin, text=True, capture_output=True,
                           timeout=timeout, env=env)
        return {'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr,
                'elapsed_ms': round((time.monotonic()-start)*1000)}
    except subprocess.TimeoutExpired as exc:
        return {'exit_code': 124, 'stdout': exc.stdout or '', 'stderr': exc.stderr or '',
                'elapsed_ms': round((time.monotonic()-start)*1000)}

def counters(stderr, elapsed):
    hit = re.findall(r'tokens: in=(\d+) out=(\d+) cache_r=(\d+) cache_w=(\d+)', stderr)
    if not hit:
        unknown = {'availability':'unavailable', 'reason':'adapter emitted no token counter'}
        return {'input_tokens':unknown,'output_tokens':unknown,'cache_read_tokens':unknown,
                'cache_write_tokens':unknown,'reasoning_tokens':unknown,
                'provider_cost_usd':{'availability':'unavailable','reason':'provider cost unavailable'},'elapsed_ms':elapsed}
    inn,out,read,write = map(int, hit[-1])
    return {'input_tokens':inn,'output_tokens':out,'cache_read_tokens':read,'cache_write_tokens':write,
            'reasoning_tokens':{'availability':'unavailable','reason':'adapter aggregates reasoning into output when applicable'},
            'provider_cost_usd':{'availability':'unavailable','reason':'local adapter has no versioned pricing record'},'elapsed_ms':elapsed}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ticket',required=True,type=Path); ap.add_argument('--worker',required=True)
    ap.add_argument('--model',required=True); ap.add_argument('--profile',required=True)
    args=ap.parse_args(); ticket_path=args.ticket.resolve(); ticket=json.loads(ticket_path.read_text())
    if ticket.get('schema')!='factory.ticket-spec/v1' or ticket.get('work_type') not in ('map','engine'): ap.error('Map or Engine TicketSpec required')
    engines={'claude-staged@1.0.0':'claude','codex-constrained@1.0.0':'codex'}
    engine=engines.get(args.profile)
    if not engine: ap.error('unsupported Engine profile')
    if ticket.get('execution',{}).get('selected_profile')!=args.profile: ap.error('worker profile does not match TicketSpec')
    if subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True): ap.error('canonical source must be clean')
    slug=ticket['id'].removeprefix('ticket:').replace('/','-').replace('.','-'); RUNS.mkdir(parents=True,exist_ok=True); CANDIDATES.mkdir(parents=True,exist_ok=True)
    raw=RUNS/(stamp()+'-'+slug+'-'+engine+'.raw.json'); receipt=RUNS/(stamp()+'-'+slug+'-'+engine+'.json')
    clone=Path(tempfile.mkdtemp(prefix='factory-ng-'+slug+'-',dir='/tmp'))
    outcome='infrastructure_failed'; gates=[]; changed=[]; result_commit='unavailable'; candidate_patch=None
    try:
        clone_result=call(['git','clone','--quiet','--no-hardlinks',str(SOURCE),str(clone)],OPS,timeout=180)
        if clone_result['exit_code']!=0: raise RuntimeError('clone failed')
        packer = OPS / ('engine-pipeline-pack.py' if ticket['work_type']=='engine' else 'map-ticket-spec-pack.py')
        pack_command=[sys.executable,str(packer),'--ticket-spec',str(ticket_path),'--repo',str(clone)]
        if ticket['work_type']=='engine': pack_command.append('--no-tools')
        packet=call(pack_command,OPS,timeout=180)
        if packet['exit_code']!=0: raise RuntimeError('packet failed: '+packet['stderr'][-300:])
        env=os.environ.copy(); env['PIPE_RAW_ARTIFACT']=str(raw)
        model=call([sys.executable,str(OPS/'scripts/model_call.py'),'--engine',engine,'--model',args.model,'--tier',ticket['work_type']],clone,stdin=packet['stdout'],timeout=1260,env=env)
        if not raw.exists(): raw.write_text(model['stdout'])
        telemetry=counters(model['stderr'],model['elapsed_ms'])
        apply_cmd=[sys.executable,str(OPS/'scripts/map-pipeline-apply.py')]
        if ticket['work_type']=='engine': apply_cmd.append('--allow-game')
        apply=call(apply_cmd,clone,stdin=model['stdout'],timeout=60)
        gates.append({'id':'patch-apply','outcome':'passed' if apply['exit_code']==0 else 'failed','detail':(apply['stdout']+apply['stderr'])[-800:]})
        if model['exit_code']!=0: outcome='infrastructure_failed'
        elif apply['exit_code']==4: outcome='parked'
        elif apply['exit_code']==0:
            names=call(['git','diff','--name-only'],clone,timeout=30); changed=[x for x in names['stdout'].splitlines() if x]
            allowed=set(ticket['scope']['allowed_paths']); scope_ok=bool(changed) and set(changed).issubset(allowed)
            gates.append({'id':'scope','outcome':'passed' if scope_ok else 'failed','detail':'changed='+','.join(changed)})
            for index, command in enumerate(ticket.get('gates',[])):
                gate=call(['bash','-lc',command],clone,timeout=720)
                gates.append({'id':'ticket-gate-%d'%index,'outcome':'passed' if gate['exit_code']==0 else 'failed','detail':(gate['stdout']+gate['stderr'])[-800:]})
            if all(g['outcome']=='passed' for g in gates):
                call(['git','add','-A'],clone,timeout=60)
                commit=call(['git','-c','user.name=Factory NG','-c','user.email=factory-ng@local','commit','-m','factory-ng: supervised engine observation'],clone,timeout=60)
                if commit['exit_code']==0:
                    outcome='accepted_for_dependent_observation'
                    exported=call(['git','format-patch','-1','--stdout','HEAD'],clone,timeout=60)
                    if exported['exit_code']==0:
                        candidate_patch=CANDIDATES/(stamp()+'-'+slug+'.patch'); candidate_patch.write_text(exported['stdout'])
                    else:
                        outcome='infrastructure_failed_candidate_export'
                        gates.append({'id':'candidate-export','outcome':'failed','detail':exported['stderr'][-800:]})
                else: gates.append({'id':'candidate-commit','outcome':'failed','detail':commit['stderr'][-800:]})
            else: outcome='gate_failed'
        result_commit=call(['git','rev-parse','HEAD'],clone,timeout=30)['stdout'].strip()
    except Exception as exc:
        raw.write_text('runner failure: %s\n'%exc)
        telemetry={'input_tokens':{'availability':'unavailable','reason':'runner failed before model'},'output_tokens':{'availability':'unavailable','reason':'runner failed before model'},'cache_read_tokens':{'availability':'unavailable','reason':'runner failed before model'},'cache_write_tokens':{'availability':'unavailable','reason':'runner failed before model'},'reasoning_tokens':{'availability':'unavailable','reason':'runner failed before model'},'provider_cost_usd':{'availability':'unavailable','reason':'runner failed before model'},'elapsed_ms':0}
    source_changed=bool(subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True).strip())
    value={'schema':'factory.observation-receipt/v1','ticket':{'id':ticket['id'],'path':str(ticket_path.relative_to(OPS)),'sha256':file_digest(ticket_path)},'skill':ticket['skill'],'model':{'profile':args.profile,'resolved_model':args.model,'worker':args.worker,'telemetry':telemetry},'execution':{'mode':'isolated_clone_observation_only','source_revision':ticket['source']['revision'],'source_tree_changed':source_changed,'candidate_commit':result_commit,'candidate_clone':str(clone)},'raw_artifacts':[{'path':str(raw.relative_to(OPS)),'sha256':file_digest(raw)}],'gates':gates,'outcome':outcome,'integration':'eligible_full_gate' if outcome=='accepted_for_dependent_observation' else 'observation_only','next_action':'Explicit integration decision required; the factory never integrates automatically.'}
    if candidate_patch:
        value['execution']['candidate_patch']=str(candidate_patch.relative_to(OPS)); value['execution']['candidate_patch_sha256']=file_digest(candidate_patch)
        value['next_action']='Factory NG may integrate this durable patch under its configured full-gate policy.'
    receipt.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':outcome,'ticket_id':ticket['id'],'worker':args.worker,'receipt':str(receipt.relative_to(OPS))}))
    if candidate_patch is not None or outcome!='accepted_for_dependent_observation': shutil.rmtree(clone,ignore_errors=True)

if __name__=='__main__': main()
