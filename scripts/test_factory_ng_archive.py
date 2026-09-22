import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from factory_ng_archive import archive_jobs, archived


class ArchiveTests(unittest.TestCase):
    def test_dependencies_outrank_discovery_and_discovery_uses_rank(self):
        spec = importlib.util.spec_from_file_location('priority_controller', Path(__file__).with_name('factory-ng-controller.py'))
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        engine = {'work_type': 'engine', 'state': 'queued'}
        first = {'work_type': 'map', 'state': 'queued', 'production': {'producer': 'corpus-frontier', 'ranking': [1, 1, -20, 50]}}
        second = {'work_type': 'map', 'state': 'queued', 'production': {'producer': 'corpus-frontier', 'ranking': [4, 2, -1, 100]}}
        self.assertLess(controller.dispatch_priority(('engine', engine)), controller.dispatch_priority(('first', first)))
        self.assertLess(controller.dispatch_priority(('first', first)), controller.dispatch_priority(('second', second)))

    def test_completion_is_cold_but_dependency_and_duplicate_identity_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = {'ticket_id': 'done', 'state': 'completed', 'receipt': 'observation.json',
                        'integration_receipt': 'integration.json', 'production': {'key': 'unique'},
                        'attempts': 3, 'usage_status': {'large': 'historical detail'}}
            jobs = {'done': dict(original), 'busy': {'state': 'working'},
                    'failed': {'state': 'failed', 'attempts': 2},
                    'old': {'state': 'failed', 'superseded_by': 'done'}}
            self.assertEqual(archive_jobs(root, jobs, 'now'), 2)
            self.assertTrue(archived(jobs['done']))
            self.assertNotIn('usage_status', jobs['done'])
            self.assertEqual(jobs['done']['production']['key'], 'unique')
            self.assertEqual(jobs['done']['attempts'], 3)
            self.assertEqual(json.loads((root / jobs['done']['archive_path']).read_text())['job'], original)
            self.assertFalse(archived(jobs['busy']))
            self.assertFalse(archived(jobs['failed']))
            self.assertEqual(archive_jobs(root, jobs, 'later'), 0)
            jobs['done']['state'] = 'queued'
            self.assertFalse(archived(jobs['done']))

    def test_crash_between_archive_and_tombstone_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = {'done': {'state': 'completed', 'ticket_id': 'done'}}
            first = json.loads(json.dumps(original))
            archive_jobs(root, first, 'first')
            archive_jobs(root, original, 'second')
            self.assertEqual(original['done']['archive_path'], first['done']['archive_path'])
            self.assertEqual(len(list((root / 'docs/factory-ng/job-archive').glob('*.json'))), 1)

    def test_archive_work_per_cycle_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = {str(i): {'state': 'completed'} for i in range(4)}
            self.assertEqual(archive_jobs(Path(tmp), jobs, 'now', limit=2), 2)
            self.assertEqual(sum(archived(j) for j in jobs.values()), 2)

    def test_archived_artifact_is_not_statted_but_hot_replacement_is_seen(self):
        spec = importlib.util.spec_from_file_location('archive_controller', Path(__file__).with_name('factory-ng-controller.py'))
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller.OPS = root
            cold = root / 'cold.json'; hot = root / 'hot.json'
            cold.write_text('{"state":"done"}'); hot.write_text('{"state":"active"}')
            cache = {}
            is_cold = lambda entry: entry[3] == cold
            controller.cached_artifacts(root, cache, lambda v: v, is_cold)
            original_stat = Path.stat
            def stat(path, *args, **kwargs):
                if path == cold:
                    raise AssertionError('archived artifact statted')
                return original_stat(path, *args, **kwargs)
            hot.write_text('{"state":"changed"}')
            with mock.patch.object(Path, 'stat', stat):
                controller.cached_artifacts(root, cache, lambda v: v, is_cold)
            self.assertEqual(cache[str(hot)][1]['state'], 'changed')


if __name__ == '__main__':
    unittest.main()
