#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from factory_ng_retry_batch import active_count, selected


class RetryBatchTest(unittest.TestCase):
    def controller(self):
        spec = importlib.util.spec_from_file_location('retry_batch_controller', Path(__file__).with_name('factory-ng-controller.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def test_two_active_limit_tracks_versions_and_integration(self):
        batch = {'tickets': ['ticket:one/v1', 'ticket:two/v1', 'ticket:three/v1']}
        specs = {'ticket:one/v2': {'supersedes': 'ticket:one/v1'}}
        jobs = {'ticket:one/v1': {'state': 'failed'}, 'ticket:one/v2': {'state': 'integrating'},
                'ticket:two/v1': {'state': 'working'}, 'ticket:other/v1': {'state': 'working'}}
        self.assertEqual(active_count(batch, specs, jobs), 2)
        self.assertTrue(selected(batch, 'ticket:one/v3'))
        self.assertFalse(selected(batch, 'ticket:someone/v1'))
        jobs['ticket:one/v2']['state'] = 'completed'
        self.assertEqual(active_count(batch, specs, jobs), 1)

    def test_admission_cannot_bypass_batch_limit(self):
        controller = self.controller()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'config').mkdir(); tickets = root / 'tickets'; tickets.mkdir()
            batch = {'enabled': True, 'id': 'four', 'tickets': ['ticket:one/v1', 'ticket:two/v1', 'ticket:three/v1']}
            (root / 'config/factory-ng-context-retry-batch.json').write_text(json.dumps(batch))
            jobs = {'jobs': {'ticket:one/v2': {'state': 'queued'}, 'ticket:two/v2': {'state': 'awaiting_integration'}}}
            with mock.patch.multiple(controller, OPS=root, TICKETS=tickets), mock.patch.object(controller, 'load_jobs', return_value=jobs):
                self.assertEqual(controller.persist_ready({'ticket': {'id': 'ticket:three/v2'}}), ('retry_batch_full', 'ticket:three/v2'))
                self.assertEqual(list(tickets.iterdir()), [])

    def test_selected_replays_use_staged_workers_and_keep_trial_restriction(self):
        controller = self.controller()
        job = {'work_type': 'map', 'production': {'retry_batch': 'four'}}
        self.assertTrue(controller.worker_supports_job({'profile': 'claude-staged@1.0.0'}, job))
        self.assertFalse(controller.worker_supports_job({'profile': 'codex-constrained@1.0.0'}, job))
        self.assertFalse(controller.worker_supports_job({'profile': 'claude-staged@1.0.0', 'map_trial_only': 'five'}, job))
        job['production']['trial_id'] = 'five'
        self.assertTrue(controller.worker_supports_job({'profile': 'claude-staged@1.0.0', 'map_trial_only': 'five'}, job))


if __name__ == '__main__':
    unittest.main()
