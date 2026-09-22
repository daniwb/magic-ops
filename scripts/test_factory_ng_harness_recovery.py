import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('factory-ng-reviewed-harness-recovery.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class HarnessRecoveryTests(unittest.TestCase):
    def test_only_presemantic_failures_are_eligible(self):
        receipt = {'outcome': 'gate_failed', 'gates': [{'id': 'ticket-gate-0', 'outcome': 'failed',
                    'command': 'test -z "$(gofmt -l file.go)"'}]}
        self.assertEqual(m.failure_kind(receipt), 'formatting')
        receipt['attempt_history'] = [{'gates': [{'id': 'ticket-gate-1', 'outcome': 'failed', 'command': 'go test ./game'}]}]
        self.assertIsNone(m.failure_kind(receipt))
        receipt.pop('attempt_history')
        receipt['gates'].append({'id': 'ticket-gate-1', 'outcome': 'failed', 'command': 'go test ./...'})
        self.assertIsNone(m.failure_kind(receipt))
        receipt['gates'] = [{'id': 'ticket-gate-0', 'outcome': 'failed', 'command': 'python3 behavior_test.py'}]
        self.assertIsNone(m.failure_kind(receipt))
        receipt['gates'] = [{'id': 'patch-apply', 'outcome': 'failed', 'detail': 'SEARCH did not match'}]
        self.assertEqual(m.failure_kind(receipt), 'patch_protocol')
        receipt['outcome'] = 'parked'
        self.assertIsNone(m.failure_kind(receipt))

    def test_review_is_hash_bound_finite_and_preserves_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = {'id': 'ticket:engine.example/v2', 'work_type': 'engine', 'title': 'Example',
                        'parents': ['ticket:map.parent/v1'],
                        'source': {'revision': 'old', 'repository': '/source'},
                        'scope': {'allowed_paths': ['a.go']}, 'gates': ['format', 'semantic'],
                        'required_behavior': ['the actual behavior'], 'capability': {'required_behavior': 'actual'},
                        'execution': {'selected_profile': 'claude-staged@1.0.0',
                                      'compatible_profiles': ['claude-staged@1.0.0', 'codex-constrained@1.0.0']},
                        'production': {'retry_generation': 2, 'key': 'capability:example'}}
            (root / 'ticket.json').write_text(json.dumps(original))
            receipt = {'outcome': 'gate_failed', 'gates': [{'id': 'patch-apply', 'outcome': 'failed', 'detail': 'SEARCH not found'}]}
            (root / 'receipt.json').write_text(json.dumps(receipt))
            item = {'ticket_id': original['id'], 'ticket_sha256': m.digest(root / 'ticket.json'),
                    'receipt': 'receipt.json', 'receipt_sha256': m.digest(root / 'receipt.json'),
                    'attempts': 3, 'kind': 'patch_protocol'}
            manifest = {'schema': 'factory.reviewed-harness-recovery/v1', 'batch': 'batch', 'max_active': 24, 'tickets': [item]}
            jobs = {original['id']: {'state': 'failed', 'ticket_path': 'ticket.json', 'receipt': 'receipt.json', 'attempts': 3}}
            jobs['ticket:map.parent/v1'] = {'state': 'blocked'}
            tickets = {original['id']: original}
            result = m.candidate(root, manifest, jobs, tickets, 'new')
            new = result['ticket']
            for key in ('scope', 'gates', 'required_behavior', 'capability'):
                self.assertEqual(new[key], original[key])
            self.assertEqual(new['production']['retry_generation'], 2)
            self.assertEqual(new['source']['revision'], 'new')
            self.assertEqual(new['supersedes'], original['id'])
            self.assertEqual(new['execution']['compatible_profiles'][0], 'codex-constrained@1.1.0')
            self.assertIn('claude-staged@1.0.0', new['execution']['compatible_profiles'])
            self.assertEqual(original['execution']['selected_profile'], 'claude-staged@1.0.0')
            jobs['ticket:map.parent/v1']['state'] = 'completed'
            self.assertEqual(m.candidate(root, manifest, jobs, tickets, 'new')['status'], 'no_reviewed_harness_remaining')
            jobs['ticket:map.parent/v1']['state'] = 'blocked'
            self.assertEqual(m.candidate(root, manifest, jobs, tickets, 'new', lambda t: 'contract collision')['status'], 'no_reviewed_harness_remaining')
            tickets[new['id']] = new
            self.assertEqual(m.candidate(root, manifest, jobs, tickets, 'new')['status'], 'no_reviewed_harness_remaining')
            del tickets[new['id']]
            (root / 'receipt.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'changed after audit'):
                m.candidate(root, manifest, jobs, tickets, 'new')


if __name__ == '__main__':
    unittest.main()
