"""Repair supply follows current corpus and durable ancestry, never plan samples."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

from factory_ng_producer_cache import ProducerCache


def producer():
    spec = importlib.util.spec_from_file_location('supply_producer',
        Path(__file__).with_name('factory-ng-produce-build-plan.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SupplyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.m = producer()
        self.old = {'ticket_id': 'ticket:map.example/v1', 'state': 'failed',
                    'outcome': 'gate_failed', 'profile': 'qwen-prepared-direct@1.0.2',
                    'retry_generation': 0, 'receipt': 'old-receipt.json'}

    def test_repair_discovers_card_absent_from_plan_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); db = root / 'backend/data/carddb'; db.mkdir(parents=True)
            (db / 'e.json').write_text(json.dumps({'Example': {
                'name': 'Example', 'text': 'Draw a card.', 'status': 'review'}}))
            key = 'build-plan:verb_unmapped:draw:' + self.m.digest_bytes(b'Draw a card.')
            history = {key: [self.old]}
            parser = mock.Mock(reparse_card=lambda _: {'misses': [('verb_unmapped:draw', 'draw')]})
            args = (root, parser, [{'item': 'verb_unmapped:draw', 'examples': []}], {'draw': {}}, history)
            self.assertIsNone(self.m.discover_fresh_example(*args))
            self.assertEqual(self.m.discover_fresh_example(*args, lane='repair')[1], 'Example')
            self.assertIsNone(self.m.discover_fresh_example(*args, lane='conflict'))
            # A newly emitted successor closes this inventory on the next pass.
            history[key].append(dict(self.old, state='queued', retry_generation=1))
            self.assertIsNone(self.m.discover_fresh_example(*args, lane='repair'))

    def test_only_existing_repair_classes_receive_bounded_successors(self):
        m = self.m
        for changes in ({'state': 'completed'}, {'state': 'parked'}, {'state': 'blocked'},
                        {'state': 'working'}, {'state': 'queued'}, {'retry_generation': 1},
                        {'profile': 'codex-constrained@1.1.0'}, {'superseded': True}, {'dedicated_recovery': True},
                        {'outcome': 'invalid_capability_demand'}):
            with self.subTest(changes=changes):
                self.assertIsNone(m.candidate_retry({'key': [dict(self.old, **changes)]}, 'key', 'repair'))
        result = m.candidate_retry({'key': [self.old]}, 'key', 'repair')
        self.assertEqual(result, {'parent': self.old['ticket_id'], 'generation': 1,
                                 'reason': 'semantic_gate_repair', 'receipt': 'old-receipt.json'})
        infra = dict(self.old, profile='claude-staged@1.0.0', outcome='infrastructure_failed_model_protocol')
        self.assertEqual(m.candidate_retry({'key': [infra]}, 'key', 'repair')['reason'], 'infrastructure_repair')
        self.assertIsNone(m.candidate_retry({}, 'key', 'repair'))

    def test_conflict_reserve_and_maximum_historical_budget_survive(self):
        conflict = dict(self.old, state='integration_failed', outcome='candidate_conflict', retry_generation=1)
        self.assertEqual(self.m.candidate_retry({'key': [conflict]}, 'key', 'conflict')['generation'], 2)
        self.assertIsNone(self.m.candidate_retry({'key': [conflict]}, 'key', 'repair'))
        history = {'key': [dict(conflict, retry_generation=2), dict(conflict, retry_generation=0)]}
        self.assertIsNone(self.m.candidate_retry(history, 'key', 'conflict'))

    def test_history_uses_versions_and_cross_key_successors_not_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); tickets = root / 'tickets'; tickets.mkdir()
            jobs = root / 'jobs.json'
            old_id = 'ticket:map.example/v1'; new_id = 'ticket:map.example/v10'
            old = tickets / 'old.json'; newer = tickets / 'new.json'
            old.write_text(json.dumps({'id': old_id, 'production': {'key': 'key'}}))
            newer.write_text(json.dumps({'id': new_id, 'production': {'key': 'key', 'retry_generation': 1}}))
            os.utime(old, (200, 200)); os.utime(newer, (100, 100))
            jobs.write_text(json.dumps({'jobs': {old_id: self.old, new_id: {'state': 'completed'}}}))
            (tickets / 'unrelated.json').write_text(json.dumps({'id': None}))
            self.assertEqual(self.m.next_ticket_id(tickets, 'map.example'), 'ticket:map.example/v11')
            history = self.m.production_history(tickets, jobs)
            self.assertEqual(history['key'][-1]['ticket_id'], new_id)
            self.assertIsNone(self.m.candidate_retry(history, 'key', 'repair'))
            newer.write_text(json.dumps({'id': new_id, 'supersedes': old_id,
                                        'production': {'key': 'key:after:engine'}}))
            history = self.m.production_history(tickets, jobs)
            self.assertTrue(history['key'][0]['superseded'])
            self.assertIsNone(self.m.candidate_retry(history, 'key', 'repair'))

    def test_integration_recovery_obligations_cannot_become_generic_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); tickets = root / 'tickets'; tickets.mkdir(); jobs = root / 'jobs.json'
            jobs.write_text(json.dumps({'jobs': {self.old['ticket_id']: self.old}}))
            for extra in ({'producer': 'build-plan-integration-recovery'},
                          {'integration_repair_generation': 2}, {'trial_id': 'bounded-trial'},
                          {'integration_recovery_parent': 'ticket:map.original/v1'}):
                with self.subTest(extra=extra):
                    (tickets / 'old.json').write_text(json.dumps({'id': self.old['ticket_id'],
                        'production': {'key': 'key', 'producer': 'build-plan-continuous', **extra}}))
                    history = self.m.production_history(tickets, jobs)
                    self.assertIsNone(self.m.candidate_retry(history, 'key', 'repair'))
    def test_repair_cursor_does_not_move_fresh_cursor_and_rechecks_new_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); db = root / 'backend/data/carddb'; db.mkdir(parents=True)
            (db / 'e.json').write_text(json.dumps({'Example': {
                'name': 'Example', 'text': 'Oracle', 'status': 'review'}}))
            key = 'build-plan:verb_unmapped:draw:' + self.m.digest_bytes(b'Oracle')
            parser = mock.Mock(); parser.reparse_card.return_value = {'misses': [('verb_unmapped:draw', 'draw')]}
            cache = ProducerCache(root / 'cache.db')
            scan_key = str(root.resolve()) + ':miss-count=1'
            cache.put('fresh-cursor-v1', scan_key, 'position', 'Fresh position')
            args = (root, parser, [{'item': 'verb_unmapped:draw'}], {'draw': {}}, {key: [self.old]}, cache)
            self.assertIsNotNone(self.m.discover_fresh_example(*args, revision='r1', lane='repair'))
            self.assertEqual(cache.get('fresh-cursor-v1', scan_key, 'position')[1], 'Fresh position')
            parser.reparse_card.return_value = {'misses': []}
            self.assertIsNone(self.m.discover_fresh_example(*args, revision='r2', lane='repair'))
            cache.close()

    def test_main_emits_missing_plan_repair_once_across_process_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); db = root / 'backend/data/carddb'; db.mkdir(parents=True)
            (db / 'e.json').write_text(json.dumps({'Example': {
                'name': 'Example', 'text': 'Draw a card.', 'status': 'review'}}))
            parser_path = root / 'scripts/paragraph/reparse.py'; parser_path.parent.mkdir(parents=True)
            parser_path.write_text('def map_atom(atom):\n    pass\n')
            tickets = root / 'tickets'; tickets.mkdir(); jobs = root / 'jobs.json'
            plan = root / 'plan.jsonl'
            plan.write_text(json.dumps({'item': 'verb_unmapped:draw', 'examples': ['Obsolete sample']}) + '\n')
            key = 'build-plan:verb_unmapped:draw:' + self.m.digest_bytes(b'Draw a card.')
            old_id = 'ticket:map.example/v1'
            (tickets / 'old.json').write_text(json.dumps({'id': old_id, 'production': {'key': key}}))
            jobs.write_text(json.dumps({'jobs': {old_id: self.old}}))

            def run():
                m = producer()  # a fresh interpreter/module must retain no selection memory
                output = io.StringIO()
                argv = ['producer', '--lane', 'repair', '--repo', str(root), '--ticket-dir', str(tickets),
                        '--jobs', str(jobs), '--plan', str(plan)]
                fake_parser = mock.Mock(reparse_card=lambda _: {'misses': [('verb_unmapped:draw', 'draw')]})
                with mock.patch.object(sys, 'argv', argv), mock.patch.dict(sys.modules, reparse=fake_parser), \
                     mock.patch.object(m, 'clean_source', return_value=True), \
                     mock.patch.object(m, 'source_revision', return_value='a' * 40), \
                     mock.patch.object(m, 'registry_effects', return_value={'draw': {
                         'path': 'backend/cards/registry.go', 'executor': 'Draw', 'shape_test': 'TestDraw'}}), \
                     mock.patch.object(m, 'ProducerCache', side_effect=lambda _: ProducerCache(root / 'cache.db')), \
                     contextlib.redirect_stdout(output):
                    m.main()
                return json.loads(output.getvalue())

            result = run(); self.assertEqual(result['status'], 'ready')
            ticket = result['ticket']
            self.assertEqual(ticket['supersedes'], old_id)
            self.assertEqual(ticket['production']['retry_generation'], 1)
            self.assertEqual(result['measurement']['members'][0]['name'], 'Example')
            self.assertTrue(any(e.get('path') == 'old-receipt.json' for e in ticket['evidence']))
            self.assertTrue(any('zero remaining pinned members' in gate for gate in ticket['gates']))
            (tickets / 'successor.json').write_text(json.dumps(ticket))
            jobs.write_text(json.dumps({'jobs': {old_id: self.old, ticket['id']: dict(self.old, state='failed')}}))
            self.assertEqual(run()['status'], 'exhausted_supported_plan')


if __name__ == '__main__':
    unittest.main()
