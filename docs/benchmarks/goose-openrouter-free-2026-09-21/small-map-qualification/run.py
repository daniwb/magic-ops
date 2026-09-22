"""Frozen small-Map qualification; same runner/gates, isolated receipts/intake.

Usage: python run.py --preflight; python run.py --case gained-life
"""
import argparse,ast,hashlib,importlib.util,json,subprocess,sys,tempfile,time
from pathlib import Path
OUT=Path(__file__).resolve().parent
OPS=OUT.parents[3]
sys.path.insert(0,str(OPS/'scripts'))
CASES={'gained-life':'map-static-condition-gained-life-pump-v1.json',
       'drawn-two':'map-static-condition-drawn-two-keywords-v1.json',
       'graveyard-thresholds':'map-static-condition-graveyard-thresholds-v1.json'}
spec=importlib.util.spec_from_file_location('qualification_runner',OPS/'scripts/factory-ng-run-engine-ticket.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

def source_evidence(repo):
    path=Path(repo)/'scripts/paragraph/reparse.py';source=path.read_text();lines=source.splitlines()
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='parse_static_condition')
    if node.end_lineno-node.lineno>400:raise RuntimeError('Seam exceeds small-task evidence bound')
    return ('\n\n## Qualification: complete exact parser seam at the pinned revision\n'
            'This is read-only evidence; original scope and behavior still apply.\n'
            '### scripts/paragraph/reparse.py:%d-%d\n```python\n%s\n```\n' %
            (node.lineno,node.end_lineno,'\n'.join(lines[node.lineno-1:node.end_lineno])))

def preflight():
    rows=[]
    for name,filename in CASES.items():
        ticket_path=OPS/'docs/factory-ng/tickets'/filename;t=json.loads(ticket_path.read_text())
        with tempfile.TemporaryDirectory(prefix='goose-map-preflight-') as d:
            subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(runner.SOURCE),d],check=True)
            subprocess.run(['git','checkout','--quiet','--detach',t['source']['revision']],cwd=d,check=True)
            problems=runner.preparation_problems(t,Path(d))
            if problems:raise RuntimeError(str(problems))
            evidence=source_evidence(d)
            packet=subprocess.run([sys.executable,str(OPS/'scripts/map-ticket-spec-pack.py'),'--ticket-spec',str(ticket_path),'--repo',d],capture_output=True,text=True,check=True)
            measure=runner.ticket_gate(t['gates'][-1],Path(d),t)
            measured=json.loads(measure['stdout'])
            if measure['exit_code']!=1 or measured['member_count']<=0:raise RuntimeError('Expected genuine baseline misses: '+str(measure))
            row={'case':name,'ticket':str(ticket_path.relative_to(OPS)), 'ticket_sha256':hashlib.sha256(ticket_path.read_bytes()).hexdigest(),
                 'source_revision':t['source']['revision'],'baseline_measurement':measured,'packet_chars':len(packet.stdout+evidence),'complete_seam_chars':len(evidence),'preparation_problems':problems}
            rows.append(row);print(name,'baseline misses',measured['member_count'],'packet chars',row['packet_chars'],flush=True)
    (OUT/'preflight.json').write_text(json.dumps(rows,indent=2)+'\n')

def handoff_evidence(repo, ticket):
    measurement=next(OPS/e['path'] for e in ticket['evidence'] if e.get('path','').startswith('docs/factory-ng/measurements/'))
    members=json.loads(measurement.read_text())['members']
    names=[m['name'] for m in members]
    code='''import json,sys
sys.path.insert(0,sys.argv[1]+'/scripts/paragraph')
import reparse
original=reparse.parse_static_condition
calls=[]
def traced(text):
    value=original(text);calls.append({'input':text,'result':value});return value
reparse.parse_static_condition=traced
rows=[]
for name in json.loads(sys.argv[2]):
    calls.clear();card=reparse.load_card(name)
    assert card is not None,name
    result=reparse.reparse_card(card)
    rows.append({'card':name,'oracle':card['text'],'condition_calls':list(calls),'misses':result['misses']})
print(json.dumps(rows,indent=2))
'''
    checked=subprocess.run([sys.executable,'-c',code,str(repo),json.dumps(names)],capture_output=True,text=True,check=True)
    return '\n\n## Measured public parser handoffs at this pinned revision\n'+checked.stdout

def run(name, handoffs=False):
    assert (OUT/'preflight.json').exists(),'Preflight first'
    ticket=OPS/'docs/factory-ng/tickets'/CASES[name]
    expected=next(v for v in json.loads((OUT/'preflight.json').read_text()) if v['case']==name)
    assert hashlib.sha256(ticket.read_bytes()).hexdigest()==expected['ticket_sha256']
    directory=OUT/(name+'-handoff' if handoffs else name);directory.mkdir(exist_ok=True)
    if list((directory/'runs').glob('*-goose-openrouter-staged.json')):
        raise RuntimeError('Completed benchmark exists; use a fresh output directory for another run')
    runner.RUNS=directory/'runs';runner.CANDIDATES=directory/'candidates'
    original=runner.call
    def call(command,cwd,stdin=None,**kwargs):
        result=original(command,cwd,stdin=stdin,**kwargs)
        if any(str(p).endswith('map-ticket-spec-pack.py') for p in command) and result['exit_code']==0:
            repo=command[command.index('--repo')+1]
            result['stdout']+=source_evidence(repo)
            if handoffs:
                measured=handoff_evidence(repo,json.loads(ticket.read_text()))
                (directory/'measured-handoffs.txt').write_text(measured)
                result['stdout']+=measured
        return result
    runner.call=call
    sys.argv=['runner','--ticket',str(ticket),'--worker','goose-small-map-qualification',
              '--profile','openrouter-goose-staged@1.0.0','--model','openrouter/free']
    start=time.monotonic()
    try:runner.main()
    finally:(directory/'timing.json').write_text(json.dumps({'elapsed_seconds':round(time.monotonic()-start,3)},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');p.add_argument('--case',choices=CASES);p.add_argument('--handoffs',action='store_true');args=p.parse_args()
    if args.preflight:preflight()
    elif args.case:run(args.case,args.handoffs)
    else:p.error('Select preflight or case')
