#!/usr/bin/env python3
"""Real parser handoffs and source waits must preserve evidence and budgets."""
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from factory_ng_map_context import trace_card, map_regions
from factory_ng_safety import source_wait_receipt


class MapContextTests(unittest.TestCase):
    def test_real_arguments_are_copied_and_parser_restored(self):
        parser = types.SimpleNamespace()
        def atom(verb, args, kind=None):
            return None
        parser.map_atom = atom
        def parse(card):
            ch = 'put x counters on this creature'
            parser.map_atom('put_counters', None, kind='triggered')
            args = {'amount': 'three'}
            parser.map_atom('mill', args, kind='triggered')
            args['amount'] = 'changed'
            return {'eligible': False}
        parser.reparse_card = parse
        result, calls = trace_card(parser, {})
        self.assertFalse(result['eligible'])
        self.assertIsNone(calls[0]['args'])
        self.assertEqual(calls[0]['clause'], 'put x counters on this creature')
        self.assertEqual(calls[1]['args'], {'amount': 'three'})
        self.assertIs(parser.map_atom, atom)
        parser.reparse_card = mock.Mock(side_effect=ValueError('bad card'))
        with self.assertRaises(ValueError):
            trace_card(parser, {})
        self.assertIs(parser.map_atom, atom)

    def test_null_arguments_include_raw_helper_and_current_verb_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'scripts/paragraph/reparse.py'
            path.parent.mkdir(parents=True)
            path.write_text('\n' * 400 + '''def map_atom(verb, args):
    if args is None: return None
    if verb == 'put_counters':
        return 'counter branch'
    elif verb == 'mill':
        return 'unrelated branch'

def _put_counters_per_count(ch):
    return 'raw count helper'
''')
            sections, remaining = map_regions(root, [{'verb': 'put_counters', 'args': None, 'result': None}])
            text = '\n'.join(sections)
            self.assertIn('raw count helper', text)
            self.assertIn('counter branch', text)
            self.assertIn('401', text)
            self.assertGreaterEqual(remaining, 0)
            _, remaining = map_regions(root, [{'verb': 'put_counters', 'args': None, 'result': None}], budget=3)
            self.assertEqual(remaining, 0)

    def test_source_wait_refund_is_bound_to_one_receipt_and_ticket(self):
        spec = importlib.util.spec_from_file_location('source_wait_controller', Path(__file__).with_name('factory-ng-controller.py'))
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ticket = {'id': 'ticket:map.test/v1', 'source': {'revision': 'abc'}}
            path = root / 'ticket.json'
            path.write_text(json.dumps(ticket))
            first = source_wait_receipt(path, ticket, 'worker', 'profile', 'model', root / 'runs', root, 'index.lock')
            second = source_wait_receipt(path, ticket, 'worker', 'profile', 'model', root / 'runs', root, 'index.lock')
            self.assertNotEqual(first['receipt'], second['receipt'])
            job = {'ticket_id': ticket['id'], 'attempts': 2}
            with mock.patch.object(controller, 'OPS', root):
                self.assertTrue(controller.refund_source_wait_attempt(job, first['receipt']))
                self.assertEqual(job['attempts'], 1)
                self.assertFalse(controller.refund_source_wait_attempt(job, first['receipt']))
                self.assertFalse(controller.refund_source_wait_attempt({'ticket_id': 'other'}, first['receipt']))
                receipt = json.loads((root / second['receipt']).read_text())
                receipt['execution']['model_called'] = True
                (root / second['receipt']).write_text(json.dumps(receipt))
                self.assertFalse(controller.refund_source_wait_attempt(job, second['receipt']))

    def test_dispatch_waits_before_allocating_worker_or_attempt(self):
        spec = importlib.util.spec_from_file_location('source_dispatch_controller', Path(__file__).with_name('factory-ng-controller.py'))
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        jobs = {'jobs': {'test': {'state': 'queued', 'attempts': 0}}}
        with mock.patch.object(controller, 'sync_jobs', return_value=(jobs, {})), \
             mock.patch.object(controller, 'reconcile_running'), \
             mock.patch.object(controller, 'save_jobs'), \
             mock.patch.object(controller, 'source_problem', return_value='index.lock'), \
             mock.patch.object(controller, 'next_dispatch') as dispatch:
            results = []
            controller.dispatch_one(results, [])
            dispatch.assert_not_called()
            self.assertEqual(jobs['jobs']['test']['attempts'], 0)
            self.assertEqual(results[0]['status'], 'source_unavailable')


if __name__ == '__main__':
    unittest.main()
