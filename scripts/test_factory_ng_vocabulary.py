import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import importlib.util

from factory_ng_vocabulary import vocabulary, engine_registration_gate
from factory_ng_recovery import annotate_dependency_blockers

OPS = Path(__file__).resolve().parents[1]


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        for name in ['backend/game', 'backend/cards', 'backend/data/carddb', 'scripts/paragraph']:
            (self.repo / name).mkdir(parents=True)
        self.dispatch = self.repo / 'backend/game/ability_effects.go'
        self.dispatch.write_text('package game\nfunc ExecuteAbilityEffect() { switch effect { case "old": } }\n')
        (self.repo / 'backend/cards/registry.go').write_text(
            'package cards\nvar V2EffectRegistry = map[string]Primitive{"old": {}}\n')
        self.git('init', '-q'); self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@local', 'commit', '-qm', 'base')
        self.ticket = {'source': {'revision': self.git('rev-parse', 'HEAD').strip()}}

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True)

    def test_new_dispatch_rejects_comments_and_requires_real_registration(self):
        self.dispatch.write_text('''package game
func ExecuteAbilityEffect() {
 switch effect { case "old", "new": switch unrelated { case "internal": } }
}
func unrelated() { switch effect { case "not_public": } }
''')
        p = self.repo / 'backend/cards/registry_new.go'
        p.write_text('package cards\n// regEffect("new", Primitive{})\n')
        gate = engine_registration_gate(self.ticket, self.repo)
        self.assertEqual(gate['outcome'], 'failed')
        self.assertIn('new', gate['detail'])
        self.assertNotIn('internal', gate['detail'])
        p.write_text('package cards\nfunc init() { regEffect("new", Primitive{}) }\n')
        self.assertEqual(engine_registration_gate(self.ticket, self.repo)['outcome'], 'passed')

    def test_existing_init_assignments_are_observed(self):
        (self.repo / 'backend/cards/registry_old.go').write_text(
            'package cards\nfunc init() { V2EffectRegistry["assigned"] = Primitive{} }\n')
        self.assertIn('assigned', vocabulary(self.repo)['registered'])

    def test_early_dispatch_cannot_hide_an_unregistered_effect(self):
        self.dispatch.write_text('package game\nfunc ExecuteAbilityEffect() { if effect == "early" { return }; switch effect { case "old": } }\n')
        (self.repo / 'backend/cards/registry_new.go').write_text(
            'package cards\nfunc unused() { regEffect("early", Primitive{}) }\n')
        gate = engine_registration_gate(self.ticket, self.repo)
        self.assertEqual(gate['outcome'], 'failed')
        self.assertIn('early', gate['detail'])

    def test_pinned_map_rejects_fabricated_parser_registry(self):
        card = {'status': 'review', 'text': 'Example'}
        (self.repo / 'backend/data/carddb/t.json').write_text(json.dumps({'Test': card}))
        (self.repo / 'scripts/paragraph/reparse.py').write_text(
            'from pathlib import Path\nCARDDB = Path(__file__).resolve().parents[2] / "backend/data/carddb"\n'
            'REGISTERED = {"fabricated"}\n'
            'def reparse_card(card):\n return {"eligible": True, "misses": [], '
            '"abilities": [{"effects": [{"effect": "fabricated"}]}]}\n')
        pinned = self.repo / 'pinned.json'
        pinned.write_text(json.dumps({'schema': 'factory.targeted-demand/v1', 'shape': 'verb_unmapped:test',
            'members': [{'name': 'Test', 'text_sha256': 'sha256:' + hashlib.sha256(b'Example').hexdigest()}]}))
        result = subprocess.run([sys.executable, str(OPS / 'scripts/factory-ng-targeted-demand.py'),
            '--repo', str(self.repo), '--members-from', str(pinned)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('emits unregistered effects: fabricated', result.stderr)


class DependencyTests(unittest.TestCase):
    def test_failed_profile_cannot_fill_runnable_reserve(self):
        spec = importlib.util.spec_from_file_location('vocab_controller', OPS / 'scripts/factory-ng-controller.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        worker = {'id': 'claude', 'profile': 'claude-staged@1.0.0', 'routing_mode': 'auto'}
        job = {'ticket_id': 'sigil', 'state': 'queued', 'work_type': 'engine',
               'compatible_profiles': ['claude-staged@1.0.0'],
               'failed_profiles': ['claude-staged@1.0.0']}
        inventory = controller.queue_inventory({'jobs': {'sigil': job}},
            {'claude-staged@1.0.0': [worker]}, {'claude-staged@1.0.0': {'claude': {'allowed': True}}})
        self.assertEqual(inventory['runnable'], [])
        self.assertEqual(inventory['deferred'], ['sigil'])

    def test_failed_successor_is_not_reported_as_running_and_history_survives(self):
        tickets = {'e1': {'work_type': 'engine', 'parents': ['m']},
                   'e2': {'work_type': 'engine', 'parents': ['e1']}}
        jobs = {'m': {'state': 'blocked', 'attempts': 2},
                'e1': {'state': 'failed', 'superseded_by': 'e2'},
                'e2': {'state': 'failed', 'receipt': 'immutable.json'}}
        annotate_dependency_blockers(jobs, tickets)
        self.assertEqual(jobs['m']['dependency_blocker']['children'], {'e2': 'failed'})
        self.assertIn('no active successor', jobs['m']['waiting_reason'])
        self.assertEqual(jobs['m']['attempts'], 2)
        jobs['e2']['state'] = 'working'
        annotate_dependency_blockers(jobs, tickets)
        self.assertIn('running', jobs['m']['waiting_reason'])
        jobs['m']['state'] = 'completed'
        annotate_dependency_blockers(jobs, tickets)
        self.assertNotIn('waiting_reason', jobs['m'])


if __name__ == '__main__':
    unittest.main()
