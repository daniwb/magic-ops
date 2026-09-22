import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import subprocess
import sys
import tempfile
from unittest.mock import patch

import goose_openrouter_staged as adapter
from test_goose_staged import load


class OpenRouterGooseTests(unittest.TestCase):
    def events(self, text='ok', tokens=10):
        return '\n'.join(json.dumps(e) for e in [
            {'type': 'message', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]}},
            {'type': 'complete', 'input_tokens': 10, 'output_tokens': tokens}])

    def test_provider_errors_are_not_proposals(self):
        for text, code in [('Network error: connection failed', 1), ('429 rate limit', 76), ('401 unauthorized', 75)]:
            self.assertEqual(adapter.classify(dict(events=self.events(text, 0), stderr='', exit_code=0)), code)
        self.assertEqual(adapter.classify(dict(events=self.events('source mentions 429'), stderr='', exit_code=0)), 0)
        self.assertEqual(adapter.classify(dict(events=self.events(tokens=32000), stderr='', exit_code=0)), 1)

    def test_no_tools_full_packet_and_secret_redaction(self):
        def invoke(command, **kw):
            self.assertTrue(Path(command[command.index('--instructions') + 1]).read_text().startswith('complete packet\n'))
            self.assertIn('There are NO tools', command[command.index('--system') + 1])
            self.assertIn('--no-profile', command)
            self.assertEqual(kw['env']['GOOSE_MODEL'], 'openrouter/free')
            self.assertNotIn('GOOSE_RECIPE', kw['env'])
            config = Path(kw['env']['GOOSE_PATH_ROOT']) / 'config/config.yaml'
            self.assertIn('extensions: {}', config.read_text())
            return SimpleNamespace(stdout=self.events(), stderr='test-secret', returncode=0)
        with patch.object(adapter, 'credential', return_value='test-secret'), patch.object(adapter.openrouter_cooldown, 'status', return_value={'allowed': True}), patch.object(adapter.openrouter_cooldown, 'record_success') as success, patch.object(adapter.subprocess, 'run', side_effect=invoke), patch.dict('os.environ', {'GOOSE_RECIPE': 'untrusted'}):
            result = adapter.run('complete packet', 'openrouter/free')
        self.assertEqual(result['exit_code'], 0)
        self.assertNotIn('test-secret', json.dumps(result))
        success.assert_called_once()

    def test_cooldown_skips_provider(self):
        with patch.object(adapter.openrouter_cooldown, 'status', return_value={'allowed': False}), patch.object(adapter.subprocess, 'run') as run:
            self.assertEqual(adapter.run('packet', 'openrouter/free')['exit_code'], 76)
            run.assert_not_called()

    def test_routing_exact_contracts_and_expiry(self):
        controller, runner = load('factory-ng-controller'), load('factory-ng-run-engine-ticket')
        profile = 'openrouter-goose-staged@1.0.0'
        worker = {'id': 'fixture-goose', 'enabled': True, 'profile': profile, 'trial_ends_at_epoch': 100}
        for kind in ('map', 'engine'):
            ticket = {'work_type': kind, 'execution': {'compatible_profiles': ['claude-staged@1.0.0']}}
            self.assertIn(profile, controller.compatible_profiles_for(ticket, 'claude-staged@1.0.0'))
            self.assertTrue(runner.supports_profile(ticket, profile))
            ticket['execution']['profile_policy'] = 'exact'
            self.assertNotIn(profile, controller.compatible_profiles_for(ticket, 'claude-staged@1.0.0'))
            self.assertFalse(runner.supports_profile(ticket, profile))
        with patch.object(controller.time, 'time', return_value=99):
            self.assertIn(profile, controller.configured_workers_by_profile([worker]))
        with patch.object(controller.time, 'time', return_value=100):
            self.assertEqual(controller.configured_workers_by_profile([worker]), {})
            self.assertFalse(controller.usage_gate(worker)[0])
            self.assertFalse(controller.worker_supports_job(worker, {'work_type': 'engine'}))
        self.assertTrue(runner.repair_available(profile, {'need_continuation_attempted': True}))
        self.assertFalse(runner.repair_available(profile, {'bounded_repair_attempted': True}))

    def test_reasoning_numbers_do_not_trigger_provider_cooldown(self):
        events = [
            {'type': 'message', 'message': {'content': [{'type': 'thinking', 'thinking': 'source line 429, HTTP 401'}]}},
            {'type': 'complete', 'output_tokens': 32000}]
        artifact = dict(events='\n'.join(map(json.dumps, events)), stderr='', exit_code=0)
        self.assertEqual(adapter.classify(artifact), 1)
        self.assertEqual(artifact['failure_reason'], 'completion_budget_exhausted')
        events[-1]['output_tokens'] = 934
        artifact = dict(events='\n'.join(map(json.dumps, events)), stderr='', exit_code=0)
        self.assertEqual(adapter.classify(artifact), 1)

    def test_reported_truncation_is_rejected_below_token_ceiling(self):
        event = {'type': 'message', 'message': {'role': 'assistant',
                 'metadata': {'outputTokenLimitReached': True},
                 'content': [{'type': 'text', 'text': 'partial patch'}]}}
        raw = json.dumps(event) + '\n' + json.dumps({'type': 'complete', 'output_tokens': 99})
        self.assertEqual(adapter.classify(dict(events=raw, stderr='', exit_code=0)), 1)

    def test_phase_contract_closes_discovery(self):
        self.assertIn('up to three lines', adapter.response_contract('initial'))
        for phase in ('continuation', 'correction'):
            self.assertIn('Do not emit NEED', adapter.response_contract(phase))
            self.assertNotIn('up to three lines', adapter.response_contract(phase))

    def test_delimiter_translation_still_requires_exact_unique_source(self):
        applier = Path(__file__).with_name('map-pipeline-apply.py').resolve()
        for before, code in [('value = 0\n', 0), ('value=0\n', 6), ('value = 0\nvalue = 0\n', 6)]:
            raw = '<<<FILE example.py\n<<<<<<< SEARCH\nvalue = 0\n=======\nvalue = 42\n>>>END\n'
            normalized, changes = adapter.normalize_patch_markers(raw)
            self.assertEqual(len(changes), 2)
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / 'example.py'
                path.write_text(before)
                applied = subprocess.run([sys.executable, str(applier)], cwd=d, input=normalized,
                                         text=True, capture_output=True)
                self.assertEqual(applied.returncode, code, applied.stdout)
                self.assertEqual(path.read_text(), 'value = 42\n' if code == 0 else before)

    def test_normalization_leaves_ambiguous_incomplete_and_newfile_blocks_untouched(self):
        malformed = '<<<FILE example.py\n<<<SEARCH\nold\n>>>REPLACE\nnew\n'
        ambiguous = malformed + '=======\nother\n>>>END\n'
        newfile = '<<<NEWFILE example.py\n' + malformed + '>>>END\n'
        for text in (malformed, ambiguous, newfile):
            self.assertEqual(adapter.normalize_patch_markers(text), (text, []))
        raw = malformed + '>>>END\n'
        normalized, changes = adapter.normalize_patch_markers(raw)
        self.assertEqual(normalized, raw.replace('>>>REPLACE\n', '===REPLACE\n'))
        self.assertEqual(len(changes), 1)

    def test_new_profile_need_then_correction_passes_original_gate(self):
        from test_factory_ng_staged import RunnerTests
        fixture = RunnerTests()
        receipt, prompts, commands = fixture.run_fixture([
            'NEED: backend/game/effect.py: 1-1', fixture.patch(0, 1), fixture.patch(1, 2)],
            profile='openrouter-goose-staged@1.0.0')
        self.assertEqual(receipt['outcome'], 'accepted_for_dependent_observation')
        self.assertEqual(len(prompts), 3)
        self.assertTrue(all(g['outcome'] == 'passed' for g in receipt['gates']))
        calls = [c for c in commands if any(str(p).endswith('model_call.py') for p in c)]
        self.assertTrue(all('goose-openrouter-staged' in c for c in calls))


if __name__ == '__main__':
    unittest.main()
