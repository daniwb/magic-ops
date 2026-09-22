"""Multi-clause admission must retain whole-card gates and one durable lineage."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from factory_ng_producer_cache import ProducerCache

OPS = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, OPS / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MultiMissTests(unittest.TestCase):
    def setUp(self):
        self.m = load('factory-ng-produce-build-plan')
        self.effects = {name: {'path': 'backend/cards/registry_%s.go' % name,
                              'executor': name, 'shape_test': 'Test' + name}
                        for name in ('draw', 'damage', 'tap')}
        self.misses = [('verb_unmapped:draw', 'draw first'), ('verb_unmapped:damage', 'damage'),
                       ('verb_unmapped:draw', 'draw again')]

    def fixture(self, root):
        db = root / 'backend/data/carddb'; db.mkdir(parents=True)
        card = {'name': 'Example', 'text': 'Draw, damage, then draw again.', 'status': 'review'}
        (db / 'e.json').write_text(json.dumps({'Example': card}))
        parser_path = root / 'scripts/paragraph/reparse.py'; parser_path.parent.mkdir(parents=True)
        parser_path.write_text('def map_atom(atom):\n    pass\n')
        return card

    def test_mixed_and_three_to_six_misses_are_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            rows = [{'item': 'verb_unmapped:' + verb, 'examples': []} for verb in self.effects]
            for misses in (self.misses[:2], self.misses, self.misses * 2,
                           [('verb_unmapped:tap', 'tap')] * 4):
                with self.subTest(misses=misses):
                    parser = mock.Mock(reparse_card=lambda _: {'misses': misses})
                    args = (root, parser, rows, self.effects, {})
                    self.assertIsNone(self.m.discover_fresh_example(*args))
                    self.assertEqual(self.m.discover_fresh_example(*args, max_misses=6)[1], 'Example')

    def test_unknown_mixed_family_missing_runtime_and_over_bound_are_excluded(self):
        for misses in (self.misses + [('static_unmapped', 'static')],
                       self.misses + [('verb_unmapped:?', 'unknown')],
                       self.misses + [('verb_unmapped:mill', 'unregistered here')],
                       self.misses * 2 + [self.misses[0]], self.misses[:1]):
            self.assertEqual(self.m.eligible_shapes(misses, self.effects, max_misses=6), [])

    def test_existing_card_never_gets_fresh_budget_under_a_new_family_set(self):
        text_hash = self.m.digest_bytes(b'Oracle')
        old = 'build-plan:verb_unmapped:tap:' + text_hash
        multi = 'build-plan:multi:' + text_hash
        for state in ('queued', 'working', 'blocked', 'failed', 'parked', 'completed'):
            with self.subTest(state=state):
                history = {old: [{'state': state}]}
                self.assertIsNone(self.m.candidate_retry(history, multi, 'fresh'))
                history = {multi + ':after:ticket:engine.draw/v1': [{'state': state}]}
                self.assertIsNone(self.m.candidate_retry(history, old, 'fresh'))

    def test_multi_cursor_is_independent_and_uses_revision_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root); cache = ProducerCache(root / 'cache.db')
            scan_key = str(root.resolve()) + ':miss-count=1'
            cache.put('fresh-cursor-v1', scan_key, 'position', 'single cursor')
            parser = mock.Mock(); parser.reparse_card.return_value = {'misses': self.misses}
            args = (root, parser, [{'item': 'verb_unmapped:' + v} for v in self.effects], self.effects, {}, cache)
            self.assertIsNotNone(self.m.discover_fresh_example(*args, revision='one', max_misses=6))
            self.assertEqual(cache.get('fresh-cursor-v1', scan_key, 'position')[1], 'single cursor')
            parser.reparse_card.return_value = {'misses': []}
            self.assertIsNone(self.m.discover_fresh_example(*args, revision='two', max_misses=6))
            cache.close()

    def make_ticket(self, root, misses=None):
        self.fixture(root); tickets = root / 'tickets'; tickets.mkdir(); jobs = root / 'jobs.json'
        # Failed pilot dependencies must not occupy a permanent new-lane slot.
        for i in range(2):
            (tickets / ('pilot%d.json' % i)).write_text(json.dumps({'id': 'ticket:map.pilot%d/v1' % i,
                'production': {'producer': 'build-plan-continuous', 'miss_count': 2}}))
        jobs.write_text(json.dumps({'jobs': {'ticket:map.pilot%d/v1' % i: {'state': 'blocked'} for i in range(2)}}))
        plan = root / 'plan.jsonl'; plan.write_text(json.dumps({'item': 'verb_unmapped:draw', 'examples': []}) + '\n')
        out = io.StringIO()
        argv = ['p', '--lane', 'fresh', '--max-misses', '6', '--repo', str(root),
                '--ticket-dir', str(tickets), '--jobs', str(jobs), '--plan', str(plan)]
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(sys, 'path', list(sys.path)), \
             mock.patch.dict(sys.modules, reparse=mock.Mock(reparse_card=lambda _: {'misses': misses or self.misses})), \
             mock.patch.object(self.m, 'clean_source', return_value=True), \
             mock.patch.object(self.m, 'source_revision', return_value='a' * 40), \
             mock.patch.object(self.m, 'registry_effects', return_value=self.effects), \
             mock.patch.object(self.m, 'ProducerCache', side_effect=lambda _: ProducerCache(root / 'cache.db')), \
             contextlib.redirect_stdout(out):
            self.m.main()
        return json.loads(out.getvalue())

    def test_ticket_pins_every_clause_and_all_runtime_evidence_despite_blocked_pilot(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_ticket(Path(tmp))
            self.assertEqual(result['status'], 'ready')
            ticket, measurement = result['ticket'], result['measurement']
            self.assertEqual(ticket['production']['miss_count'], 3)
            self.assertTrue(ticket['production']['multi_miss'])
            self.assertTrue(ticket['production']['key'].startswith('build-plan:multi:'))
            self.assertEqual(len(measurement['members'][0]['misses']), 3)
            self.assertEqual(measurement['shapes'], ['verb_unmapped:damage', 'verb_unmapped:draw'])
            paths = {item['path'] for item in ticket['evidence']}
            self.assertTrue({'backend/cards/registry_damage.go', 'backend/cards/registry_draw.go'} <= paths)
            self.assertTrue(any('ANY family' in text for text in ticket['required_behavior']))
            self.assertTrue(any('zero remaining pinned members' in gate for gate in ticket['gates']))
            self.assertEqual(ticket['scope']['allowed_paths'][0], 'scripts/paragraph/reparse.py')

    def test_dependency_resume_preserves_whole_card_contract_and_current_remaining_misses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); result = self.make_ticket(root)
            parent, measurement = result['ticket'], result['measurement']
            path = next(item['path'] for item in parent['evidence'] if item['path'].endswith('.json'))
            (root / path).parent.mkdir(parents=True); (root / path).write_text(json.dumps(measurement))
            dependency = load('factory-ng-produce-capability-dependency')
            parser = mock.Mock(reparse_card=lambda _: {'eligible': False, 'misses': [('verb_unmapped:tap', 'new remaining dependency')]})
            with mock.patch.multiple(dependency, OPS=root, SOURCE=root), \
                 mock.patch.object(dependency, 'source_revision', return_value='b' * 40), \
                 mock.patch.object(dependency, 'source_evidence', return_value=[]), \
                 mock.patch.dict(sys.modules, reparse=parser):
                ticket, current = dependency.resumed_map(parent, {'id': 'ticket:engine.draw/v1'},
                                                         {'key': 'draw'}, {parent['id']: parent})
            self.assertTrue(ticket['production']['multi_miss'])
            self.assertEqual(ticket['gates'], parent['gates'])
            self.assertEqual(ticket['scope'], parent['scope'])
            self.assertTrue(set(parent['required_behavior']) <= set(ticket['required_behavior']))
            self.assertEqual(current['initial_miss_count'], 3)
            self.assertEqual(current['miss_count'], 1)
            self.assertEqual(current['members'][0]['misses'][0]['shape'], 'verb_unmapped:tap')
            (root / 'tickets/resumed.json').write_text(json.dumps(ticket))
            history = self.m.production_history(root / 'tickets', root / 'jobs.json')
            new_key = 'build-plan:verb_unmapped:tap:' + self.m.digest_bytes(b'Draw, damage, then draw again.')
            self.assertIsNone(self.m.candidate_retry(history, new_key, 'fresh'))

    def test_real_pinned_gate_rejects_partial_or_migrated_miss_and_accepts_complete_card(self):
        runner = load('factory-ng-run-map-ticket')
        remote = load('factory-ng-run-engine-ticket')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                            'commit', '--allow-empty', '-qm', 'fixture'], check=True)
            pinned = root / 'pinned.json'
            pinned.write_text(json.dumps({'schema': 'factory.targeted-demand/v1', 'shape': 'verb_unmapped:damage',
                'shapes': ['verb_unmapped:damage', 'verb_unmapped:draw'], 'multi_miss': True,
                'members': [{'name': 'Example', 'text_sha256': self.m.digest_bytes(b'Draw, damage, then draw again.') }]}))
            command = 'python3 %s --repo . --members-from %s reports zero remaining pinned members' % (
                OPS / 'scripts/factory-ng-targeted-demand.py', pinned)
            for misses, eligible, expected in ([('verb_unmapped:draw', 'draw remains')], False, 1), \
                                               ([('spell_seq_targeted', 'moved miss')], False, 1), ([], True, 0):
                with self.subTest(misses=misses):
                    (root / 'scripts/paragraph/reparse.py').write_text(
                        'from pathlib import Path\nCARDDB = Path(__file__).resolve().parents[2] / "backend/data/carddb"\n'
                        'def reparse_card(card):\n    return ' + repr({'eligible': eligible, 'misses': misses, 'abilities': []}) + '\n')
                    for gate in (runner.run_ticket_gate, remote.ticket_gate):
                        result = gate(command, root, {'work_type': 'map'})
                        self.assertEqual(result['exit_code'], expected, result)


if __name__ == '__main__':
    unittest.main()
