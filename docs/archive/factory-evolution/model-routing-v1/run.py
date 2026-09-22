#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess, time

ROOT = pathlib.Path(__file__).resolve().parent
OPS = pathlib.Path('/opt/development/magic-ops')
REPO = pathlib.Path('/opt/development/test/openmagic')
BASE = '6d85a3d649103d8f3a50fb6436ed266c77b0942a'
RUNS = ROOT / 'runs'

MAP_TEST = r'''import sys, unittest
sys.path.insert(0, 'scripts/paragraph')
import reparse

class ExternalTargetPlayerDraw(unittest.TestCase):
    def mapped(self, text):
        verb, args = reparse.O.parse_atom(text)
        return reparse.map_atom(verb, args, kind='oneshot')
    def test_positive(self):
        self.assertEqual(self.mapped('Target player draws two cards.'),
                         ('draw', {'amount': 2}, {'filter': 'player'}))
    def test_adjacent(self):
        self.assertEqual(self.mapped('Target opponent draws two cards.'),
                         ('draw', {'amount': 2, 'target': 'opponent'}, None))
        self.assertEqual(self.mapped('Each opponent draws two cards.'),
                         ('draw', {'amount': 2, 'target': 'opponent'}, None))
        self.assertIsNone(self.mapped('Each player draws two cards.'))
        self.assertIsNone(self.mapped('That player draws two cards.'))
'''

GO_TEST = r'''package cards
import (
    "testing"
    "magic-backend/game"
)
func TestBenchmarkExternalTargetPlayerDraw(t *testing.T) {
    def := &CardDefinition{Name:"Benchmark Inspiration", Type:"Instant", Types:[]string{"Instant"},
        Abilities:[]AbilityDSL{{Type:"spell", Effect:"draw", Value:map[string]interface{}{"amount":2},
            Target:&TargetFilter{Filter:"player"}}}, Status:StatusManual}
    spell, err := def.ToGameCard(0); if err != nil { t.Fatal(err) }
    if spell.SpellEffect == nil || spell.SpellEffect.SpellTargetType != game.TargetPlayer {
        t.Fatalf("converter dropped player target: %+v", spell.SpellEffect)
    }
    gs := game.NewGame("controller", "target", false)
    gs.PhaseManager.CurrentPhase = game.Phase{Type:game.PhaseMain1, Step:game.StepMain}
    gs.PrioritySystem.SetActivePlayer(0); gs.GameStarted = true
    for i:=0; i<2; i++ {
        gs.Players[0].Library.AddCard(game.NewCard("C", game.TypeInstant, game.ManaCost{}, 0))
        gs.Players[1].Library.AddCard(game.NewCard("T", game.TypeInstant, game.ManaCost{}, 1))
    }
    gs.Players[0].Hand.AddCard(spell)
    if err := gs.CastSpellWithTargets(0, spell.ID, []game.Target{{IsCard:false, PlayerIdx:1}}); err != nil { t.Fatal(err) }
    if err := gs.ResolveTopOfStack(); err != nil { t.Fatal(err) }
    if got:=len(gs.Players[1].Hand.GetAll()); got != 2 { t.Fatalf("target drew %d", got) }
    if got:=len(gs.Players[0].Hand.GetAll()); got != 0 { t.Fatalf("controller drew %d", got) }
}
'''

def run(cmd, cwd, timeout=1200, stdin=None):
    start = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=cwd, input=stdin, text=True,
                           capture_output=True, timeout=timeout)
        return {'argv':cmd, 'exit_code':p.returncode, 'stdout':p.stdout,
                'stderr':p.stderr, 'wall_seconds':round(time.monotonic()-start, 3)}
    except subprocess.TimeoutExpired as e:
        return {'argv':cmd, 'exit_code':124, 'stdout':e.stdout or '',
                'stderr':e.stderr or '', 'wall_seconds':round(time.monotonic()-start, 3)}

def usage_codex(raw):
    usage = {}
    for line in raw.splitlines():
        try: event=json.loads(line)
        except Exception: continue
        if event.get('type') == 'turn.completed': usage=event.get('usage', {})
    return {'input_tokens':usage.get('input_tokens',0),
            'cached_input_tokens':usage.get('cached_input_tokens',0),
            'cache_write_input_tokens':usage.get('cache_write_input_tokens',0),
            'output_tokens':usage.get('output_tokens',0),
            'reasoning_output_tokens':usage.get('reasoning_output_tokens',0)}

def usage_claude(raw):
    try: obj=json.loads(raw)
    except Exception: obj={}
    u=obj.get('usage', {})
    by_model=obj.get('modelUsage', {})
    # Claude's top-level usage is often only the final turn.  modelUsage is
    # the authoritative aggregate for a whole print-mode session.
    aggregate={
        'inputTokens':sum(v.get('inputTokens',0) for v in by_model.values()),
        'cacheReadInputTokens':sum(v.get('cacheReadInputTokens',0) for v in by_model.values()),
        'cacheCreationInputTokens':sum(v.get('cacheCreationInputTokens',0) for v in by_model.values()),
        'outputTokens':sum(v.get('outputTokens',0) for v in by_model.values()),
        'costUSD':sum(v.get('costUSD',0) for v in by_model.values()),
    }
    return {'input_tokens':aggregate['inputTokens'] or u.get('input_tokens',0),
            'cached_input_tokens':aggregate['cacheReadInputTokens'] or u.get('cache_read_input_tokens',0),
            'cache_write_input_tokens':aggregate['cacheCreationInputTokens'] or u.get('cache_creation_input_tokens',0),
            'output_tokens':aggregate['outputTokens'] or u.get('output_tokens',0),
            'reasoning_output_tokens':u.get('output_tokens_details',{}).get('thinking_tokens',0),
            'provider_cost_usd':aggregate['costUSD'],
            'resolved_model':by_model}

def usage_qwen(stderr):
    hits=re.findall(r'tokens: in=(\d+) out=(\d+) cache_r=(\d+) cache_w=(\d+)', stderr)
    if not hits: return {'input_tokens':0,'output_tokens':0,'cached_input_tokens':0,'cache_write_input_tokens':0,'reasoning_output_tokens':0}
    a=hits[-1]
    return {'input_tokens':int(a[0])+int(a[2]), 'output_tokens':int(a[1]),
            'cached_input_tokens':int(a[2]), 'cache_write_input_tokens':int(a[3]), 'reasoning_output_tokens':0}

def price(model, usage):
    r=model['rates_per_million']; cached=usage['cached_input_tokens']
    uncached=max(0, usage['input_tokens']-cached)
    return round((uncached*r.get('input',0)+cached*r.get('cached_input',r.get('input',0))+
                  usage['cache_write_input_tokens']*r.get('cache_write',0)+
                  usage['output_tokens']*r.get('output',0))/1_000_000, 6)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--model-id'); args=ap.parse_args()
    matrix=json.loads((ROOT/'models.json').read_text())['models']
    selected=[m for m in matrix if not args.model_id or m['id']==args.model_id]
    RUNS.mkdir(exist_ok=True)
    prompt=(ROOT/'prompt.md').read_text()
    for model in selected:
        rid=model['id']; wt=pathlib.Path('/tmp')/f'factory-ng-benchmark-{rid}'
        if wt.exists(): subprocess.run(['git','worktree','remove','--force',str(wt)],cwd=REPO,capture_output=True)
        setup=run(['git','worktree','add','--detach',str(wt),BASE], REPO, 180)
        record={'schema':'factory.model-benchmark-run/v1','model':model,'setup':setup}
        if setup['exit_code'] != 0:
            record['status']='INFRASTRUCTURE_FAILURE'; (RUNS/f'{rid}.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n'); continue
        start=time.monotonic()
        if model['engine']=='codex':
            call=run(['codex','exec','--ephemeral','--dangerously-bypass-approvals-and-sandbox','--json','--model',model['model'],prompt],wt,1200)
            usage=usage_codex(call['stdout'])
        elif model['engine']=='claude':
            call=run(['claude','-p','--output-format','json','--model',model['model'],'--max-turns','25','--max-budget-usd','5','--permission-mode','bypassPermissions','--no-session-persistence',prompt],wt,1200)
            usage=usage_claude(call['stdout'])
        else:
            call=run(['python3',str(OPS/'scripts/qwen-agentic-call.py'),'--repo',str(wt),'--model',model['model'],'--max-turns','18','--max-tokens','16000'],wt,1200,stdin=prompt)
            usage=usage_qwen(call['stderr'])
            if call['stdout'].strip():
                apply=run(['python3',str(OPS/'scripts/map-pipeline-apply.py')],wt,60,stdin=call['stdout'])
                record['apply']=apply
        record['model_call']=call; record['usage']=usage
        record['cost_usd']=usage.get('provider_cost_usd', price(model,usage))
        # Harness-owned tests are temporary and excluded from candidate scope.
        map_path=wt/'scripts/paragraph/zz_benchmark_external_test.py'
        go_path=wt/'backend/cards/zz_benchmark_external_test.go'
        map_path.write_text(MAP_TEST); go_path.write_text(GO_TEST)
        gates={}
        gates['map_external']=run(['python3','-m','unittest','scripts.paragraph.zz_benchmark_external_test'],wt,120)
        gates['engine_external']=run(['go','test','./cards','-run','^TestBenchmarkExternalTargetPlayerDraw$','-count=1'],wt/'backend',300)
        map_path.unlink(); go_path.unlink()
        gates['parser_regression']=run(['python3','-m','unittest','discover','-s','scripts/paragraph','-p','test_*.py'],wt,180)
        gates['cards_regression']=run(['go','test','./cards','-count=1'],wt/'backend',600)
        diff=run(['git','diff','--check'],wt,30); names=run(['git','status','--short'],wt,30)
        changed=[]
        for line in names['stdout'].splitlines():
            if line: changed.append(line[3:])
        allowed=lambda p: p.startswith('scripts/paragraph/') or p in ('backend/cards/converter.go',) or (p.startswith('backend/cards/') and p.endswith('_test.go'))
        scope_ok=bool(changed) and all(allowed(p) for p in changed)
        scores={'map_behavior':35 if gates['map_external']['exit_code']==0 else 0,
                'engine_boundary':35 if gates['engine_external']['exit_code']==0 else 0,
                'regressions':15 if gates['parser_regression']['exit_code']==0 and gates['cards_regression']['exit_code']==0 else 0,
                'scope':15 if scope_ok and diff['exit_code']==0 else 0}
        silent_wrong=gates['map_external']['exit_code']==0 and gates['engine_external']['exit_code']!=0
        quality=0 if silent_wrong else sum(scores.values())
        record.update({'status':'COMPLETE','gates':gates,'diff_check':diff,'changed_paths':changed,
                       'scope_ok':scope_ok,'scores':scores,'quality_score':quality,
                       'silent_wrong':silent_wrong,'total_wall_seconds':round(time.monotonic()-start,3)})
        (RUNS/f'{rid}.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
        subprocess.run(['git','worktree','remove','--force',str(wt)],cwd=REPO,capture_output=True)

if __name__=='__main__': main()
