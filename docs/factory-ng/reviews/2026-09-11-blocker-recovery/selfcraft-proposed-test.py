import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import reparse


class TestSelfcraftMechan(unittest.TestCase):
    def test_selfcraft_mechan_maps_every_oracle_clause(self):
        result = reparse.reparse_card(reparse.load_card('Selfcraft Mechan'))

        self.assertTrue(result['eligible'])
        self.assertEqual(result['misses'], [])
        self.assertEqual(len(result['abilities']), 1)

        ability = result['abilities'][0]
        self.assertEqual(ability['type'], 'triggered')
        self.assertEqual(ability['trigger_v2'], {
            'event': 'etb',
            'subject': {'filter': 'self'},
        })
        self.assertEqual(ability['effects'], [
            {
                'effect': 'sacrifice',
                'value': {'filter': 'artifact', 'n': 1},
                'optional': True,
            },
            {
                'effect': 'put_counter_and_draw_card',
                'value': {'amount': 1, 'counter_type': '+1/+1'},
                'target': {'filter': 'creature'},
                'link': 'if_you_do',
            },
        ])

    def test_counter_plus_two_draws_preserves_both_draws(self):
        result = reparse.reparse_card({
            'name': '',
            'types': ['Creature'],
            'text': (
                'When this creature enters, put a +1/+1 counter on '
                'target creature and draw two cards.'
            ),
        })

        self.assertTrue(result['eligible'], result['misses'])
        self.assertEqual(result['abilities'][0]['effects'], [
            {'effect': 'put_counters', 'value': {'amount': 1, 'counter_type': '+1/+1'},
             'target': {'filter': 'creature'}},
            {'effect': 'draw', 'value': {'amount': 2}, 'link': 'and'},
        ])
        self.assertIsNone(reparse._put_counter_and_draw_atom(
            'put a +1/+1 counter on target creature and draw two cards.', kind='triggered'))



if __name__ == '__main__':
    unittest.main()
