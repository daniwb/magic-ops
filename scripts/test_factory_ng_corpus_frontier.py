import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from factory_ng_producer_cache import ProducerCache


def load():
    spec = importlib.util.spec_from_file_location('corpus_frontier', Path(__file__).with_name('factory-ng-produce-corpus-frontier.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CorpusFrontierTests(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def test_scan_includes_nonverb_families_and_is_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = ProducerCache(root / 'cache.db')
            parser = Mock()
            parser.reparse_card.return_value = {'eligible': False, 'misses': [['kind_unsupported:modal', 'choose']]}
            cards = [('Modal', {'text': 'Choose one'})]
            try:
                first, stamp = self.m.discover(root, cards, parser, 'parser1', cache)
                second, _ = self.m.discover(root, cards, parser, 'parser1', cache)
                self.assertEqual(first, second)
                self.assertTrue(first['complete'])
                self.assertEqual(len(first['rows']), 1)
                self.assertEqual(parser.reparse_card.call_count, 1)
                self.m.discover(root, cards, parser, 'parser2', cache)
                self.assertEqual(parser.reparse_card.call_count, 2)
            finally:
                cache.close()

    def test_bounded_scan_resumes_and_isolates_parser_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = ProducerCache(root / 'cache.db')
            parser = Mock()
            parser.reparse_card.side_effect = [ValueError('bad card'), {'eligible': False, 'misses': [['static_unmapped', 'x']]}]
            cards = [('A', {}), ('B', {})]
            try:
                first, _ = self.m.discover(root, cards, parser, 's', cache, budget=0)
                self.assertFalse(first['complete'])
                second, _ = self.m.discover(root, cards, parser, 's', cache, budget=0)
                self.assertTrue(second['complete'])
                self.assertEqual(second['rows'][0]['name'], 'B')
                self.assertEqual(len(second['errors']), 1)
            finally:
                cache.close()

    def test_short_bounded_high_reuse_work_ranks_first(self):
        small = {'complexity': 1, 'misses': [['verb_unmapped:draw', 'x']], 'text_length': 20, 'name': 'A', 'same_detail_cards': 4}
        complex_ = dict(small, complexity=4)
        low_reuse = dict(small, same_detail_cards=1)
        self.assertLess(self.m.ranking(small), self.m.ranking(complex_))
        self.assertLess(self.m.ranking(small), self.m.ranking(low_reuse))

    def test_nonverb_ticket_preserves_whole_card_gates_and_dependency_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            parser = source / 'scripts/paragraph'
            parser.mkdir(parents=True)
            (parser / 'reparse.py').write_text('# source')
            (parser / 'classify.py').write_text('# source')
            row = {'name': 'Example', 'misses': [['kind_unsupported:modal', 'choose']], 'complexity': 4, 'text_length': 10}
            payload = self.m.compile_ticket(source, 'a' * 40, row, {'text': 'Choose one'}, self.m.build_plan())
            ticket = payload['ticket']
            self.assertIn('scripts/paragraph/classify.py', ticket['scope']['allowed_paths'])
            self.assertTrue(any('zero remaining pinned members' in gate for gate in ticket['gates']))
            self.assertTrue(any('NEEDS_PRIMITIVE' in behavior for behavior in ticket['required_behavior']))
            self.assertEqual(ticket['execution']['profile_policy'], 'exact')
            self.assertTrue(ticket['production']['key'].startswith('build-plan:multi:sha256:'))

    def test_completed_measurement_ownership_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tickets = root / 'tickets'; tickets.mkdir()
            measurement = root / 'docs/factory-ng/measurements/m.json'
            measurement.parent.mkdir(parents=True)
            measurement.write_text(json.dumps({'schema': 'factory.targeted-demand/v1', 'members': [{'name': 'Already done'}]}))
            (tickets / 'old.json').write_text(json.dumps({'id': 'old', 'work_type': 'map', 'evidence': [{'path': str(measurement.relative_to(root))}]}))
            cache = ProducerCache(root / 'cache.db')
            try:
                with patch.object(self.m, 'OPS', root):
                    self.assertIn('Already done', self.m.owned_members(tickets, cache))
            finally:
                cache.close()

    def test_dependency_has_engine_profiles_and_map_resume_keeps_shape_lease(self):
        spec = importlib.util.spec_from_file_location('frontier_dependency', Path(__file__).with_name('factory-ng-produce-capability-dependency.py'))
        producer = importlib.util.module_from_spec(spec); spec.loader.exec_module(producer)
        parent = {'production': {'frontier_signature': 'shape', 'ranking': [1, 1, -5, 20]},
                  'execution': {'profile_policy': 'exact', 'selected_profile': 'staged', 'compatible_profiles': ['staged']}}
        engine = {'work_type': 'engine', 'execution': {'compatible_profiles': ['engine-qualified']}}
        producer.inherit_trial(parent, engine)
        self.assertEqual(engine['execution']['compatible_profiles'], ['engine-qualified'])
        resume = {'work_type': 'map'}
        producer.inherit_trial(parent, resume)
        self.assertEqual(resume['production']['frontier_signature'], 'shape')
        self.assertEqual(resume['execution']['compatible_profiles'], ['staged'])
        parent['production']['trial_id'] = 'controlled'
        producer.inherit_trial(parent, engine)
        self.assertEqual(engine['execution']['compatible_profiles'], ['staged'])


if __name__ == '__main__':
    unittest.main()
