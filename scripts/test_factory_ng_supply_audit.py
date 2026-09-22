"""Supply measurement must expose unsupported work without granting retries."""
import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    'supply_audit', Path(__file__).with_name('factory-ng-supply-audit.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class SupplyAuditTests(unittest.TestCase):
    def setUp(self):
        self.producer = audit.load_producer()
        self.effects = {'draw': {}}

    def classify(self, result, history=None, text='Oracle'):
        return audit.classify(result, self.effects, {} if history is None else history, self.producer,
                              self.producer.digest_bytes(text.encode()), 6)

    def test_unsupported_work_is_visible_but_not_dispatchable(self):
        self.assertEqual(self.classify({'misses': [('kind_unmapped:replacement', 'x')]}),
                         'needs_preparation')
        self.assertEqual(self.classify({'misses': [('verb_unmapped:draw', 'x'),
                                                  ('kind_unmapped:replacement', 'y')]}),
                         'needs_preparation')

    def test_known_work_does_not_get_new_attempt_from_audit(self):
        key = 'build-plan:verb_unmapped:draw:' + self.producer.digest_bytes(b'Oracle')
        result = {'misses': [('verb_unmapped:draw', 'x')]}
        self.assertEqual(self.classify(result), 'fresh_supported_candidate')
        self.assertEqual(self.classify(result, {key: [{'state': 'failed'}]}), 'existing_lineage')

    def test_eligible_requires_explicit_parser_evidence(self):
        self.assertEqual(self.classify({'misses': [], 'eligible': True}), 'remeasure_import')
        self.assertEqual(self.classify({'misses': [], 'eligible': False}), 'unexplained_ineligible')

    def test_card_failure_does_not_hide_other_frontiers(self):
        cards = [(name, {'text': name}) for name in ('A', 'B', 'C')]
        def parse(name, card):
            if name == 'A':
                raise ValueError('broken parser case')
            return {'misses': [('new_family', name), ('verb_unmapped:draw', 'x')]}
        report = audit.census(cards, parse, self.effects, {}, self.producer)
        self.assertEqual(report['review_cards'], 3)
        self.assertEqual(report['dispositions'], {'measurement_error': 1, 'needs_preparation': 2})
        self.assertEqual(report['measurement_errors'][0]['card'], 'A')
        self.assertEqual(len(report['discovery_groups']), 1)
        self.assertTrue(all(row['sole_blocker_cards'] == 0 for row in report['families']))

    def test_family_counts_are_per_card_and_groups_are_stable(self):
        cards = [('A', {'text': 'A'})]
        def parse(name, card):
            return {'misses': [('new_family', 'first'), ('new_family', 'second')]}
        one = audit.census(cards, parse, self.effects, {}, self.producer)
        two = audit.census(cards, parse, self.effects, {}, self.producer)
        self.assertEqual(one, two)
        self.assertEqual(one['families'][0]['cards'], 1)
        self.assertEqual(one['families'][0]['sole_blocker_cards'], 1)

    def test_widening_scope_does_not_bypass_multi_card_ownership(self):
        history = self.producer.ProductionHistory()
        history.multi_text_hashes.add(self.producer.digest_bytes(b'Oracle'))
        self.assertEqual(self.classify({'misses': [('verb_unmapped:draw', 'x')]}, history),
                         'existing_lineage')


if __name__ == '__main__':
    unittest.main()
