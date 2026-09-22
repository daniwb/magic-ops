"""Bounded collection and the shared-wave failure recovery contract."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('batch_controller',
                                            Path(__file__).with_name('factory-ng-controller.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class BatchingTest(unittest.TestCase):
    def setUp(self):
        self.settings = {'wave_size': 8, 'collect_seconds': 120, 'collect_min_candidates': 3}
        self.first = {'state': 'awaiting_integration', 'finished_at': '2026-09-12T12:00:00Z'}
        self.second = dict(self.first, finished_at='2026-09-12T12:00:30Z')
        self.jobs = {'jobs': {'worker': {'state': 'working'}}}
        self.epoch = m.datetime.fromisoformat('2026-09-12T12:00:40+00:00').timestamp()

    def wait(self, selected, **settings):
        return m.integration_collection_wait(selected, self.jobs,
                                             dict(self.settings, **settings), self.epoch)

    def test_new_arrivals_do_not_extend_oldest_deadline(self):
        self.assertEqual(self.wait([self.first]), 80)
        self.assertEqual(self.wait([self.first, self.second]), 80)
        self.epoch += 80
        self.assertEqual(self.wait([self.first, self.second]), 0)

    def test_collection_flushes_when_target_reached(self):
        self.assertEqual(self.wait([self.first, self.second, dict(self.second)]), 0)
        self.assertEqual(self.wait([self.first, self.second], wave_size=2), 0)

    def test_idle_fleet_and_isolated_retries_never_wait(self):
        self.assertEqual(self.wait([dict(self.first, integration_isolate=True)]), 0)
        self.jobs['jobs']['worker']['state'] = 'queued'
        self.assertEqual(self.wait([self.first]), 0)

    def test_remote_isolated_verification_starts_without_batch_collection(self):
        for isolate in (False, True):
            with self.subTest(isolate=isolate), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                pending = dict(self.first, state='awaiting_verification', ticket_id='pending',
                               ticket_path='ticket.json', proposal='proposal.json',
                               worker='codex', model='model', dispatch_profile='profile',
                               verification_isolate=isolate)
                jobs = {'jobs': {'pending': pending, **self.jobs['jobs']}}
                settings = {'verification': dict(self.settings, batch_size=8),
                            'compilation': {'enabled': True}}
                results = []
                with patch.object(m, 'OPS', root), patch.object(m, 'policy', return_value=settings), \
                     patch.object(m, 'load_json', return_value={'source': {'revision': 'base'}}), \
                     patch.object(m, 'job_files', return_value=(root/'out.json', root/'log')), \
                     patch.object(m.time, 'time', return_value=self.epoch), \
                     patch.object(m.subprocess, 'Popen') as spawn, patch.object(m, 'save_jobs'):
                    spawn.return_value.pid = 123
                    m.dispatch_verification_batch(jobs, results, host='ryzen-395-1')
                self.assertEqual(spawn.call_count, int(isolate))
                if isolate:
                    self.assertEqual(pending['state'], 'working')
                    self.assertEqual(pending['verification_attempts'], 1)
                    self.assertEqual(len(json.loads((root/'out.manifest.json').read_text())), 1)
                    self.assertIn('factory-ng-verify-remote.py', str(spawn.call_args.args[0]))
                else:
                    self.assertEqual(pending['state'], 'awaiting_verification')
                    self.assertEqual(results[0]['remaining_seconds'], 80)

    def test_legacy_and_future_timestamps_never_strand_work(self):
        for stamp in (None, '', 'invalid', '2026-09-12T12:00:00', '2026-09-13T12:00:00Z'):
            with self.subTest(stamp=stamp):
                self.assertEqual(self.wait([dict(self.first, finished_at=stamp)]), 0)
        self.assertEqual(self.wait([{}]), 0)

    def test_disabled_and_maximum_collection_window(self):
        self.assertEqual(self.wait([self.first], collect_seconds=0), 0)
        self.assertEqual(self.wait([self.first], collect_seconds=9999), 260)

    def test_dispatch_returns_without_spawning_or_mutating_waiting_work(self):
        first = dict(self.first, receipt='receipt.json', ticket_id='first')
        jobs = {'jobs': {'first': first, **self.jobs['jobs']}}
        results = []
        with patch.object(m, 'policy', return_value={'integration': dict(self.settings, automatic=True)}), \
             patch.object(m, 'source_problem', return_value=''), \
             patch.object(m.time, 'time', return_value=self.epoch), \
             patch.object(m.subprocess, 'Popen') as spawn, patch.object(m, 'save_jobs') as save:
            m.dispatch_integration(jobs, results)
        self.assertFalse(spawn.called)
        self.assertFalse(save.called)
        self.assertEqual(first['state'], 'awaiting_integration')
        self.assertEqual(results[0]['status'], 'collecting_wave')
        self.assertEqual(results[0]['remaining_seconds'], 80)

    def test_failed_shared_wave_is_retried_individually(self):
        jobs = {'jobs': {name: {'ticket_id': name, 'state': 'integrating', 'pid': -1,
                               'result_path': 'result.json', 'integration_wave_size': 3,
                               'integration_attempts': 1}
                         for name in ('first', 'second', 'conflict')}}
        result = {'ticket_results': {
            'first': {'status': 'full_gate_failed', 'reason': 'combined contract failed'},
            'second': {'status': 'full_gate_failed', 'reason': 'combined contract failed'},
            'conflict': {'status': 'candidate_conflict', 'gates': [{'outcome': 'failed'}]}}}
        with patch.object(m, 'load_json', return_value=result), \
             patch.object(m, 'save_jobs'), patch.object(m, 'log'):
            m.reconcile_running(jobs, [])
        for name in ('first', 'second'):
            job = jobs['jobs'][name]
            self.assertEqual(job['state'], 'awaiting_integration')
            self.assertTrue(job['integration_isolate'])
            self.assertEqual(job['integration_attempts'], 1)
            self.assertEqual(self.wait([job]), 0)
        self.assertEqual(jobs['jobs']['conflict']['state'], 'integration_failed')


if __name__ == '__main__':
    unittest.main()
