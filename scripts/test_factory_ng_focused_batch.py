"""Real Git compositions, retained contracts, switch pauses and controller fanout."""
import contextlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

import factory_ng_verification as proposals

SCRIPTS = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


class FocusedBatchTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.source = self.root / 'source'; self.source.mkdir()
        self.m = load('factory-ng-verify-batch'); self.runner = load('factory-ng-run-engine-ticket')
        self.stack.enter_context(patch.object(self.m, 'OPS', self.root))
        self.stack.enter_context(patch.object(self.m, 'SOURCE', self.source))
        self.stack.enter_context(patch.object(self.runner, 'preparation_problems', return_value=[]))
        self.policy = self.root / 'policy.json'; self.policy.write_text('{"compilation":{"enabled":true}}')
        self.stack.enter_context(patch.object(proposals, 'POLICY', self.policy))
        self.git('init', '-q')
        (self.source / 'a.txt').write_text('old\n'); (self.source / 'b.txt').write_text('old\n')
        (self.source / '.gitignore').write_text('__pycache__/\n')
        (self.source / 'shared_test.py').write_text('import unittest\nclass Shared(unittest.TestCase):\n    def test_shared(self): self.assertEqual(1, 1)\n')
        self.git('add', '.'); self.commit()
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.entries = []

    def git(self, *args):
        return self.m.git(self.source, *args)

    def commit(self):
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@local', 'commit', '-qm', 'test')

    def proposal(self, name, filename, content, gates=None):
        ticket = self.root / (name + '.json')
        ticket.write_text(json.dumps({'schema': 'factory.ticket-spec/v1', 'id': name, 'work_type': 'map',
            'source': {'revision': self.base}, 'scope': {'allowed_paths': [filename]},
            'gates': gates or ["python3 -c \"from pathlib import Path; assert Path('%s').read_text() == %r\"" % (filename, content),
                               'git status --porcelain paths only allowed', 'git diff --check']}))
        identity = {'worker': 'w', 'profile': 'p', 'model': 'model'}
        (self.source / filename).write_text(content)
        saved = proposals.save_proposal(self.root / 'saved', self.source, ticket, identity, {})
        self.git('reset', '--hard', self.base)
        entry = {'ticket_id': name, 'ticket_path': ticket.name, 'proposal': str(saved.relative_to(self.root)), 'identity': identity}
        self.entries.append(entry)
        return entry

    def verify(self):
        return self.m.verify(self.entries, self.runner)['ticket_results']

    def test_all_contracts_run_on_same_tree_and_keep_individual_patches(self):
        self.proposal('a', 'a.txt', 'new-a\n'); self.proposal('b', 'b.txt', 'new-b\n')
        original = self.runner.ticket_gate
        seen = []
        def gate(command, clone, ticket):
            seen.append((str(clone), (clone / 'a.txt').read_text(), (clone / 'b.txt').read_text()))
            return original(command, clone, ticket)
        with patch.object(self.runner, 'ticket_gate', side_effect=gate): result = self.verify()
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(set(seen)), 1)
        self.assertEqual(seen[0][1:], ('new-a\n', 'new-b\n'))
        receipts = [json.loads((self.root / result[x]['receipt']).read_text()) for x in ('a', 'b')]
        self.assertEqual(receipts[0]['execution']['verified_tree'], receipts[1]['execution']['verified_tree'])
        for receipt, filename in zip(receipts, ('a.txt', 'b.txt')):
            text = (self.root / receipt['execution']['candidate_patch']).read_text()
            self.assertIn('diff --git a/' + filename, text)
            self.assertNotIn('diff --git a/' + ('b.txt' if filename == 'a.txt' else 'a.txt'), text)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), self.base)

    def test_conflict_or_failed_gate_preserves_both_for_individual_repair(self):
        for conflict in (True, False):
            with self.subTest(conflict=conflict):
                self.entries = []
                self.proposal('a', 'a.txt', 'new-a\n')
                self.proposal('b', 'a.txt' if conflict else 'b.txt', 'new-b\n', ['python3 -c "raise SystemExit(1)"'])
                result = self.verify()
                self.assertTrue(all(x['status'] == 'verification_pending' and x['verification_isolate'] for x in result.values()), result)
                self.assertFalse(list(self.root.glob('docs/factory-ng/runs/*.json')))
                self.assertTrue(all((self.root / x['proposal']).exists() for x in result.values()))

    def test_switch_off_before_or_during_batch_publishes_no_acceptance(self):
        self.proposal('a', 'a.txt', 'new\n')
        self.policy.write_text('{"compilation":{"enabled":false}}')
        self.assertFalse(self.verify()['a']['verification_isolate'])
        self.policy.write_text('{"compilation":{"enabled":true}}')
        original = self.runner.ticket_gate
        def gate(*args):
            result = original(*args)
            self.policy.write_text('{"compilation":{"enabled":false}}')
            return result
        with patch.object(self.runner, 'ticket_gate', side_effect=gate):
            result = self.verify()
        self.assertFalse(result['a']['verification_isolate'])
        self.assertFalse(list(self.root.glob('docs/factory-ng/runs/*.json')))

    def test_scope_tampering_is_rejected(self):
        self.proposal('a', 'a.txt', 'new\n')
        entry = self.entries[0]; ticket = self.root / entry['ticket_path']
        value = json.loads(ticket.read_text()); value['scope']['allowed_paths'] = ['b.txt']; ticket.write_text(json.dumps(value))
        saved = self.root / entry['proposal']; value = json.loads(saved.read_text())
        value['ticket_sha256'] = proposals.checksum(ticket.read_bytes()); saved.write_text(json.dumps(value))
        self.assertTrue(self.verify()['a']['verification_isolate'])

    def test_identical_test_command_runs_once_but_receipts_keep_both_checks(self):
        command = 'python3 -m unittest shared_test'
        self.proposal('a', 'a.txt', 'new\n', [command]); self.proposal('b', 'b.txt', 'new\n', [command])
        with patch.object(self.runner, 'ticket_gate', wraps=self.runner.ticket_gate) as gate:
            result = self.verify()
        self.assertEqual(gate.call_count, 1)
        second = json.loads((self.root / result['b']['receipt']).read_text())
        self.assertIn('reused_from_batch', second['gates'][-1])

    def test_go_tests_share_compilation_and_still_require_named_tests(self):
        (self.source / 'go.mod').write_text('module example.org/focusedbatch' + uuid.uuid4().hex + '\n\ngo 1.23\n')
        self.git('add', '.'); self.commit(); self.base = self.git('rev-parse', 'HEAD').strip()
        for name in ('A', 'B'):
            self.proposal(name, name.lower() + '_test.go',
                          'package batch\nimport "testing"\nfunc Test%s(t *testing.T) {}\n' % name,
                          ['go test -x . -run Test%s -count=1' % name])
        original = self.runner.ticket_gate
        executions = []
        def gate(*args):
            result = original(*args); executions.append(result); return result
        with patch.object(self.runner, 'ticket_gate', side_effect=gate): result = self.verify()
        self.assertTrue(all('receipt' in x for x in result.values()), result)
        self.assertEqual(len(executions), 2)
        # Go 1.25 includes build diagnostics in the JSON stdout stream.
        self.assertIn('/compile ', executions[0]['stderr'] + executions[0]['stdout'])
        self.assertNotIn('/compile ', executions[1]['stderr'] + executions[1]['stdout'])
        # A selector with no executed test must still fail after successful peers.
        self.assertIn('"Test":"TestA"', executions[0]['stdout'])
        self.assertIn('"Test":"TestB"', executions[1]['stdout'])

    def test_subset_integration_rechecks_composed_acceptance(self):
        self.proposal('a', 'a.txt', 'new\n', ["test $(cat b.txt) = new"])
        self.proposal('b', 'b.txt', 'new\n')
        result = self.verify()
        receipt = json.loads((self.root / result['a']['receipt']).read_text())
        # Only a's patch applied: its shell contract depends on b and MUST fail.
        isolated = self.root / 'subset'
        self.m.git(self.root, 'clone', '--quiet', str(self.source), str(isolated))
        self.m.git(isolated, 'apply', str(self.root / receipt['execution']['candidate_patch']))
        integration = load('factory-ng-integrate')
        (self.root / 'scripts').symlink_to(SCRIPTS, target_is_directory=True)
        with patch.object(integration, 'OPS', self.root):
            gates = []
            self.assertFalse(integration.semantic_gates(receipt, isolated, gates))
        self.assertEqual(gates[-1]['outcome'], 'failed')

    def test_controller_groups_pinned_sources_and_serializes_builds(self):
        a = self.proposal('a', 'a.txt', 'new\n'); b = self.proposal('b', 'b.txt', 'new\n')
        m = load('factory-ng-controller')
        settings = {'verification': {'batch_size': 8, 'collect_seconds': 0}, 'compilation': {'enabled': True}}
        jobs = {'jobs': {entry['ticket_id']: dict(entry, state='awaiting_verification', worker='w', model='model',
                                                dispatch_profile='p', attempts=1) for entry in (a, b)}}
        with patch.object(m, 'OPS', self.root), patch.object(m, 'policy', return_value=settings), \
             patch.object(m, 'job_files', return_value=(self.root / 'result.json', self.root / 'log.txt')), \
             patch.object(m, 'save_jobs'), patch.object(m.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 123
            settings['compilation']['enabled'] = False
            m.dispatch_verification_batch(jobs, [])
            spawn.assert_not_called()
            settings['compilation']['enabled'] = True
            jobs['jobs']['integration'] = {'state': 'integrating'}
            m.dispatch_verification_batch(jobs, [])
            spawn.assert_not_called()
            del jobs['jobs']['integration']
            m.dispatch_verification_batch(jobs, [])
            spawn.assert_called_once()
            manifest = json.loads((self.root / 'result.manifest.json').read_text())
            self.assertEqual([x['ticket_id'] for x in manifest], ['a', 'b'])
            self.assertEqual(jobs['jobs']['a']['attempts'], 1)
            self.assertEqual(jobs['jobs']['a']['pid'], jobs['jobs']['b']['pid'])
            m.dispatch_verification_batch(jobs, [])
            m.dispatch_integration(jobs, [])
            spawn.assert_called_once()

    def test_overlap_runs_one_pinned_batch_alongside_integration(self):
        a = self.proposal('a', 'a.txt', 'new\n'); b = self.proposal('b', 'b.txt', 'new\n')
        m = load('factory-ng-controller')
        settings = {'verification': {'batch_size': 8, 'collect_seconds': 0,
                                      'overlap_integration': True},
                    'compilation': {'enabled': True}, 'integration': {'automatic': True}}
        jobs = {'jobs': {entry['ticket_id']: dict(entry, state='awaiting_verification', worker='w',
                                                model='model', dispatch_profile='p', attempts=1)
                         for entry in (a, b)}}
        jobs['jobs']['integration'] = {'state': 'integrating', 'pid': 100}
        # A further accepted patch must not block the independent verifier slot.
        jobs['jobs']['accepted'] = {'state': 'awaiting_integration', 'receipt': 'r.json'}
        with patch.object(m, 'OPS', self.root), patch.object(m, 'policy', return_value=settings), \
             patch.object(m, 'job_files', return_value=(self.root / 'result.json', self.root / 'log.txt')), \
             patch.object(m, 'save_jobs'), patch.object(m.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 123
            m.dispatch_verification_batch(jobs, [])
            spawn.assert_called_once()
            manifest = json.loads((self.root / 'result.manifest.json').read_text())
            self.assertEqual([x['ticket_id'] for x in manifest], ['a', 'b'])
            self.assertEqual(jobs['jobs']['a']['pid'], 123)
            self.assertEqual(jobs['jobs']['b']['pid'], 123)
            self.assertEqual(jobs['jobs']['integration']['pid'], 100)
            m.dispatch_verification_batch(jobs, [])
            m.dispatch_integration(jobs, [])
            spawn.assert_called_once()

    def test_local_and_remote_slots_claim_disjoint_batches(self):
        entries = [self.proposal(x, x + '.txt', 'new\n') for x in ('a', 'b', 'c', 'd')]
        m = load('factory-ng-controller')
        settings = {'verification': {'batch_size': 2, 'collect_seconds': 0, 'overlap_integration': True},
                    'compilation': {'enabled': True}}
        jobs = {'jobs': {e['ticket_id']: dict(e, state='awaiting_verification', worker='w',
                                             model='model', dispatch_profile='p') for e in entries}}
        with patch.object(m, 'OPS', self.root), patch.object(m, 'policy', return_value=settings), \
             patch.object(m, 'job_files', side_effect=lambda name: (self.root/(name+'.json'), self.root/(name+'.log'))), \
             patch.object(m, 'save_jobs'), patch.object(m.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 123
            m.dispatch_verification_batch(jobs, [])
            spawn.return_value.pid = 456
            m.dispatch_verification_batch(jobs, [], host='ryzen-395')
            self.assertEqual(spawn.call_count, 2)
            self.assertIn('factory-ng-verify-remote.py', str(spawn.call_args.args[0]))
            self.assertEqual({jobs['jobs'][x]['pid'] for x in ('a', 'b')}, {123})
            self.assertEqual({jobs['jobs'][x]['pid'] for x in ('c', 'd')}, {456})
            self.assertTrue(m.verification_slot_busy(jobs))
            self.assertTrue(m.verification_slot_busy(jobs, 'ryzen-395'))
            m.dispatch_verification_batch(jobs, [])
            m.dispatch_verification_batch(jobs, [], host='ryzen-395')
            self.assertEqual(spawn.call_count, 2)

    def test_remote_keeps_isolated_proposals_separate_and_does_not_repeat_failures(self):
        entries = [self.proposal(x, x + '.txt', 'new\n') for x in ('a', 'b')]
        m = load('factory-ng-controller')
        settings = {'verification': {'batch_size': 8, 'collect_seconds': 0, 'overlap_integration': True},
                    'compilation': {'enabled': True}}
        jobs = {'jobs': {e['ticket_id']: dict(e, state='awaiting_verification', worker='w',
                                             model='model', dispatch_profile='p', verification_isolate=True)
                         for e in entries}}
        with patch.object(m, 'OPS', self.root), patch.object(m, 'policy', return_value=settings), \
             patch.object(m, 'job_files', side_effect=lambda name: (self.root/(name+'.json'), self.root/(name+'.log'))), \
             patch.object(m, 'save_jobs'), patch.object(m.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 123
            m.dispatch_verification_batch(jobs, [], host='ryzen-395-1', slot=0)
            self.assertEqual(jobs['jobs']['a']['state'], 'working')
            self.assertEqual(jobs['jobs']['b']['state'], 'awaiting_verification')
            jobs['jobs']['b']['verification_remote_failed'] = True
            m.dispatch_verification_batch(jobs, [], host='ryzen-395-2', slot=1)
            spawn.assert_called_once()

    def test_controller_batch_fanout_retains_model_attempts_and_failure_fallback(self):
        m = load('factory-ng-controller')
        jobs = {'jobs': {x: {'ticket_id': x, 'state': 'working', 'pid': -1, 'result_path': 'r.json',
                             'proposal': x + '.json', 'attempts': 1, 'verification_attempts': 1,
                             'verification_batch': True, 'verification_resume': True} for x in ('a', 'b')}}
        payload = {'ticket_results': {'a': {'status': 'accepted_for_dependent_observation', 'receipt': 'a-receipt.json'},
                    'b': {'status': 'verification_pending', 'proposal': 'b.json', 'verification_isolate': True}}}
        with patch.object(m, 'load_json', return_value=payload), patch.object(m, 'save_jobs'), patch.object(m, 'log'), patch.object(m, 'policy', return_value={}):
            m.reconcile_running(jobs, [])
        self.assertEqual(jobs['jobs']['a']['state'], 'awaiting_integration')
        self.assertEqual(jobs['jobs']['b']['state'], 'awaiting_verification')
        self.assertTrue(jobs['jobs']['b']['verification_isolate'])
        self.assertEqual(jobs['jobs']['b']['verification_attempts'], 0)
        self.assertEqual(jobs['jobs']['a']['attempts'], 1)
        self.assertEqual(jobs['jobs']['b']['attempts'], 1)


if __name__ == '__main__':
    unittest.main()
