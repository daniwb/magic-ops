"""Finite reviewed admission and cost-report conservation regressions."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


def load(filename):
    spec = importlib.util.spec_from_file_location(filename, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CapacityTests(unittest.TestCase):
    def test_codex_successor_routes_ordinary_work_but_preserves_exact_cohort(self):
        controller = load('factory-ng-controller.py')
        runner = load('factory-ng-run-engine-ticket.py')
        old, new = 'codex-constrained@1.0.0', 'codex-constrained@1.1.0'
        ticket = {'work_type': 'engine', 'execution': {'compatible_profiles': [old]}}
        self.assertIn(new, controller.compatible_profiles_for(ticket, old))
        self.assertTrue(runner.supports_profile(ticket, new))
        ticket['execution']['profile_policy'] = 'exact'
        self.assertNotIn(new, controller.compatible_profiles_for(ticket, old))
        self.assertFalse(runner.supports_profile(ticket, new))
        ticket['execution']['compatible_profiles'] = [new]
        ticket['execution'].pop('profile_policy')
        self.assertTrue(runner.supports_profile(ticket, new))

    def test_costs_deduplicate_receipts_and_keep_unknowns(self):
        report = load('factory-ng-cost-report.py')
        row = {'receipt_path': 'a', 'ticket_id': 'ticket:a/v1', 'outcome': 'gate_failed',
               'telemetry': {'input_tokens': 10, 'elapsed_ms': 3}}
        other = dict(row, receipt_path='b', telemetry={'input_tokens': {'availability': 'unavailable'}})
        result = report.aggregate([row, row, other])
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(result['counters']['input_tokens']['known_sum'], 10)
        self.assertEqual(result['counters']['input_tokens']['unknown_attempts'], 1)
        self.assertEqual(result['counters']['provider_cost_usd']['unknown_attempts'], 2)

    def test_shared_dependency_is_included_without_unrelated_siblings(self):
        report = load('factory-ng-cost-report.py')
        edges = [('ticket:root', 'ticket:resume'), ('ticket:engine', 'ticket:resume'),
                 ('ticket:engine', 'ticket:unrelated')]
        self.assertEqual(report.mission_members('ticket:root', edges),
                         {'ticket:root', 'ticket:resume', 'ticket:engine'})

    def test_reviewed_admission_is_digest_bound_single_use_and_capacity_limited(self):
        producer = load('factory-ng-reviewed-contracts.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = {'id': 'old'}
            new = {'id': 'new', 'supersedes': 'old', 'production': {'contract_correction_batch': 'batch'}}
            for path, ticket in [('old.json', old), ('new.json', new)]:
                (root / path).write_text(json.dumps(ticket))
            digest = lambda name: 'sha256:' + hashlib.sha256((root / name).read_bytes()).hexdigest()
            manifest = {'batch': 'batch', 'max_active': 2, 'tickets': [{
                'original': 'old', 'original_sha256': digest('old.json'),
                'ticket_path': 'new.json', 'ticket_sha256': digest('new.json')}]}
            jobs = {'old': {'state': 'failed', 'ticket_path': 'old.json'}}
            self.assertEqual(producer.candidate(root, manifest, jobs, {'old': old})['status'], 'ready')
            self.assertEqual(producer.candidate(root, manifest, jobs, {'old': old, 'new': new})['status'], 'no_reviewed_contract_remaining')
            active = {str(i): {'state': 'working'} for i in range(2)}
            self.assertEqual(producer.candidate(root, manifest, active, {str(i): new for i in range(2)})['status'], 'reviewed_contract_reserve_full')
            (root / 'new.json').write_text('{}')
            with self.assertRaises(ValueError):
                producer.candidate(root, manifest, jobs, {'old': old})


if __name__ == '__main__':
    unittest.main()
