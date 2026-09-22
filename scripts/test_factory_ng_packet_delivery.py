"""Packet and transport regressions from the September 9 receipt audit."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest import mock

OPS = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, OPS / 'scripts' / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PacketDeliveryTests(unittest.TestCase):
    def test_host_access_is_opt_in_and_keeps_remote_surfaces_disabled(self):
        adapter = load('model_call.py')
        default = adapter.codex_exec_command('model', 60)
        enabled = adapter.codex_exec_command('model', 60, host_access=True)
        self.assertIn('read-only', default)
        self.assertIn('danger-full-access', enabled)
        self.assertIn('web_search="disabled"', enabled)
        self.assertIn('multi_agent', enabled)

    def test_direct_checkout_edits_reject_answer_and_retain_spending(self):
        adapter = load('model_call.py')
        response = json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 17, 'output_tokens': 3}}).encode()
        with mock.patch.dict(os.environ, {'PIPE_FACTORY_CODEX_HOST_ACCESS': '1'}), \
             mock.patch.object(adapter, 'checkout_fingerprint', side_effect=['before', 'changed']), \
             mock.patch.object(adapter.sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(b'fixture'))), \
             mock.patch.object(adapter.subprocess, 'run', return_value=types.SimpleNamespace(stdout=response)), \
             mock.patch.object(adapter, 'save_raw') as saved, \
             contextlib.redirect_stderr(io.StringIO()) as stderr, \
             self.assertRaises(SystemExit):
            adapter.call_codex('model', 'engine')
        saved.assert_called_once()
        self.assertIn('tokens: in=17 out=3', stderr.getvalue())
        self.assertIn('rejected direct checkout mutation', stderr.getvalue())

    def test_failed_codex_process_is_not_an_empty_success_or_zero_cost(self):
        adapter = load('model_call.py')
        with mock.patch.dict(os.environ, {'PIPE_FACTORY_CODEX_HOST_ACCESS': '0'}), \
             mock.patch.object(adapter.sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(b'fixture'))), \
             mock.patch.object(adapter.subprocess, 'run', return_value=types.SimpleNamespace(stdout=b'', returncode=2)), \
             mock.patch.object(adapter, 'save_raw'), \
             contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
            adapter.call_codex('model', 'engine')
        self.assertNotIn('tokens:', stderr.getvalue())
        self.assertIn('process exited 2', stderr.getvalue())

    def packet(self, work_type, *flags):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'backend/cards/fixture_test.go'
            path.parent.mkdir(parents=True)
            path.write_text('package cards\n// PINNED_FIXTURE_MUST_REACH_WORKER\n')
            ticket = {'schema': 'factory.ticket-spec/v1', 'id': 'ticket:engine.fixture/v1',
                      'title': 'fixture', 'work_type': work_type, 'required_behavior': ['Prove the real card.'],
                      'scope': {'allowed_paths': ['backend/cards/new_test.go']},
                      'evidence': [{'path': 'backend/cards/fixture_test.go', 'anchor': '1-2'}],
                      'execution': {'parser_probes': [{'function': 'parse_static_condition', 'text': 'fixture'}]}}
            ticket_path = root / 'ticket.json'
            ticket_path.write_text(json.dumps(ticket))
            script = 'engine-pipeline-pack.py' if work_type == 'engine' else 'map-ticket-spec-pack.py'
            cwd, paths = os.getcwd(), list(sys.path)
            try:
                with mock.patch.object(sys, 'argv', [script, '--ticket-spec', str(ticket_path), '--repo', str(root), *flags]), \
                     mock.patch.dict(sys.modules, {'reparse': types.SimpleNamespace(parse_static_condition=lambda text: None)}), \
                     mock.patch('factory_ng_knowledge.discover_capability', return_value={'lookups': [], 'candidates': []}), \
                     contextlib.redirect_stdout(io.StringIO()) as output:
                    runpy.run_path(str(OPS / 'scripts' / script), run_name='__main__')
                return output.getvalue()
            finally:
                os.chdir(cwd)
                sys.path[:] = paths

    def test_engine_pinned_fixture_survives_without_search_hits(self):
        packet = self.packet('engine', '--no-tools')
        self.assertIn('PINNED_FIXTURE_MUST_REACH_WORKER', packet)
        self.assertIn('No repository tools are available', packet)

    def test_native_readonly_packets_allow_source_reads_and_keep_harness_authority(self):
        for packet in (self.packet('engine'), self.packet('map', '--read-only-tools')):
            self.assertIn('Local read-only source tools are available', packet)
            self.assertNotIn('No repository tools are available', packet)
            self.assertIn('Do not edit files, run', packet)
            self.assertIn('harness owns those actions', packet)

    def test_direct_map_retains_no_tools_contract(self):
        self.assertIn('No repository tools are available', self.packet('map'))

    def test_http_error_is_retained_and_cannot_become_empty_success(self):
        adapter = load('model_call.py')
        error = adapter.urllib.error.HTTPError('https://example.invalid', 404, 'Gone', {},
                                               io.BytesIO(b'{"error":{"code":404,"message":"model unavailable"}}'))
        with mock.patch.dict(os.environ, {'OPENROUTER_API_KEY': 'fixture'}), \
             mock.patch.object(adapter.openrouter_cooldown, 'status', return_value={'allowed': True}), \
             mock.patch.object(adapter.sys, 'stdin', io.StringIO('fixture')), \
             mock.patch.object(adapter.urllib.request, 'urlopen', side_effect=error), \
             mock.patch.object(adapter, 'save_raw') as saved, \
             self.assertRaises(SystemExit) as raised:
            adapter.call_openrouter('unavailable', 'map')
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(saved.call_args.args[0]['provider_error']['http_status'], 404)


if __name__ == '__main__':
    unittest.main()
