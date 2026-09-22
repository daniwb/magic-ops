"""Lifecycle caching observes edits, replacement, publication and removal."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


class ControllerCacheTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            'controller_cache_test', Path(__file__).with_name('factory-ng-controller.py'))
        self.controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.controller)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.controller.OPS = self.root
        self.controller.TICKETS = self.root / 'tickets'
        self.controller.TICKETS.mkdir()

    def test_ticket_cache_tracks_same_size_edit_replacement_removal_and_partial_publication(self):
        m = self.controller
        path = m.TICKETS / 'ticket.json'
        path.write_text('')
        self.assertEqual(m.ticket_projections(), [])
        ticket = {'schema': 'factory.ticket-spec/v1', 'id': 'ticket:test/v1',
                  'lifecycle': 'ready_for_observation', 'work_type': 'map',
                  'execution': {'selected_profile': 'profile-a', 'parser_probes': ['large']},
                  'production': {'retry_generation': 1}, 'required_behavior': ['large']}
        path.write_text(json.dumps(ticket))
        first = m.ticket_projections()[0]
        self.assertEqual(first[2], 'tickets/ticket.json')
        self.assertNotIn('required_behavior', first[1])
        self.assertNotIn('parser_probes', first[1]['execution'])
        with mock.patch.object(m, 'load_json', side_effect=AssertionError('unchanged ticket reread')):
            self.assertEqual(m.ticket_projections(), [first])
        old_stat = path.stat()
        ticket['execution']['selected_profile'] = 'profile-b'
        path.write_text(json.dumps(ticket))
        os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        self.assertEqual(m.ticket_projections()[0][1]['execution']['selected_profile'], 'profile-b')
        replacement = self.root / 'replacement'
        ticket['supersedes'] = 'ticket:older/v1'
        replacement.write_text(json.dumps(ticket))
        replacement.replace(path)
        self.assertEqual(m.ticket_projections()[0][1]['supersedes'], 'ticket:older/v1')
        path.unlink()
        self.assertEqual(m.ticket_projections(), [])
        self.assertEqual(m._ticket_projection_cache, {})

    def test_one_receipt_snapshot_produces_both_indexes_without_rescanning(self):
        m = self.controller
        receipts = [('observation', {'schema': 'factory.observation-receipt/v1',
                                    'ticket': {'id': 'ticket:test/v1'}, 'outcome': 'accepted'}),
                    ('integration', {'schema': 'factory.integration-receipt/v1',
                                     'parents': ['ticket:test/v1'],
                                     'outcome': 'pushed_full_production_gate_green'})]
        with mock.patch.object(m, 'receipt_projections', side_effect=AssertionError('second scan')):
            self.assertEqual(m.observed_ticket_ids(receipts)['ticket:test/v1']['receipt'], 'observation')
            self.assertEqual(m.integrated_ticket_ids(receipts)['ticket:test/v1']['receipt'], 'integration')

    def test_admission_cache_preserves_duplicate_checks_after_replacement_and_removal(self):
        m = self.controller
        path = m.TICKETS / 'old.json'
        path.write_text(json.dumps({'id': 'old', 'production': {'key': 'first'}, 'evidence': ['large packet']}))
        jobs = {'jobs': {'old': {'state': 'working'}}}
        with mock.patch.object(m, 'load_jobs', return_value=jobs):
            self.assertEqual(m.persist_ready({'ticket': {'id': 'new', 'production': {'key': 'first'}}}), ('duplicate_active', 'old'))
            original_load = m.load_json
            def no_packet_reload(p):
                self.assertNotEqual(p, path)
                return original_load(p)
            with mock.patch.object(m, 'load_json', side_effect=no_packet_reload):
                self.assertEqual(m.persist_ready({'ticket': {'id': 'new', 'production': {'key': 'first'}}}), ('duplicate_active', 'old'))
            replacement = self.root / 'replacement'
            replacement.write_text(json.dumps({'id': 'old', 'production': {'key': 'new-key'}}))
            replacement.replace(path)
            self.assertEqual(m.persist_ready({'ticket': {'id': 'new', 'production': {'key': 'new-key'}}}), ('duplicate_active', 'old'))
            path.unlink()
            self.assertEqual(m.persist_ready({'ticket': {'id': 'new', 'production': {'key': 'new-key'}}}), ('queued', 'new'))

    def test_missing_directory_clears_cache(self):
        m = self.controller
        m.TICKETS.rmdir()
        m._ticket_projection_cache['removed'] = None
        self.assertEqual(m.ticket_projections(), [])
        self.assertEqual(m._ticket_projection_cache, {})


if __name__ == '__main__':
    unittest.main()
