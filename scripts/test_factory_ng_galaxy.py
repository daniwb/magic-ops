"""Galaxy refreshes update job state without recomputing unchanged geometry."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


class GalaxyTest(unittest.TestCase):
    def test_reuses_geometry_but_refreshes_state_and_detects_edge_changes(self):
        spec = importlib.util.spec_from_file_location('galaxy', Path(__file__).with_name('factory-ng-galaxy-snapshot.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        nodes = {'hub': {'id': 'hub', 'kind': 'hub', 'label': 'hub'},
                 'ticket': {'id': 'ticket', 'kind': 'ticket', 'label': 'ticket', 'state': 'working'}}
        edges = [{'a': 'ticket', 'b': 'hub', 'kind': 'cluster'}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(m, 'extract_graph', return_value=(nodes, edges)):
            m.OUT = Path(d) / 'prior.json'
            with mock.patch.object(m, 'layout', wraps=m.layout) as layout:
                first = m.build(5)
                self.assertEqual(layout.call_args.args[-1], 5)
                m.OUT.write_text(json.dumps(first))
                nodes['ticket']['state'] = 'completed'
                second = m.build(5)
                self.assertEqual(layout.call_args.args[-1], 0)
                self.assertEqual([(n['x'], n['y']) for n in first['nodes']],
                                 [(n['x'], n['y']) for n in second['nodes']])
                self.assertEqual(second['nodes'][1]['s'], 'completed')
                edges[0]['kind'] = 'dependency'
                third = m.build(5)
                self.assertEqual(layout.call_args.args[-1], 3)
                self.assertNotEqual(first['topology'], third['topology'])


if __name__ == '__main__':
    unittest.main()
