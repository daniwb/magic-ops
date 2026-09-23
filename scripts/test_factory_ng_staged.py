#!/usr/bin/env python3
"""Regression tests for staged evidence, preparation and bounded gate repair.

Runner tests use real isolated Git clones, strict patch application and shell
gates. Only the packet builder and provider responses are substituted.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from factory_ng_context import (requested_context, preparation_problems,
                                failure_detail, source_path)

OPS = Path(__file__).resolve().parents[1]
# The supervised controller puts the repo toolchain on PATH; do the same so
# the real-Go gate tests run from a plain interactive shell too.
REPO_GO_BIN = OPS.parents[1] / 'toolchain' / 'go' / 'bin'
if (REPO_GO_BIN / 'go').exists() and not shutil.which('go'):
    os.environ['PATH'] = '%s:%s' % (REPO_GO_BIN, os.environ.get('PATH', ''))
GO_TOOLCHAIN = shutil.which('go') or Path('/usr/local/go/bin/go').exists()


def load(filename):
    spec = importlib.util.spec_from_file_location(filename.replace('-', '_'), OPS / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / 'backend/game').mkdir(parents=True)

    def write(self, name, content):
        path = self.repo / 'backend/game' / name
        path.write_text(content)
        return path

    def test_real_dispatch_beats_early_comment_and_includes_named_type(self):
        self.write('effects.go', '// grant_keywords_until_eot fake early hit\n' + '\n' * 220 +
                   'func Execute(effect Effect) {\n\tswitch effect.Type {\n'
                   '\tcase "grant_keywords_until_eot":\n\t\tapply(effect)\n'
                   '\tcase "other":\n\t\tother()\n\t}\n}\n')
        self.write('types.go', 'package game\ntype Effect struct {\n\tType string\n}\n')
        evidence = requested_context('NEED: backend/game/effects.go: grant_keywords_until_eot case in Execute (Effect type)', self.repo)
        self.assertIn('case "grant_keywords_until_eot":', evidence)
        self.assertNotIn('fake early hit', evidence)
        self.assertIn('type Effect struct', evidence)
        self.assertIn('effects.go:224-', evidence)

    def test_unknown_request_is_an_honest_index(self):
        self.write('effects.go', '// header\nfunc Real() {}\n')
        evidence = requested_context('NEED: backend/game/effects.go: MissingImplementation', self.repo)
        self.assertIn('requested implementation unresolved', evidence)
        self.assertIn('2 func Real()', evidence)
        self.assertNotIn('// header', evidence)

    def test_bare_small_fixture_request_includes_its_assertions(self):
        self.write('fixture_test.go', 'package game\nfunc TestFixture() {\n t.Fatal("required assertion")\n}\n')
        evidence = requested_context('NEED: backend/game/fixture_test.go', self.repo)
        self.assertIn('required assertion', evidence)
        self.assertNotIn('source index', evidence)

    def test_context_reads_are_separate_from_edit_authority_but_source_only(self):
        self.write('types.go', 'type Effect struct { Value int }\n')
        evidence = requested_context('NEED: backend/game/types.go: Effect', self.repo,
                                     {'scope': {'allowed_paths': []}})
        self.assertIn('Value int', evidence)
        (self.repo / 'secret.go').write_text('secret')
        self.assertIsNone(source_path(self.repo, 'backend/game/../../secret.go'))
        self.assertIsNone(source_path(self.repo, '/etc/passwd'))
        self.write('escape.go', '').unlink()
        (self.repo / 'backend/game/escape.go').symlink_to('/etc/passwd')
        self.assertIsNone(source_path(self.repo, 'backend/game/escape.go'))

    def test_scope_reference_requires_authority_or_explicit_context_marker(self):
        self.write('gamestate_cast.go', 'package game\n')
        ticket = {'required_behavior': ['Update gamestate_cast.go to accept the target cap.'],
                  'scope': {'allowed_paths': []}}
        self.assertEqual(preparation_problems(ticket, self.repo)[0]['category'], 'scope_contract')
        ticket['execution'] = {'context_only_paths': ['backend/game/gamestate_cast.go']}
        self.assertEqual(preparation_problems(ticket, self.repo), [])

    def test_module_relative_required_edit_is_not_silently_ignored(self):
        self.write('monarch.go', 'package game\n')
        ticket = {'required_behavior': ['BecomeMonarch (game/monarch.go) must notify returns.'],
                  'scope': {'allowed_paths': []}}
        self.assertEqual(preparation_problems(ticket, self.repo)[0]['path'], 'backend/game/monarch.go')

    def test_existing_required_test_is_detected_before_model(self):
        self.write('old_test.go', 'package game\nfunc TestCollision(t *testing.T) {}\n')
        ticket = {'scope': {'allowed_paths': ['backend/game/new_test.go']},
                  'required_behavior': ['Add a discriminating behavior test named TestCollision.'],
                  'gates': ["cd backend && go test ./game -run '^TestCollision$'"]}
        self.assertEqual(preparation_problems(ticket, self.repo)[0]['category'], 'test_symbol_collision')
        ticket['required_behavior'] = ['Preserve existing behavior.']
        self.assertEqual(preparation_problems(ticket, self.repo), [])

    def test_diagnostics_survive_a_long_go_json_tail(self):
        result = {'stdout': '\n'.join(json.dumps({'Output': line}) for line in
                  ['game/effect.go:18: undefined: Missing'] + ['package summary'] * 1000), 'stderr': ''}
        self.assertIn('game/effect.go:18: undefined: Missing', failure_detail(result))

    def test_same_capability_key_gets_different_test_symbols_for_different_semantics(self):
        producer = load('factory-ng-produce-capability-dependency.py')
        def capability(behavior):
            return {'key': 'filter_dealt_damage_this_turn', 'summary': behavior,
                    'specification': {'required_behavior': behavior}}
        with mock.patch.object(producer, 'source_revision', return_value='abc'), \
             mock.patch.object(producer, 'source_evidence', return_value=[]):
            first = producer.engine_ticket('parent', OPS / 'receipt.json', capability('Source dealt damage.'))
            second = producer.engine_ticket('parent', OPS / 'receipt.json', capability('Source was dealt damage.'))
        self.assertNotEqual(first['id'], second['id'])
        self.assertNotEqual(first['gates'][1], second['gates'][1])
        self.assertEqual(first['capability']['required_behavior'], 'Source dealt damage.')
        self.assertEqual(second['capability']['required_behavior'], 'Source was dealt damage.')


class RunnerTests(unittest.TestCase):
    def run_fixture(self, replies, gates=None, scope_problem=False, go_fixture=False, misnamed_test=False, exact_profile=False, long_file=False, source_busy=False, profile='claude-staged@1.0.0', work_type='engine', capability_result=None):
        runner = load('factory-ng-run-engine-ticket.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            (source / 'backend/game').mkdir(parents=True)
            effect_path = 'scripts/paragraph/effect.py' if work_type == 'map' else 'backend/game/effect.py'
            (source / effect_path).parent.mkdir(parents=True, exist_ok=True)
            (source / effect_path).write_text(('\n' * 500 if long_file else '') + 'value = 0\n')
            if go_fixture:
                (source / 'backend/go.mod').write_text('module fixture\n\ngo 1.20\n')
                (source / 'backend/game/effect.go').write_text('package game\nvar Value = 0\n')
                (source / 'backend/game/effect_test.go').write_text('package game\nimport "testing"\nfunc TestValue(t *testing.T) { if Value != 2 { t.Fatal(Value) } }\n')
                if misnamed_test:
                    path = source / 'backend/game/effect_test.go'
                    path.write_text(path.read_text().replace('TestValue', 'TestWrongName'))
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(source), '-c', 'user.name=Test', '-c',
                            'user.email=test@local', 'commit', '-qm', 'fixture'], check=True)
            revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            if source_busy:
                (source / '.git/index.lock').touch()
            ticket = {'schema': 'factory.ticket-spec/v1', 'id': 'ticket:fixture/v1',
                      'work_type': work_type, 'skill': {}, 'source': {'revision': revision},
                      'scope': {'allowed_paths': [effect_path]},
                      'required_behavior': [], 'gates': gates or [
                          "python3 -c \"import runpy; assert runpy.run_path('%s')['value'] == 2\"" % effect_path,
                          'git diff --check'],
                      'execution': {'compatible_profiles': [profile]}}
            if exact_profile:
                ticket['execution']['profile_policy'] = 'exact'
            if go_fixture:
                ticket['scope']['allowed_paths'] = ['backend/game/effect.go']
                if misnamed_test:
                    ticket['scope']['allowed_paths'].append('backend/game/effect_test.go')
                ticket['gates'] = ["cd backend && go test ./game -run '^TestValue$' -count=1", 'git diff --check']
            if scope_problem:
                ticket['scope']['allowed_paths'] = ['backend/game/other.py']
                ticket['required_behavior'] = ['Update backend/game/effect.py.']
            ticket_path = root / 'ticket.json'
            ticket_path.write_text(json.dumps(ticket))
            original_call = runner.call
            prompts, commands = [], []
            response = iter(replies)
            def call(command, cwd, stdin=None, **kwargs):
                commands.append(command)
                if any(str(c).endswith('model_call.py') for c in command):
                    prompts.append(stdin)
                    answer = next(response)
                    if isinstance(answer, dict):
                        return answer
                    return {'exit_code': 0, 'stdout': answer,
                            'stderr': 'tokens: in=10 out=2 cache_r=3 cache_w=0', 'elapsed_ms': 1}
                if any(str(c).endswith(('engine-pipeline-pack.py', 'map-ticket-spec-pack.py')) for c in command):
                    return {'exit_code': 0, 'stdout': 'fixture packet', 'stderr': '', 'elapsed_ms': 1}
                if any(str(c).endswith('map-pipeline-apply.py') for c in command):
                    command = [sys.executable, str(OPS / 'scripts/map-pipeline-apply.py'), '--allow-game']
                if str(command[0]).endswith('go-cache-run.sh'):
                    command = [str(OPS / 'scripts/go-cache-run.sh'), *command[1:]]
                return original_call(command, cwd, stdin=stdin, **kwargs)
            with mock.patch.multiple(runner, OPS=root, SOURCE=source, RUNS=root / 'runs', CANDIDATES=root / 'candidates'), \
                 mock.patch.object(runner, 'call', side_effect=call), \
                 mock.patch.object(runner, 'validated_capability', return_value=capability_result), \
                 mock.patch.object(sys, 'argv', ['runner', '--ticket', str(ticket_path), '--worker', 'fixture',
                                                '--model', 'fixture', '--profile', profile]), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                runner.main()
            result = json.loads(output.getvalue())
            receipt = json.loads((root / result['receipt']).read_text())
            self.assertEqual(subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True), '')
            return receipt, prompts, commands

    @staticmethod
    def patch(before, after):
        return '<<<FILE backend/game/effect.py\n<<<SEARCH\nvalue = %s\n===REPLACE\nvalue = %s\n>>>END\n' % (before, after)

    def test_goose_staged_preserves_contract_and_has_one_gate_correction(self):
        receipt, prompts, commands = self.run_fixture([self.patch(0, 1), self.patch(1, 2)],
                                                       profile='qwen-goose-staged@1.0.0')
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(len(prompts), 2)
        self.assertTrue(receipt['model']['telemetry']['gate_repair_attempted'])
        self.assertTrue(all(g['outcome'] == 'passed' for g in receipt['gates']))
        self.assertIn('TICKET CONTRACT', prompts[0])
        self.assertIn('TICKET CONTRACT', prompts[1])
        pack = next(c for c in commands if any(str(p).endswith('engine-pipeline-pack.py') for p in c))
        self.assertIn('--no-tools', pack)

    def test_goose_need_then_gate_correction_is_allowed_once(self):
        receipt, prompts, _ = self.run_fixture(['NEED: backend/game/effect.py: 1-1',
            self.patch(0, 1), self.patch(1, 2)], profile='qwen-goose-staged@1.0.0')
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(len(prompts), 3)
        self.assertTrue(receipt['model']['telemetry']['gate_repair_attempted'])
        self.assertIn('ONE COMPILE/TEST REPAIR', prompts[2])

    def test_goose_need_then_parser_correction_is_allowed_once(self):
        receipt, prompts, _ = self.run_fixture(['NEED: backend/game/effect.py: 1-1',
            self.patch(999, 2), self.patch(0, 2)], profile='qwen-goose-staged@1.0.0')
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(len(prompts), 3)
        self.assertIn('SEARCH text not found', prompts[2])
        self.assertIn('value = 0', prompts[2])

    def test_goose_need_and_failed_correction_never_get_fourth_call(self):
        receipt, prompts, _ = self.run_fixture(['NEED: backend/game/effect.py: 1-1',
            self.patch(0, 1), self.patch(1, 3)], profile='qwen-goose-staged@1.0.0')
        self.assertEqual(receipt['outcome'], 'gate_failed')
        self.assertEqual(len(prompts), 3)
        self.assertNotIn('candidate_patch', receipt['execution'])

    def test_goose_staged_failed_correction_does_not_loop(self):
        receipt, prompts, _ = self.run_fixture([self.patch(0, 1), self.patch(1, 3)],
                                               profile='qwen-goose-staged@1.0.0')
        self.assertEqual(len(prompts), 2)
        self.assertEqual(receipt['outcome'], 'gate_failed')
        self.assertNotIn('candidate_patch', receipt['execution'])

    def test_codex_gets_native_source_access_in_the_actual_runner(self):
        receipt, _, commands = self.run_fixture([self.patch(0, 2)], profile='codex-constrained@1.0.0')
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        pack = next(c for c in commands if any(str(p).endswith('engine-pipeline-pack.py') for p in c))
        self.assertNotIn('--no-tools', pack)

    def test_codex_host_profile_gets_its_one_focused_gate_correction(self):
        receipt, prompts, _ = self.run_fixture([self.patch(0, 1), self.patch(1, 2)], profile='codex-constrained@1.1.0')
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(len(prompts), 2)
        self.assertTrue(receipt['model']['telemetry']['gate_repair_attempted'])
        self.assertTrue(all(g['outcome'] == 'passed' for g in receipt['gates']))

    def test_codex_rejected_search_repair_gets_exact_source_and_read_tools(self):
        receipt, prompts, _ = self.run_fixture([self.patch(999, 2), self.patch(0, 2)],
                                               profile='codex-constrained@1.1.0', long_file=True)
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(len(prompts), 2)
        self.assertIn('Read-only source tools remain available', prompts[1])
        self.assertIn('Do not return NEED', prompts[1])
        self.assertTrue(any(a.get('kind') == 'repair_packet' for a in receipt['raw_artifacts']))

    def test_codex_malformed_repair_is_bounded_and_never_accepted(self):
        bad = self.patch(0, 2).replace('===REPLACE', '===INVALID')
        receipt, prompts, _ = self.run_fixture([bad, bad], profile='codex-constrained@1.1.0')
        self.assertEqual(receipt['outcome'], 'infrastructure_failed_model_protocol')
        self.assertEqual(len(prompts), 2)
        self.assertNotIn('candidate_patch', receipt['execution'])

    def test_transport_failure_does_not_spend_a_patch_correction(self):
        receipt, prompts, _ = self.run_fixture([{'exit_code': 1, 'stdout': '',
                                               'stderr': 'openrouter: HTTP 404', 'elapsed_ms': 1}])
        self.assertEqual(receipt['outcome'], 'infrastructure_failed')
        self.assertEqual(len(prompts), 1)
        self.assertTrue(any(g['id'] == 'provider-call' and 'HTTP 404' in g['detail'] for g in receipt['gates']))

    def test_map_correction_keeps_validated_dependency_and_failed_gate_evidence(self):
        patch = self.patch(0, 1).replace('backend/game/effect.py', 'scripts/paragraph/effect.py')
        capability = {'key': 'fixture_gap', 'specification': {'required_behavior': 'missing runtime'}}
        receipt, prompts, _ = self.run_fixture([patch, 'VERDICT: NEEDS_PRIMITIVE\nREASON: missing runtime\n'],
                                               work_type='map', capability_result=capability)
        self.assertEqual(receipt['outcome'], 'blocked_by_capability')
        self.assertEqual(receipt['capability_demand'], capability)
        self.assertEqual(len(prompts), 2)
        self.assertTrue(any(g['outcome'] == 'failed' for g in receipt['gates']))
        self.assertNotIn('candidate_patch', receipt['execution'])

    def test_failed_behavior_gets_one_repair_then_all_gates_rerun(self):
        receipt, prompts, commands = self.run_fixture([self.patch(0, 1), self.patch(1, 2)])
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(len(prompts), 2)
        self.assertIn('value = 1', prompts[1])
        self.assertIn('CURRENT candidate', prompts[1])
        self.assertEqual(receipt['attempt_history'][0]['gates'][-1]['outcome'], 'failed')
        self.assertTrue(all(g['outcome'] == 'passed' for g in receipt['gates']))
        self.assertEqual(receipt['model']['telemetry']['input_tokens'], 20)
        behavior_runs = [c for c in commands if c[:2] == ['bash', '-lc'] and 'runpy' in c[-1]]
        self.assertEqual(len(behavior_runs), 2)

    def test_failed_correction_is_terminal_and_cannot_export(self):
        receipt, prompts, _ = self.run_fixture([self.patch(0, 1), self.patch(1, 3)])
        self.assertEqual(receipt['outcome'], 'gate_failed')
        self.assertEqual(len(prompts), 2)
        self.assertNotIn('candidate_patch', receipt['execution'])
        self.assertIn('successor TicketSpec', receipt['next_action'])
        self.assertNotIn('integrate an accepted candidate', receipt['next_action'])

    def test_repair_sees_modified_lines_far_beyond_the_file_header(self):
        receipt, prompts, _ = self.run_fixture([self.patch(0, 1), self.patch(1, 2)], long_file=True)
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertIn('value = 1', prompts[1])
        self.assertIn('501', prompts[1])

    def test_busy_source_writes_zero_model_wait_receipt(self):
        receipt, prompts, commands = self.run_fixture([], source_busy=True)
        self.assertEqual(receipt['outcome'], 'source_unavailable')
        self.assertFalse(receipt['execution']['model_called'])
        self.assertEqual(receipt['model']['telemetry']['model_calls'], 0)
        self.assertFalse(prompts)
        self.assertFalse(any('clone' in c for c in commands))

    @unittest.skipUnless(GO_TOOLCHAIN, "real Go gate needs a go toolchain on PATH or in /usr/local/go/bin")
    def test_real_go_compile_failure_can_repair_and_pass_named_behavior_test(self):
        def patch(before, after):
            return '<<<FILE backend/game/effect.go\n<<<SEARCH\nvar Value = %s\n===REPLACE\nvar Value = %s\n>>>END\n' % (before, after)
        receipt, prompts, _ = self.run_fixture([patch('0', 'Missing'), patch('Missing', '2')], go_fixture=True)
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertIn('undefined: Missing', prompts[1])
        self.assertIn('var Value = Missing', prompts[1])
        self.assertIn('Named test gate: 1 test(s) passed', receipt['gates'][-2]['detail'])

    @unittest.skipUnless(GO_TOOLCHAIN, "real Go gate needs a go toolchain on PATH or in /usr/local/go/bin")
    def test_misnamed_real_go_test_is_rejected_then_repaired_before_acceptance(self):
        first = '<<<FILE backend/game/effect.go\n<<<SEARCH\nvar Value = 0\n===REPLACE\nvar Value = 2\n>>>END\n'
        repair = ('<<<FILE backend/game/effect_test.go\n<<<SEARCH\n'
                  'func TestWrongName(t *testing.T) { if Value != 2 { t.Fatal(Value) } }\n'
                  '===REPLACE\nfunc TestValue(t *testing.T) { if Value != 2 { t.Fatal(Value) } }\n>>>END\n')
        receipt, prompts, commands = self.run_fixture([first, repair], go_fixture=True, misnamed_test=True)
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(len(prompts), 2)
        self.assertIn('executed no passing tests', prompts[1])
        self.assertIn('TestWrongName', prompts[1])
        self.assertIn('Named test gate: 1 test(s) passed', receipt['gates'][-2]['detail'])
        self.assertEqual(receipt['attempt_history'][0]['gates'][-1]['outcome'], 'failed')

    def test_need_does_not_consume_the_claude_patch_repair(self):
        receipt, prompts, _ = self.run_fixture(['NEED: backend/game/effect.py: 1-1', self.patch(0, 1), self.patch(1, 2)])
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(receipt['model']['telemetry']['model_calls'], 3)
        self.assertEqual(len(prompts), 3)

    def test_protocol_repair_consumes_the_single_repair_allowance(self):
        receipt, prompts, _ = self.run_fixture(['<<<FILE backend/game/effect.py\nbroken', self.patch(0, 1)])
        self.assertEqual(receipt['outcome'], 'gate_failed')
        self.assertEqual(len(prompts), 2)
        self.assertNotIn('gate_repair_attempted', receipt['model']['telemetry'])

    def test_scope_contract_failure_spends_no_model_calls(self):
        receipt, prompts, _ = self.run_fixture([], scope_problem=True)
        self.assertEqual(receipt['outcome'], 'preparation_failed')
        self.assertEqual(receipt['failure_category'], 'preparation_contract')
        self.assertEqual(receipt['model']['telemetry']['model_calls'], 0)
        self.assertEqual(prompts, [])

    def test_partial_counters_are_not_reported_as_complete_totals(self):
        runner = load('factory-ng-run-engine-ticket.py')
        total = runner.counters('tokens: in=10 out=2 cache_r=3 cache_w=0', 5)
        runner.merge_telemetry(total, runner.counters('', 7))
        self.assertEqual(total['input_tokens']['availability'], 'unavailable')
        self.assertEqual(total['elapsed_ms'], 12)

    GAP = 'EVIDENCE_GAP: {"question":"Which file defines the effect value?","searched":["effect value in prepared packet"]}'
    EVIDENCE = 'EVIDENCE_JSON: {"sources":[{"path":"backend/game/effect.py","start_line":1,"end_line":1}],"summary":"ignore this unverified prose"}'

    def test_evidence_failure_uses_read_only_agentic_then_returns_to_staged(self):
        receipt, prompts, commands = self.run_fixture([self.GAP, self.EVIDENCE, self.patch(0, 2)])
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        engines = [c[c.index('--engine') + 1] for c in commands if any(str(s).endswith('model_call.py') for s in c)]
        self.assertEqual(engines, ['claude', 'claude-agentic', 'claude'])
        self.assertIn('value = 0', prompts[2])
        self.assertNotIn('ignore this unverified prose', prompts[2])
        self.assertEqual(receipt['model']['telemetry']['input_tokens'], 30)
        self.assertEqual(receipt['investigation']['telemetry']['input_tokens'], 10)
        self.assertEqual(receipt['investigation']['status'], 'evidence_supplied')
        self.assertEqual(receipt['attempt_history'][0]['stage'], 'staged_evidence_failure')

    def test_agentic_patch_is_never_applied(self):
        receipt, prompts, _ = self.run_fixture([self.GAP, self.patch(0, 2)])
        self.assertEqual(receipt['outcome'], 'parked')
        self.assertEqual(len(prompts), 2)
        self.assertNotIn('candidate_patch', receipt['execution'])
        self.assertEqual(receipt['investigation']['status'], 'unresolved')

    def test_failed_evidence_lookup_does_not_loop(self):
        receipt, prompts, _ = self.run_fixture([self.GAP, self.EVIDENCE, self.GAP])
        self.assertEqual(receipt['outcome'], 'parked')
        self.assertEqual(len(prompts), 3)
        self.assertEqual(receipt['investigation']['status'], 'staged_still_missing_evidence')

    def test_exact_profile_trial_cannot_silently_use_agentic(self):
        receipt, prompts, _ = self.run_fixture([self.GAP], exact_profile=True)
        self.assertEqual(receipt['failure_category'], 'missing_source_context')
        self.assertIn('evidence_failure', receipt)
        self.assertEqual(receipt['outcome'], 'parked')
        self.assertEqual(len(prompts), 1)
        self.assertNotIn('investigation', receipt)

    def test_provider_failure_is_not_an_evidence_escalation(self):
        receipt, prompts, _ = self.run_fixture([{'exit_code': 1, 'stdout': self.GAP, 'stderr': 'provider failed', 'elapsed_ms': 1}])
        self.assertEqual(receipt['outcome'], 'infrastructure_failed')
        self.assertEqual(len(prompts), 1)
        self.assertNotIn('investigation', receipt)

    def test_five_searched_regions_are_evidence_failure_without_coding_retry(self):
        gap = 'EVIDENCE_GAP: ' + json.dumps({'question': 'Where is the upstream parser?',
                                            'searched': ['source region %d' % i for i in range(5)]})
        receipt, prompts, _ = self.run_fixture([gap], exact_profile=True)
        self.assertEqual(receipt['failure_category'], 'missing_source_context')
        self.assertEqual(len(prompts), 1)
        self.assertEqual(len(receipt['evidence_failure']['searched']), 5)
        self.assertNotIn('bounded_repair_attempted', receipt['model']['telemetry'])

    def test_investigation_does_not_consume_or_reset_the_one_coding_repair(self):
        receipt, prompts, _ = self.run_fixture([self.GAP, self.EVIDENCE, self.patch(0, 1), self.patch(1, 3)])
        self.assertEqual(receipt['outcome'], 'gate_failed')
        self.assertEqual(len(prompts), 4)
        self.assertTrue(receipt['model']['telemetry']['bounded_repair_attempted'])

    def test_existing_need_is_resolved_before_agentic_is_considered(self):
        receipt, prompts, commands = self.run_fixture(['NEED: backend/game/effect.py: 1-1', self.GAP, self.EVIDENCE, self.patch(0, 2)])
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertTrue(receipt['model']['telemetry']['need_continuation_attempted'])
        engines = [c[c.index('--engine') + 1] for c in commands if any(str(s).endswith('model_call.py') for s in c)]
        self.assertEqual(engines, ['claude', 'claude', 'claude-agentic', 'claude'])


if __name__ == '__main__':
    unittest.main()
