"""Bound frontier expansion without accepting partial cards or replaying history."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

OPS = Path(__file__).resolve().parents[1]


def producer():
    path = os.environ.get('FRONTIER_PRODUCER', str(OPS / 'scripts/factory-ng-produce-build-plan.py'))
    spec = importlib.util.spec_from_file_location('frontier', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrontierTests(unittest.TestCase):
    def test_additional_families_require_registry_and_preserve_history(self):
        m = producer()
        families = {'token_copy': 'token_copy', 'add_mana': 'add_mana',
                    'regenerate': 'regenerate', 'remove_counter': 'remove_counter',
                    'p_sacrifice': 'edict_sacrifice', 'goad': 'goad',
                    'draw_eq': 'draw', 'p_discard_hand': 'discard'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); db = root / 'backend/data/carddb'; db.mkdir(parents=True)
            (db / 'e.json').write_text(json.dumps({'Example': {
                'name': 'Example', 'text': 'Pinned Oracle', 'status': 'review'}}))
            for verb, effect in families.items():
                with self.subTest(verb=verb):
                    shape = 'verb_unmapped:' + verb
                    parser = mock.Mock()
                    parser.reparse_card.return_value = {'misses': [(shape, 'bounded miss')]}
                    rows = [{'item': shape}]
                    self.assertEqual(m.discover_fresh_example(root, parser, rows, {effect: {}}, {})[1], 'Example')
                    self.assertIsNone(m.discover_fresh_example(root, parser, rows, {}, {}))
                    key = 'build-plan:%s:%s' % (shape, m.digest_bytes(b'Pinned Oracle'))
                    self.assertIsNone(m.discover_fresh_example(root, parser, rows, {effect: {}}, {key: [{}]}))
                    parser.reparse_card.return_value = {'misses': [(shape, 'bounded miss'), ('static_unmapped', 'other')]}
                    parser.reparse_card.side_effect = None
                    self.assertIsNone(m.discover_fresh_example(root, parser, rows, {effect: {}}, {}))

    def scan(self, count, misses, accounted=False):
        m = producer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); db = root / 'backend/data/carddb'; db.mkdir(parents=True)
            card = {'name': 'Example', 'text': 'Oracle', 'status': 'review'}
            (db / 'e.json').write_text(json.dumps({'Example': card}))
            history = {'build-plan:verb_unmapped:draw:' + m.digest_bytes(b'Oracle'): [{}]} if accounted else {}
            return m.discover_fresh_example(root, mock.Mock(reparse_card=lambda card: {'misses': misses}),
                [{'item': 'verb_unmapped:draw'}], {'draw': {}}, history, miss_count=count)

    def test_default_single_lane_does_not_admit_two_misses(self):
        self.assertIsNone(self.scan(1, [('verb_unmapped:draw', 'first'), ('verb_unmapped:draw', 'second')]))

    def test_two_lane_admits_both_occurrences_of_one_family(self):
        self.assertEqual(self.scan(2, [('verb_unmapped:draw', 'first'), ('verb_unmapped:draw', 'second')])[1], 'Example')

    def test_two_lane_rejects_mixed_or_three_misses(self):
        self.assertIsNone(self.scan(2, [('verb_unmapped:draw', 'first'), ('static_unmapped', 'second')]))
        self.assertIsNone(self.scan(2, [('verb_unmapped:draw', str(i)) for i in range(3)]))

    def test_expansion_does_not_reset_existing_history(self):
        self.assertIsNone(self.scan(2, [('verb_unmapped:draw', 'first'), ('verb_unmapped:draw', 'second')], accounted=True))

    def test_two_lane_bound_includes_map_waiting_for_engine(self):
        m = producer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jobs = root / 'jobs.json'; tickets = root / 'tickets'; tickets.mkdir()
            for i in range(2):
                (tickets / f'{i}.json').write_text(json.dumps({'id': str(i), 'production': {
                    'producer': 'build-plan-continuous', 'miss_count': 2}}))
            jobs.write_text(json.dumps({'jobs': {'0': {'state': 'blocked'}, '1': {'state': 'working'}}}))
            out = io.StringIO()
            with mock.patch.object(sys, 'argv', ['producer', '--lane', 'fresh', '--miss-count', '2',
                    '--max-active', '2', '--jobs', str(jobs), '--ticket-dir', str(tickets)]), \
                    mock.patch.object(m, 'clean_source', side_effect=AssertionError('full frontier should not scan')), \
                    contextlib.redirect_stdout(out):
                m.main()
            self.assertEqual(json.loads(out.getvalue())['status'], 'active_frontier_limit')

    def test_registry_metadata_uses_go_syntax(self):
        m = producer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cards = root / 'backend/cards'; cards.mkdir(parents=True)
            game = root / 'backend/game'; game.mkdir()
            (game / 'ability_effects.go').write_text('package game\n')
            (cards / 'registry.go').write_text('''package cards
var V2EffectRegistry = map[string]Primitive{"draw": {Executor:"real", ShapeTest:"TestDraw"}}
''')
            (cards / 'registry_prevent.go').write_text('''package cards
// regEffect("fake_comment", Primitive{Executor:"fake", ShapeTest:"Fake"})
func unused() { regEffect("fake_function", Primitive{Executor:"fake", ShapeTest:"Fake"}) }
func init() {
 regEffect("prevent", Primitive{Executor:"Register(&ReplacementEffect{}) then consume", ShapeTest:"TestPrevent"})
 V2EffectRegistry["assigned"] = Primitive{Executor:"real", ShapeTest:"TestAssigned"}
 regEffect("incomplete", Primitive{Executor:"no shape test"})
}
''')
            entries = m.registry_effects(root)
            self.assertEqual(set(entries), {'draw', 'prevent', 'assigned'})
            self.assertEqual(entries['prevent']['shape_test'], 'TestPrevent')
            self.assertEqual(entries['prevent']['path'], 'backend/cards/registry_prevent.go')

    def test_partial_card_still_fails_pinned_gate(self):
        spec = importlib.util.spec_from_file_location('map_runner', OPS / 'scripts/factory-ng-run-map-ticket.py')
        runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
        command = 'python3 factory-ng-targeted-demand.py --members-from pinned.json reports zero remaining pinned members'
        for measured in ({'member_count': 1, 'pinned_unresolved_count': 1},
                         {'member_count': 0, 'pinned_unresolved_count': 1}):
            result = {'exit_code': 0, 'stdout': json.dumps(measured), 'stderr': ''}
            with mock.patch.object(runner, 'run', return_value=result):
                self.assertEqual(runner.run_ticket_gate(command, Path('.'), {'work_type': 'map'})['exit_code'], 1)

    def test_coverage_uses_enabled_producer_measurement(self):
        path = os.environ.get('FRONTIER_COVERAGE', str(OPS / 'scripts/factory-ng-coverage-snapshot.py'))
        spec = importlib.util.spec_from_file_location('coverage_snapshot', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'config').mkdir(); tickets = root / 'tickets'; tickets.mkdir()
            plan = root / 'plan.jsonl'
            plan.write_text(json.dumps({'item': 'verb_unmapped:draw', 'marginal_unlock': 36,
                'source_revision': 'pinned', 'measured_at': '2026-09-12T00:00:00Z'}) + '\n')
            (root / 'config/factory-ng-producers.json').write_text(json.dumps({'producers': [
                {'enabled': False, 'command': ['scripts/factory-ng-produce-build-plan.py', '--lane', 'fresh', '--plan', 'wrong']},
                {'enabled': True, 'command': ['scripts/factory-ng-produce-build-plan.py', '--lane', 'fresh', '--plan', 'plan.jsonl']}
            ]}))
            with mock.patch.multiple(module, OPS=root, PLAN=None, TICKETS=tickets, JOBS=root / 'absent'):
                snapshot = module.build()
            self.assertEqual(snapshot['plan_path'], str(plan))
            self.assertEqual(snapshot['source_revision'], 'pinned')
            self.assertEqual(snapshot['shapes'][0]['unlock'], 36)


if __name__ == '__main__':
    unittest.main()
