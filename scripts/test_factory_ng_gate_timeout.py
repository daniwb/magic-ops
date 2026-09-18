"""Lower CPU capacity must not retain the old twelve-minute Go build deadline."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class GateTimeoutTest(unittest.TestCase):
    def test_relocated_gate_tools_preserve_original_contract(self):
        command = 'python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo .'
        for name, function, call in [('factory-ng-run-engine-ticket', 'ticket_gate', 'call'),
                                     ('factory-ng-run-map-ticket', 'run_ticket_gate', 'run')]:
            m = load(name)
            ticket = {'gates': [command]}
            with patch.object(m, call, return_value={
                    'exit_code': 0, 'stdout': '', 'stderr': '', 'elapsed_ms': 0}) as run:
                getattr(m, function)(command, Path('/unused'), ticket)
                self.assertIn(str(m.OPS / 'scripts/factory-ng-targeted-demand.py'), run.call_args.args[0][-1])
                self.assertEqual(ticket['gates'], [command])

    def test_both_runners_allow_thirty_minutes_for_go_but_keep_other_deadlines(self):
        for name, function, call in [('factory-ng-run-engine-ticket', 'ticket_gate', 'call'),
                                     ('factory-ng-run-map-ticket', 'run_ticket_gate', 'run')]:
            m=load(name)
            for command, budget in [('cd backend && go test ./game ./cards -count=1', 1800),
                                    ('python3 -m unittest example', 720)]:
                with self.subTest(runner=name, command=command), patch.object(m,call,return_value={
                        'exit_code':0,'stdout':'','stderr':'','elapsed_ms':0}) as run:
                    getattr(m,function)(command,Path('/unused'),{})
                    self.assertEqual(run.call_args.kwargs['timeout'],budget)

    def test_timeout_evidence_names_the_deadline(self):
        for name, call in [('factory-ng-run-engine-ticket','call'),('factory-ng-run-map-ticket','run')]:
            m=load(name)
            with patch.object(m.subprocess,'run',side_effect=subprocess.TimeoutExpired(['x'],1800,output=b'partial')):
                result=getattr(m,call)(['x'],Path('/unused'),timeout=1800)
            self.assertEqual(result['exit_code'],124)
            self.assertEqual(result['stdout'],'partial')
            self.assertIn('1800 seconds',result['stderr'])

if __name__=='__main__':unittest.main()
