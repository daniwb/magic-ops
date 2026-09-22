import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import goose_staged as goose


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GooseStagedTests(unittest.TestCase):
    def events(self):
        return '\n'.join(json.dumps(event) for event in [
            {'type': 'message', 'message': {'role': 'user', 'content': [{'type': 'text', 'text': 'ignore'}]}},
            {'type': 'message', 'message': {'role': 'assistant', 'content': [{'type': 'thinking', 'text': 'ignore'}, {'type': 'text', 'text': 'first'}]}},
            {'type': 'message', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': ' second'}]}},
            {'type': 'complete', 'input_tokens': 20, 'output_tokens': 10}])

    def test_stream_chunks_and_usage(self):
        text, usage = goose.decode_events(self.events())
        self.assertEqual(text, 'first second')
        self.assertEqual(usage['output_tokens'], 10)

    def test_rejects_partial_and_budget_exhaustion(self):
        for raw in (self.events().rsplit('\n', 1)[0], self.events().replace('"output_tokens": 10', '"output_tokens": 32000')):
            with self.assertRaises(ValueError):
                goose.decode_events(raw)

    def test_complete_response_can_exceed_the_old_ceiling(self):
        text, usage = goose.decode_events(self.events().replace('"output_tokens": 10', '"output_tokens": 24000'))
        self.assertEqual(text, 'first second')
        self.assertEqual(usage['output_tokens'], 24000)

    def test_complete_packet_and_isolated_no_tools_settings(self):
        packet = 'source\n## Relevant code regions\ncontract\nrepair feedback\n'
        def fake_run(command, **kw):
            self.assertEqual(Path(command[command.index('--instructions') + 1]).read_text(), packet)
            env = kw['env']
            self.assertEqual(env['GOOSE_MAX_TOKENS'], '32000')
            self.assertNotIn('GOOSE_RECIPE', env)
            self.assertEqual(env['CONTEXT_FILE_NAMES'], '[]')
            self.assertIn('--no-profile', command)
            self.assertNotIn('--with-builtin', command)
            self.assertEqual(command[command.index('--max-turns') + 1], '1')
            provider = json.loads((Path(env['GOOSE_PATH_ROOT']) / 'config/custom_providers/strix_halo.json').read_text())
            self.assertEqual(provider['engine'], 'openai')
            self.assertNotEqual(provider['models'][0].get('request_params', {}).get('enable_thinking'), False)
            return SimpleNamespace(stdout=self.events(), stderr='', returncode=0)
        with patch.dict('os.environ', {'GOOSE_RECIPE': 'untrusted', 'GOOSE_MAX_TOKENS': '8192'}), patch.object(goose.subprocess, 'run', side_effect=fake_run):
            result = goose.run(packet, 'halogen-qwen3.8-flash-next')
        self.assertEqual(goose.decode_events(result['events'])[0], 'first second')

    def test_retired_profile_can_finish_saved_work_but_cannot_start_new_work(self):
        controller = load('factory-ng-controller')
        old = 'qwen-prepared-local@1.0.1'
        workers = controller.configured_workers_by_profile([{'id': 'qwen-local', 'enabled': True,
            'profile': 'qwen-goose-staged@1.0.0', 'alternate_profiles': [old], 'draining_profiles': [old]}])
        worker = workers[old][0]
        self.assertFalse(controller.worker_supports_job(worker, {'work_type': 'engine', 'state': 'queued'}))
        self.assertTrue(controller.worker_supports_job(worker, {'work_type': 'engine', 'state': 'awaiting_verification'}))
        self.assertTrue(controller.worker_supports_job(workers['qwen-goose-staged@1.0.0'][0],
                                                     {'work_type': 'engine', 'state': 'queued'}))

    def test_routing_respects_exact_contracts_and_retry_limits(self):
        controller = load('factory-ng-controller')
        runner = load('factory-ng-run-engine-ticket')
        profile = 'qwen-goose-staged@1.0.0'
        for kind in ('map', 'engine'):
            ticket = {'work_type': kind, 'execution': {'compatible_profiles': ['claude-staged@1.0.0']}}
            self.assertIn(profile, controller.compatible_profiles_for(ticket, 'claude-staged@1.0.0'))
            self.assertTrue(runner.supports_profile(ticket, profile))
            self.assertTrue(controller.worker_supports({'profile': profile}, kind))
            ticket['execution']['profile_policy'] = 'exact'
            self.assertNotIn(profile, controller.compatible_profiles_for(ticket, 'claude-staged@1.0.0'))
            self.assertFalse(runner.supports_profile(ticket, profile))
        self.assertEqual(controller.max_attempts_for({'dispatch_profile': profile}, {'infrastructure_attempts': 3}), 1)
        self.assertTrue(runner.repair_available(profile, {'need_continuation_attempted': True}))
        self.assertFalse(runner.repair_available(profile, {'need_continuation_attempted': True, 'bounded_repair_attempted': True}))


if __name__ == '__main__':
    unittest.main()
