#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from factory_ng_context import requested_context
from factory_ng_context_recovery import context_repair_requests, park_legacy_context_failure, CONTEXT_VERSION, historical_evidence_gap
from factory_ng_investigation import STAGED, evidence_gap
from factory_ng_map_context import trace_card, upstream_regions, prepared_ticket_view
import types
import sys
import copy
import importlib.util
from unittest import mock


class ContextRecoveryTests(unittest.TestCase):
    def test_legacy_location_projection_does_not_widen_live_investigation_contract(self):
        reply = 'EVIDENCE_GAP: ' + json.dumps({'question': 'Missing source', 'searched': ['source%d' % n for n in range(9)]})
        self.assertIsNone(evidence_gap({'stdout': reply, 'exit_code': 0}, STAGED))
        self.assertEqual(len(historical_evidence_gap(reply)['searched']), 8)
        self.assertIn('source8', reply)
        self.assertIsNone(historical_evidence_gap(reply + '\n<<<FILE edit.go'))
    def test_packet_omits_search_log_bulk_without_changing_contract_or_original(self):
        original = {'scope': {'allowed_paths': ['only.py']}, 'gates': ['original gate'],
                    'required_behavior': ['every clause'], 'evidence': [
                        {'fact': 'actual API', 'symbol': {'id': 'source'},
                         'lookup_trace': [{'query': 'missing', 'status': 'not_found', 'raw': 'x' * 20000}]}]}
        view = prepared_ticket_view(original)
        self.assertLess(len(json.dumps(view)), 1000)
        for key in ('scope', 'gates', 'required_behavior'):
            self.assertEqual(view[key], original[key])
        self.assertEqual(view['evidence'][0]['symbol'], original['evidence'][0]['symbol'])
        self.assertIn('lookup_trace', original['evidence'][0])
        self.assertEqual(view['evidence'][0]['lookup_summary']['recent'][0]['status'], 'not_found')

    def test_python_need_returns_whole_function_and_exact_single_quoted_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'scripts/paragraph/reparse.py'
            path.parent.mkdir(parents=True)
            path.write_text("# if verb == 'bounce': fake\ndef helper(value):\n    if value:\n        return 'complete helper body'\n    return None\n\ndef map_atom(verb):\n    if verb == 'bounce':\n        return 'library_top'\n    return None\n")
            text = requested_context('NEED: scripts/paragraph/reparse.py: helper function', root)
            self.assertIn('complete helper body', text)
            self.assertIn('return None', text)
            text = requested_context("NEED: scripts/paragraph/reparse.py: verb == 'bounce' branch", root)
            self.assertIn("return 'library_top'", text)
            self.assertNotIn('fake', text)
            text = requested_context('NEED: scripts/paragraph/reparse.py: MissingFunction', root)
            self.assertIn('requested implementation unresolved', text)

    def test_failed_handoff_includes_actual_parser_and_grammar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'scripts/paragraph/atoms.py'
            path.parent.mkdir(parents=True)
            source = "VERBS = [('damage', 'real damage grammar', None)]\ndef parse_atom(cl):\n    return ('damage', None)\n"
            path.write_text(source)
            scope = {}
            exec(compile(source, str(path), 'exec'), scope)
            atom = types.SimpleNamespace(parse_atom=scope['parse_atom'])
            original = atom.parse_atom
            parser = types.SimpleNamespace(O=atom, map_atom=lambda *a, **k: None)
            parser.reparse_card = lambda card: parser.map_atom(*atom.parse_atom('deals 1 damage'), kind='triggered')
            _, calls = trace_card(parser, {})
            self.assertIs(atom.parse_atom, original)
            self.assertEqual(calls[0]['atom_parser']['path'], 'scripts/paragraph/atoms.py')
            sections, budget = upstream_regions(root, calls)
            self.assertIn('real damage grammar', '\n'.join(sections))
            self.assertIn('def parse_atom(cl)', '\n'.join(sections))
            self.assertGreaterEqual(budget, 0)

    def test_context_successor_requires_verified_evidence_only_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / 'docs/factory-ng/runs/first.raw.json'
            raw.parent.mkdir(parents=True)
            def artifact(reply, kind=None):
                raw.write_text(json.dumps({'result': reply}))
                return {'path': str(raw.relative_to(root)), 'sha256': 'sha256:' + hashlib.sha256(raw.read_bytes()).hexdigest(), 'kind': kind}
            original = {'id': 'map', 'production': {}}
            history = {'ancestors': ['map']}
            tickets = {'map': original}
            receipt = {'model': {'profile': STAGED}, 'outcome': 'parked',
                       'execution': {}, 'gates': [{'id': 'initial-patch-apply', 'detail': 'no edit blocks'}],
                       'raw_artifacts': [artifact('NEED: scripts/paragraph/reparse.py: helper')]}
            def eligible(): return context_repair_requests(root, receipt, original, history, tickets)
            self.assertEqual(len(eligible()), 1)
            receipt['execution']['candidate_patch'] = 'patch'
            self.assertEqual(eligible(), [])
            receipt['execution'].clear()
            original['production']['context_repair_version'] = CONTEXT_VERSION
            self.assertEqual(eligible(), [])
            original['production'].clear()
            raw.write_text('tampered')
            self.assertEqual(eligible(), [])
            receipt['raw_artifacts'] = [artifact('NEED: scripts/paragraph/reparse.py: helper\n<<<FILE edit.py')]
            self.assertEqual(eligible(), [])
            receipt['raw_artifacts'] = [artifact('VERDICT: NOT_A_SHAPE')]
            self.assertEqual(eligible(), [])

    def test_legacy_evidence_failure_leaves_retry_queue_without_refunding_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / 'docs/factory-ng/runs'; runs.mkdir(parents=True)
            original = {'id': 'map', 'production': {'key': 'same-obligation'},
                        'scope': {'allowed_paths': ['only.py']}, 'gates': ['behavior'],
                        'execution': {'profile_policy': 'exact', 'compatible_profiles': [STAGED]}}
            ticket = root / 'ticket.json'; ticket.write_text(json.dumps(original))
            artifacts = []
            for n, reply in enumerate(['NEED: scripts/paragraph/reparse.py: helper',
                                      'EVIDENCE_GAP: {"question":"Where is it?","searched":["one","two","three","four","five"]}']):
                path = runs / ('%d.raw.json' % n); path.write_text(json.dumps({'result': reply}))
                artifacts.append({'path': str(path.relative_to(root)), 'sha256': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest(),
                                  'kind': 'need_continuation' if n else None})
            receipt = {'model': {'profile': STAGED}, 'outcome': 'infrastructure_failed_model_protocol',
                       'ticket': {'sha256': 'sha256:' + hashlib.sha256(ticket.read_bytes()).hexdigest()}, 'raw_artifacts': artifacts}
            (runs / 'receipt.json').write_text(json.dumps(receipt))
            job = {'state': 'queued', 'outcome': receipt['outcome'], 'attempts': 2,
                   'receipt': 'docs/factory-ng/runs/receipt.json', 'ticket_path': 'ticket.json'}
            self.assertTrue(park_legacy_context_failure(root, job, original, {'map': original}))
            self.assertEqual(job['state'], 'parked')
            self.assertEqual(job['attempts'], 2)
            self.assertFalse(park_legacy_context_failure(root, job, original, {'map': original}))
            successor = copy.deepcopy(original)
            successor.update(id='next', supersedes='map')
            successor['production'].update(context_repair_version=CONTEXT_VERSION, integration_repair_generation=1)
            successor['execution']['context_requests'] = ['scripts/paragraph/reparse.py: helper']
            spec = importlib.util.spec_from_file_location('context_admission_test', Path(__file__).with_name('factory-ng-controller.py'))
            controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
            with mock.patch.multiple(controller, OPS=root, TICKETS=root), \
                 mock.patch.object(controller, 'load_jobs', return_value={'jobs': {'map': job}}):
                invalid = copy.deepcopy(successor); invalid['gates'] = []
                self.assertEqual(controller.persist_ready({'ticket': invalid})[0], 'duplicate_terminal')
                self.assertEqual(controller.persist_ready({'ticket': successor}), ('queued', 'next'))

    def test_trigger_spine_records_exact_failing_return_and_restores_profiler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'scripts/paragraph/triggers.py'
            path.parent.mkdir(parents=True)
            source = "def slot_parse(clause, card):\n    event = 'player_damaged'\n    receiver = None\n    return 2, {'spec': None}\n"
            path.write_text(source)
            scope = {}
            exec(compile(source, str(path), 'exec'), scope)
            trigger = types.SimpleNamespace(slot_parse=scope['slot_parse'])
            original = trigger.slot_parse
            parser = types.SimpleNamespace(T=trigger, map_atom=lambda *a, **k: None)
            parser.reparse_card = lambda card: trigger.slot_parse('Whenever ...', card)
            previous = sys.getprofile()
            _, calls = trace_card(parser, {})
            self.assertIs(sys.getprofile(), previous)
            self.assertIs(trigger.slot_parse, original)
            self.assertEqual(calls[0]['atom_parser']['return_line'], 4)
            self.assertEqual(calls[0]['parser_values']['event'], 'player_damaged')
            sections, _ = upstream_regions(root, calls)
            self.assertIn('return 2', '\n'.join(sections))


if __name__ == '__main__':
    unittest.main()
