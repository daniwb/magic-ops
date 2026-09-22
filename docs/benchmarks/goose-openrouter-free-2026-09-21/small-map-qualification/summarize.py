"""Summarize the completed, frozen three-case qualification receipts."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
rows=[]
for case in json.loads((ROOT/'preflight.json').read_text()):
    name=case['case'];directory=ROOT/name
    receipts=list((directory/'runs').glob('*-goose-openrouter-staged.json'))
    if len(receipts)!=1:raise SystemExit('Expected one completed receipt for '+name)
    receipt=receipts[0];r=json.loads(receipt.read_text());telemetry=r['model']['telemetry']
    failures=[g for g in r['gates'] if g['outcome']!='passed']
    measurement=None
    for gate in r['gates']:
        if 'reports zero remaining pinned members' in gate.get('command',''):
            try:measurement=json.loads(gate['detail'])
            except ValueError:pass
    costs=[];normalizations=0;provider_failures=[]
    for p in (directory/'runs').glob('*.raw.json'):
        a=json.loads(p.read_text());normalizations+=len(a.get('marker_normalizations',[]))
        if a.get('failure_reason'):provider_failures.append(a['failure_reason'])
        for line in a.get('events','').splitlines():
            try:e=json.loads(line)
            except ValueError:continue
            if e.get('type')=='complete' and isinstance(e.get('cost_usd'),(int,float)):costs.append(e['cost_usd'])
    passed=r['outcome']=='accepted_for_dependent_observation' and not failures and measurement is not None and measurement['member_count']==0 and measurement['pinned_unresolved_count']==0
    rows.append({'case':name,'receipt':str(receipt.relative_to(ROOT)),'outcome':r['outcome'],'passed_all_original_gates':passed,
                 'baseline_pinned_misses':case['baseline_measurement']['member_count'],'final_measurement':measurement,
                 'model_calls':telemetry.get('model_calls'),'input_tokens':telemetry.get('input_tokens'),
                 'output_tokens':telemetry.get('output_tokens'),'elapsed_seconds':json.loads((directory/'timing.json').read_text())['elapsed_seconds'],
                 'used_need':telemetry.get('need_continuation_attempted',False),
                 'used_correction':telemetry.get('bounded_repair_attempted',False),'marker_normalizations':normalizations,
                 'reported_cost_usd':sum(costs) if len(costs)==telemetry.get('model_calls') else None,
                 'provider_failure_reasons':provider_failures,'failed_gates':failures,
                 'earlier_failures':[g for attempt in r.get('attempt_history',[]) for g in attempt.get('gates',[]) if g['outcome']!='passed']})
summary={'cases':rows,'passed':sum(r['passed_all_original_gates'] for r in rows),'total':len(rows),
         'production_worker_enabled':False,'integrated':False,'full_six_shard_integration_run':False,
         'scope':'Three historical parser-only Map tasks with complete parser-function evidence; original ticket gates in isolated clones. Not Engine qualification or a controlled model comparison.'}
followups=list((ROOT/'graveyard-thresholds-handoff/runs').glob('*-goose-openrouter-staged.json'))
if followups:
    assert len(followups)==1
    r=json.loads(followups[0].read_text())
    summary['separate_followup']={'case':'graveyard-thresholds-handoff',
        'receipt':str(followups[0].relative_to(ROOT)), 'outcome':r['outcome'],
        'evidence_change':'Added actual parse_static_condition inputs/results measured while parsing all seven pinned cards at the original revision.',
        'model_calls':r['model']['telemetry'].get('model_calls'),
        'failed_gates':[g for g in r['gates'] if g['outcome']!='passed'],
        'elapsed_seconds':json.loads((ROOT/'graveyard-thresholds-handoff/timing.json').read_text())['elapsed_seconds']}
(ROOT/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='cases'},indent=2))
for row in rows:print(row['case'],row['outcome'],row['elapsed_seconds'],'seconds',row['model_calls'],'calls')
