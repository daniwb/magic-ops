#!/usr/bin/env python3
"""Pipeline-faithful Factory NG profile benchmark.

The model is read-only (or Qwen's read-only tool loop).  Only this harness
applies its structured patch blocks and runs the fixed acceptance contract.
"""
import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
OPS = pathlib.Path('/opt/development/magic-ops')
REPO = pathlib.Path('/opt/development/test/openmagic')
BASE = json.loads((ROOT / 'models.json').read_text())['base_commit']
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
    started = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=cwd, input=stdin, text=True,
                           capture_output=True, timeout=timeout)
        return {'argv': cmd, 'exit_code': p.returncode, 'stdout': p.stdout,
                'stderr': p.stderr,
                'wall_seconds': round(time.monotonic() - started, 3)}
    except subprocess.TimeoutExpired as exc:
        return {'argv': cmd, 'exit_code': 124, 'stdout': exc.stdout or '',
                'stderr': exc.stderr or '',
                'wall_seconds': round(time.monotonic() - started, 3)}


def code_region(path, anchor, before, after, relative_to):
    lines = path.read_text(encoding='utf-8').splitlines()
    hit = next((i for i, line in enumerate(lines) if anchor in line), None)
    if hit is None:
        raise RuntimeError(f'anchor not found: {path}:{anchor}')
    lo, hi = max(0, hit - before), min(len(lines), hit + after + 1)
    return '### %s:%d-%d\n%s' % (
        path.relative_to(relative_to).as_posix(), lo + 1, hi,
        '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(lo, hi)))


def evidence_packet(worktree):
    parser = worktree / 'scripts/paragraph/reparse.py'
    converter = worktree / 'backend/cards/converter.go'
    parts = [
        '# Frozen Ticket Execution Bundle\n',
        'Ticket: `benchmark.map.target-player-draw/v2`  ',
        'Work type: `map`  ',
        'Source revision: `%s`\n' % BASE,
        '## Required behavior\n',
        'Map `Target player draws two cards.` to `draw`, amount 2, with the ',
        'bare real player target `{filter: player}`.  Existing `target opponent` ',
        'and `each opponent` behavior must remain unchanged.  `each player` and ',
        'referential `that player` remain honest misses.\n',
        'This is a Map ticket.  The existing Engine already resolves a targeted ',
        'draw correctly; the acceptance contract checks that the typed target is ',
        'not lost at the Map-to-converter boundary.\n',
        '## Scope and authority\n',
        '- Allowed product files: `scripts/paragraph/reparse.py`, ',
        '`backend/cards/converter.go`, and focused tests under `backend/cards/`.\n',
        '- Forbidden: `backend/game/`, `backend/cardfns/`, corpus/generated data, ',
        'commits, pushes, deployment, ticket mutation.\n',
        '- Emit only exact patch blocks accepted by the harness:\n\n',
        '```text\n<<<FILE relative/path\n<<<SEARCH\nexact old text\n===REPLACE\nnew text\n>>>END\n```\n',
        'Or return one explicit `VERDICT: AMBIGUOUS|SEMANTIC_GAP|MISMATCH` with ',
        'a one-line `REASON:`.  If an essential region is absent, request at ',
        'most three exact regions with `NEED: path symbol`.\n',
        '## Acceptance contract owned by harness\n',
        '1. Exact positive and adjacent-negative parser behavior.\n',
        '2. DSL `TargetFilter{player}` survives `ToGameCard`; cast requires a ',
        'player target; selected player rather than controller draws.\n',
        '3. Existing parser and cards regression suites pass.\n',
        '4. Scope discipline and `git diff --check` pass.\n',
        '## Indexed evidence\n',
        code_region(parser, "if verb == 'p_draw':", 2, 13, worktree), '\n',
        code_region(converter, 'case "draw":', 2, 35, worktree), '\n',
        code_region(converter, 'func (def *CardDefinition) ToGameCard', 0, 30, worktree), '\n',
        '## Decision guidance\n',
        'A nearby `p_gain_life` branch already demonstrates that a fixed-amount ',
        '`target player` phrase is a real target represented by a separate ',
        'target tuple.  Do not add a controller/opponent value shortcut for ',
        '`target player`, and do not change Engine code.\n'
    ]
    packet = ''.join(parts)
    digest = hashlib.sha256(packet.encode()).hexdigest()
    return packet, digest


def usage_codex(raw):
    usage = {}
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('type') == 'turn.completed':
            usage = event.get('usage', {})
    return {'input_tokens': usage.get('input_tokens', 0),
            'cached_input_tokens': usage.get('cached_input_tokens', 0),
            'cache_write_input_tokens': usage.get('cache_write_input_tokens', 0),
            'output_tokens': usage.get('output_tokens', 0),
            'reasoning_output_tokens': usage.get('reasoning_output_tokens', 0)}


def answer_codex(raw):
    """Extract the final natural-language item from Codex's JSONL stream."""
    answer = ''
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get('item', {})
        if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
            answer = item.get('text', '')
    return answer


def usage_claude(raw):
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = {}
    per_model = obj.get('modelUsage', {})
    aggregate = {
        'input_tokens': sum(v.get('inputTokens', 0) for v in per_model.values()),
        'cached_input_tokens': sum(v.get('cacheReadInputTokens', 0) for v in per_model.values()),
        'cache_write_input_tokens': sum(v.get('cacheCreationInputTokens', 0) for v in per_model.values()),
        'output_tokens': sum(v.get('outputTokens', 0) for v in per_model.values()),
        'provider_cost_usd': sum(v.get('costUSD', 0) for v in per_model.values()),
    }
    if not per_model:
        usage = obj.get('usage', {})
        aggregate.update({'input_tokens': usage.get('input_tokens', 0),
                          'cached_input_tokens': usage.get('cache_read_input_tokens', 0),
                          'cache_write_input_tokens': usage.get('cache_creation_input_tokens', 0),
                          'output_tokens': usage.get('output_tokens', 0)})
    aggregate['reasoning_output_tokens'] = obj.get('usage', {}).get('output_tokens_details', {}).get('thinking_tokens', 0)
    aggregate['resolved_model_usage'] = per_model
    return aggregate


def usage_qwen(stderr):
    totals = {'input_tokens': 0, 'cached_input_tokens': 0,
              'uncached_input_tokens': 0,
              'cache_write_input_tokens': 0, 'output_tokens': 0,
              'reasoning_output_tokens': 0}
    for inn, out, cache_r, cache_w in re.findall(
            r'tokens: in=(\d+) out=(\d+) cache_r=(\d+) cache_w=(\d+)', stderr):
        # qwen-agentic reports `in` as the non-cached request portion and
        # `cache_r` separately.  Normalize `input_tokens` to total input,
        # matching Codex/Claude, while retaining the raw non-cached value.
        totals['uncached_input_tokens'] += int(inn)
        totals['input_tokens'] += int(inn) + int(cache_r)
        totals['output_tokens'] += int(out)
        totals['cached_input_tokens'] += int(cache_r)
        totals['cache_write_input_tokens'] += int(cache_w)
    return totals


def add_usage(left, right):
    out = {}
    for key in ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
                'output_tokens', 'reasoning_output_tokens'):
        out[key] = left.get(key, 0) + right.get(key, 0)
    if 'uncached_input_tokens' in left or 'uncached_input_tokens' in right:
        out['uncached_input_tokens'] = left.get('uncached_input_tokens', 0) + right.get('uncached_input_tokens', 0)
    return out


def price(model, usage):
    rates = model['rates_per_million']
    cached = usage['cached_input_tokens']
    uncached = max(0, usage['input_tokens'] - cached)
    return round((uncached * rates.get('input', 0) + cached * rates.get('cached_input', rates.get('input', 0)) +
                  usage['cache_write_input_tokens'] * rates.get('cache_write', 0) +
                  usage['output_tokens'] * rates.get('output', 0)) / 1_000_000, 6)


def call_model(model, prompt, worktree):
    engine = model['engine']
    if engine == 'qwen-prepared':
        result = run(['python3', str(OPS / 'scripts/qwen-prepared-call.py'),
                      '--model', model['model'], '--max-tokens', '2000'],
                     worktree, stdin=prompt)
        return result, result['stdout'], usage_qwen(result['stderr'])
    if engine == 'codex':
        result = run(['codex', 'exec', '--ephemeral', '--json', '--sandbox', 'read-only',
                      '--model', model['model'], prompt], worktree)
        return result, answer_codex(result['stdout']), usage_codex(result['stdout'])
    if engine == 'claude':
        command = ['claude', '-p', '--output-format', 'json', '--model', model['model'],
                   '--max-turns', '5', '--permission-mode', 'bypassPermissions',
                   '--no-session-persistence', '--disallowedTools',
                   'Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill,NotebookEdit',
                   '--append-system-prompt',
                   'You have no working tools for this call. Return plain text patch blocks or a structured decision only.']
        result = run(command, worktree, stdin=prompt)
        try:
            text = json.loads(result['stdout']).get('result', '')
        except json.JSONDecodeError:
            text = ''
        return result, text, usage_claude(result['stdout'])
    result = run(['python3', str(OPS / 'scripts/qwen-agentic-call.py'), '--repo', str(worktree),
                  '--model', model['model'], '--max-turns', '25', '--max-tokens', '8000'],
                 worktree, stdin=prompt)
    return result, result['stdout'], usage_qwen(result['stderr'])


def gate_suite(worktree):
    map_path = worktree / 'scripts/paragraph/zz_benchmark_external_test.py'
    go_path = worktree / 'backend/cards/zz_benchmark_external_test.go'
    map_path.write_text(MAP_TEST)
    go_path.write_text(GO_TEST)
    try:
        gates = {
            'map_external': run(['python3', '-m', 'unittest', 'scripts.paragraph.zz_benchmark_external_test'], worktree, 120),
            'engine_boundary': run(['go', 'test', './cards', '-run', '^TestBenchmarkExternalTargetPlayerDraw$', '-count=1'], worktree / 'backend', 300),
            'parser_regression': run(['python3', '-m', 'unittest', 'discover', '-s', 'scripts/paragraph', '-p', 'test_*.py'], worktree, 180),
            'cards_regression': run(['go', 'test', './cards', '-count=1'], worktree / 'backend', 600),
        }
    finally:
        map_path.unlink(missing_ok=True)
        go_path.unlink(missing_ok=True)
    diff = run(['git', 'diff', '--check'], worktree, 30)
    names = run(['git', 'status', '--short'], worktree, 30)
    changed = [line[3:] for line in names['stdout'].splitlines() if line]
    allowed = lambda p: p == 'scripts/paragraph/reparse.py' or p == 'backend/cards/converter.go' or (p.startswith('backend/cards/') and p.endswith('_test.go'))
    scope_ok = bool(changed) and all(allowed(path) for path in changed)
    passed = all(g['exit_code'] == 0 for g in gates.values()) and diff['exit_code'] == 0 and scope_ok
    return gates, diff, changed, scope_ok, passed


def model_prompt(model, packet):
    profile = model['profile'].split('@')[0]
    if profile == 'qwen-prepared-direct':
        prefix = ('You are the prepared-direct implementation profile. All required facts and exact code regions are in the packet. '
                  'Do not ask for repository access or use tool-call syntax. ')
    elif profile == 'qwen-prepared-local':
        prefix = ('You are the prepared-local implementation profile. The packet already contains the exact decision and code regions. '
                  'Use read-only tools only if a literal SEARCH block needs confirmation; do not browse broadly. ')
    else:
        prefix = ('You are the constrained staged implementation profile. The packet contains all required evidence. ')
    return prefix + 'Return a minimal product patch using the declared block format; do not describe a hypothetical patch.\n\n' + packet


def run_one(model, dry_run=False):
    RUNS.mkdir(exist_ok=True)
    worktree = pathlib.Path('/tmp') / ('factory-ng-profile-v2-' + model['id'])
    if worktree.exists():
        run(['git', 'worktree', 'remove', '--force', str(worktree)], REPO, 180)
    setup = run(['git', 'worktree', 'add', '--detach', str(worktree), BASE], REPO, 180)
    record = {'schema': 'factory.model-benchmark-run/v2', 'model': model, 'setup': setup}
    try:
        if setup['exit_code'] != 0:
            record['status'] = 'INFRASTRUCTURE_FAILURE'
            return record
        packet, digest = evidence_packet(worktree)
        record['ticket'] = {'id': 'benchmark.map.target-player-draw/v2', 'work_type': 'map',
                            'source_revision': BASE, 'evidence_sha256': digest,
                            'acceptance_contract': 'harness-owned-map-converter-engine-boundary/v1'}
        if dry_run:
            record['status'] = 'DRY_RUN_READY'
            return record
        total_usage = {}
        calls = []
        prompt = model_prompt(model, packet)
        # At most one bounded NEED exchange before mutation.
        for need_round in range(2):
            call, answer, usage = call_model(model, prompt, worktree)
            calls.append({'kind': 'initial' if need_round == 0 else 'need_response', 'call': call, 'answer': answer, 'usage': usage})
            total_usage = add_usage(total_usage, usage)
            if not re.search(r'^NEED:\s*', answer, re.M) or need_round == 1:
                break
            fetched = run(['python3', str(OPS / 'scripts/pipeline-fetch-regions.py')], worktree, 60, answer)
            calls[-1]['need_fetch'] = fetched
            prompt += '\n\n## Bounded NEED response\n' + fetched['stdout'] + '\nNow return the final patch or verdict.\n'
        answer = calls[-1]['answer'] if calls else ''
        apply = run(['python3', str(OPS / 'scripts/map-pipeline-apply.py')], worktree, 60, answer)
        record['calls'] = calls
        record['apply'] = apply
        repair = None
        if apply['exit_code'] == 4:
            record.update({'status': 'PARKED', 'usage': total_usage,
                           'cost_usd': calls[-1]['usage'].get('provider_cost_usd', price(model, total_usage)),
                           'total_wall_seconds': round(sum(c['call']['wall_seconds'] for c in calls), 3)})
            return record
        if apply['exit_code'] != 0:
            # This is the old staged pipeline's bounded format-repair path:
            # a sound patch can still fail because its SEARCH window was too
            # short.  The model receives the exact applier error, not a new
            # exploratory mission, and has one final corrective response.
            repair_prompt = (model_prompt(model, packet) + '\n\n## Harness apply failure\n' +
                             apply['stdout'] + apply['stderr'] +
                             '\nThe harness applies patch blocks atomically: no part of the previous response was applied. '
                             'Repeat every product-file patch still required, using corrected exact SEARCH windows.\n'
                             '## Previous attempted response\n' + answer +
                             '\n## Required response\nReturn the complete corrected patch only.')
            repair_call, repair_answer, repair_usage = call_model(model, repair_prompt, worktree)
            total_usage = add_usage(total_usage, repair_usage)
            repair_apply = run(['python3', str(OPS / 'scripts/map-pipeline-apply.py')], worktree, 60, repair_answer)
            repair = {'call': repair_call, 'answer': repair_answer, 'usage': repair_usage, 'apply': repair_apply}
            if repair_apply['exit_code'] != 0:
                record.update({'status': 'CONTRACT_FAILED', 'usage': total_usage,
                               'cost_usd': sum(c['usage'].get('provider_cost_usd', 0) for c in calls) + repair_usage.get('provider_cost_usd', 0) or price(model, total_usage),
                               'repair': repair})
                return record
        gates, diff, changed, scope_ok, passed = gate_suite(worktree)
        if not passed and repair is None:
            failed = {name: gate['stderr'][-4000:] for name, gate in gates.items() if gate['exit_code'] != 0}
            repair_prompt = model_prompt(model, packet) + '\n\n## Harness result after your first patch\n' + json.dumps({'failed_gates': failed, 'diff_check': diff['stderr'], 'changed_paths': changed}, indent=2) + '\nReturn one corrective patch block only.'
            repair_call, repair_answer, repair_usage = call_model(model, repair_prompt, worktree)
            total_usage = add_usage(total_usage, repair_usage)
            repair_apply = run(['python3', str(OPS / 'scripts/map-pipeline-apply.py')], worktree, 60, repair_answer)
            repair = {'call': repair_call, 'answer': repair_answer, 'usage': repair_usage, 'apply': repair_apply}
            if repair_apply['exit_code'] == 0:
                gates, diff, changed, scope_ok, passed = gate_suite(worktree)
        scores = {'map_behavior': 35 if gates['map_external']['exit_code'] == 0 else 0,
                  'engine_boundary': 35 if gates['engine_boundary']['exit_code'] == 0 else 0,
                  'regressions': 15 if gates['parser_regression']['exit_code'] == 0 and gates['cards_regression']['exit_code'] == 0 else 0,
                  'scope': 15 if scope_ok and diff['exit_code'] == 0 else 0}
        record.update({'status': 'COMPLETE', 'usage': total_usage,
                       'cost_usd': sum(c['usage'].get('provider_cost_usd', 0) for c in calls) + (repair or {}).get('usage', {}).get('provider_cost_usd', 0) or price(model, total_usage),
                       'gates': gates, 'diff_check': diff, 'changed_paths': changed,
                       'scope_ok': scope_ok, 'scores': scores, 'quality_score': sum(scores.values()),
                       'accepted': passed, 'repair': repair,
                       'total_wall_seconds': round(sum(c['call']['wall_seconds'] for c in calls) + (repair or {}).get('call', {}).get('wall_seconds', 0), 3)})
        return record
    finally:
        (RUNS / (model['id'] + '.json')).write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
        if worktree.exists():
            run(['git', 'worktree', 'remove', '--force', str(worktree)], REPO, 180)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-id')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    models = json.loads((ROOT / 'models.json').read_text())['models']
    selected = [m for m in models if not args.model_id or m['id'] == args.model_id]
    if not selected:
        raise SystemExit('unknown model id')
    for model in selected:
        result = run_one(model, args.dry_run)
        print(json.dumps({'model': model['id'], 'status': result['status'],
                          'accepted': result.get('accepted'),
                          'quality_score': result.get('quality_score'),
                          'receipt': str(RUNS / (model['id'] + '.json'))}))


if __name__ == '__main__':
    main()
