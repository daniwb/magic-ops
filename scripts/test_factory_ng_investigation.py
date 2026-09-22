#!/usr/bin/env python3
"""No paid calls: test evidence escalation, reference safety and adapter limits."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from factory_ng_investigation import evidence_gap, validate_evidence, STAGED

OPS = Path(__file__).resolve().parents[1]


def load(filename):
    spec = importlib.util.spec_from_file_location(filename, OPS / 'scripts' / filename)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


class InvestigationTests(unittest.TestCase):
    def test_only_explicit_staged_evidence_failures_qualify(self):
        gap = 'EVIDENCE_GAP: {"question":"Where is target selection?","searched":["prepared target code"]}'
        self.assertIsNotNone(evidence_gap({'exit_code': 0, 'stdout': gap}, STAGED))
        for reply in ['VERDICT: AMBIGUOUS\nREASON: unclear request', 'undefined: Target',
                      'FAIL TestTarget', 'candidate_conflict', 'NEEDS_PRIMITIVE',
                      'VERDICT: FRAMEWORK\n' + gap, 'VERDICT: NEEDS_PRIMITIVE\n' + gap,
                      '<<<NEWFILE backend/game/a.go\n' + gap]:
            self.assertIsNone(evidence_gap({'exit_code': 0, 'stdout': reply}, STAGED))
        self.assertIsNone(evidence_gap({'exit_code': 0, 'stdout': gap}, 'claude-agentic@1.0.0'))
        self.assertIsNone(evidence_gap({'exit_code': 0, 'stdout': gap}, STAGED, attempted=True))

    def test_reference_validation_rejects_escape_and_invented_ranges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'backend/game').mkdir(parents=True)
            (root / 'backend/game/a.go').write_text('package game\nfunc Real() {}\n')
            (root / 'backend/game/escape.go').symlink_to('/etc/passwd')
            for path, end in [('backend/game/../../secret.go', 1), ('/etc/passwd', 1),
                              ('backend/game/escape.go', 1), ('backend/game/a.go', 5)]:
                reply = 'EVIDENCE_JSON: ' + json.dumps({'sources': [{'path': path, 'start_line': 1, 'end_line': end}]})
                with self.assertRaises(ValueError): validate_evidence(reply, root)
            reply = 'EVIDENCE_JSON: ' + json.dumps({'sources': [{'path': 'backend/game/a.go', 'start_line': 1, 'end_line': 2}]})
            evidence, anchors = validate_evidence(reply, root)
            self.assertIn('func Real()', evidence)
            self.assertTrue(anchors[0]['sha256'].startswith('sha256:'))

    def test_agentic_adapter_has_investigation_only_system_and_hard_turn_limit(self):
        adapter = load('model_call.py')
        reply = {'result': 'EVIDENCE_UNRESOLVED', 'modelUsage': {}}
        with mock.patch.dict(os.environ, {'PIPE_FACTORY_INVESTIGATION': '1', 'PIPE_AGENTIC_MAX_TURNS': '999', 'PIPE_AGENTIC_TIMEOUT': '9999'}), \
             mock.patch.object(adapter.sys, 'stdin', io.StringIO('one evidence question')), \
             mock.patch.object(adapter.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(reply))) as run, \
             mock.patch.object(adapter, 'save_raw'), contextlib.redirect_stderr(io.StringIO()):
            adapter.call_claude_agentic('fixture', 'engine')
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--max-turns') + 1], '12')
        self.assertEqual(command[3], '300')
        self.assertIn('Bash', command[command.index('--disallowedTools'):])
        self.assertIn('EVIDENCE_JSON', command[-1])
        self.assertNotIn('harness applies your edit blocks', command[-1])

    def test_legacy_agentic_ticket_routes_to_staged_and_cannot_run_directly(self):
        controller, runner = load('factory-ng-controller.py'), load('factory-ng-run-engine-ticket.py')
        ticket = {'work_type': 'map', 'execution': {'selected_profile': 'claude-agentic@1.0.0',
                  'compatible_profiles': ['claude-agentic@1.0.0']}}
        profiles = controller.compatible_profiles_for(ticket, 'claude-agentic@1.0.0')
        self.assertIn(STAGED, profiles)
        self.assertNotIn('claude-agentic@1.0.0', profiles)
        self.assertNotIn('claude-agentic-test@1.0.0', profiles)
        self.assertTrue(runner.supports_profile(ticket, STAGED))
        self.assertFalse(runner.supports_profile(ticket, 'claude-agentic@1.0.0'))
        ticket['execution']['profile_policy'] = 'exact'
        self.assertNotIn(STAGED, controller.compatible_profiles_for(ticket, STAGED))
        self.assertFalse(runner.supports_profile(ticket, STAGED))


if __name__ == '__main__':
    unittest.main()
