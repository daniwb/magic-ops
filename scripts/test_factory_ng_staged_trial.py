#!/usr/bin/env python3
"""Guard routing, cohort lineage, accounting and full-card completion claims."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

OPS = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, OPS / 'scripts' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class StagedTrialTest(unittest.TestCase):
    def test_verification_evidence_refresh_preserves_scope_and_is_single_use(self):
        trial = module('trial_context_successor_test', 'factory-ng-staged-trial.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').symlink_to(OPS / 'scripts', target_is_directory=True)
            ticket = {'id': 'ticket:engine.verify/v1', 'title': 'Verify', 'parents': [],
                      'work_type': 'engine', 'evidence': [], 'required_behavior': ['Every ability.'],
                      'scope': {'allowed_paths': ['backend/cards/proof_test.go']}, 'gates': ['all gates'],
                      'production': {'trial_phase': 'verification', 'key': 'trial:verify:card'},
                      'execution': {'profile_policy': 'exact', 'compatible_profiles': [trial.PROFILE]}}
            (root / 'ticket.json').write_text(json.dumps(ticket))
            receipt = {'ticket': {'id': ticket['id'], 'sha256': trial.sha(root / 'ticket.json')},
                       'model': {'profile': trial.PROFILE}, 'evidence_failure': {'question': 'Missing API'}}
            (root / 'receipt.json').write_text(json.dumps(receipt))
            job = {'state': 'parked', 'outcome': 'parked', 'receipt': 'receipt.json', 'ticket_path': 'ticket.json'}
            with mock.patch.object(trial, 'OPS', root), mock.patch.object(trial.subprocess, 'check_output', return_value='a' * 40):
                successor = trial.verification_context_successor(ticket, job, {ticket['id']: ticket})
                self.assertIsNotNone(successor)
                for key in ('scope', 'gates', 'required_behavior'):
                    self.assertEqual(ticket[key], successor[key])
                self.assertEqual(successor['execution']['compatible_profiles'], [trial.PROFILE])
                self.assertEqual(successor['execution']['profile_policy'], 'exact')
                self.assertIsNone(trial.verification_context_successor(ticket, job,
                                  {ticket['id']: ticket, successor['id']: successor}))
                receipt['ticket']['sha256'] = 'wrong'
                (root / 'receipt.json').write_text(json.dumps(receipt))
                self.assertIsNone(trial.verification_context_successor(ticket, job, {ticket['id']: ticket}))

    def test_exact_profile_dispatch_never_falls_back_to_agentic(self):
        c = module('trial_controller', 'factory-ng-controller.py')
        staged, agentic = 'claude-staged@1.0.0', 'claude-agentic@1.0.0'
        ticket = {'work_type': 'map', 'execution': {'compatible_profiles': [staged], 'profile_policy': 'exact'}}
        profiles = c.compatible_profiles_for(ticket, staged)
        self.assertEqual(profiles, [staged])
        workers = c.configured_workers_by_profile([{'id': 'agentic', 'enabled': True, 'profile': agentic, 'routing_mode': 'auto'}])
        jobs = {'jobs': {'trial': {'state': 'queued', 'ticket_id': 'trial', 'profile': staged,
                                 'compatible_profiles': profiles, 'work_type': 'map'}}}
        self.assertEqual(c.next_dispatch(jobs, workers, {agentic: {'agentic': {'allowed': True}}}), [])
        ticket['execution']['compatible_profiles'] = []
        self.assertNotIn(staged, c.compatible_profiles_for(ticket, staged))
        ticket['execution'].pop('profile_policy')
        ticket['execution']['compatible_profiles'] = [staged]
        self.assertNotIn(agentic, c.compatible_profiles_for(ticket, staged))

    def test_dependency_preserves_trial_identity_and_exact_route(self):
        d = module('trial_dependency_test', 'factory-ng-produce-capability-dependency.py')
        parent = {'production': {'trial_id': 'five', 'trial_card': 'Card'},
                  'execution': {'profile_policy': 'exact', 'selected_profile': 'claude-staged@1.0.0',
                                'compatible_profiles': ['claude-staged@1.0.0']}}
        child = {'production': {'producer': 'capability-dependencies'}, 'execution': {'selected_profile': 'other'}}
        d.inherit_trial(parent, child)
        self.assertEqual(child['production']['trial_card'], 'Card')
        self.assertEqual(child['production']['producer'], 'capability-dependencies')
        self.assertEqual(child['execution'], parent['execution'])

    def test_trial_map_route_does_not_promote_ordinary_maps(self):
        c = module('trial_worker_test', 'factory-ng-controller.py')
        worker = {'profile': 'claude-staged@1.0.0', 'routing_mode': 'auto', 'map_trial_only': 'five'}
        self.assertFalse(c.worker_supports_job(worker, {'work_type': 'map'}))
        self.assertTrue(c.worker_supports_job(worker, {'work_type': 'map', 'production': {'trial_id': 'five'}}))
        self.assertTrue(c.worker_supports_job(worker, {'work_type': 'engine'}))

    def test_report_counts_failed_attempts_and_requires_integrated_verification(self):
        trial = module('trial_report_test', 'factory-ng-staged-trial.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / 'docs/factory-ng/runs'; runs.mkdir(parents=True)
            for n, outcome in enumerate(['gate_failed', 'accepted_for_dependent_observation']):
                r = {'schema': 'factory.observation-receipt/v1', 'ticket': {'id': 'map'}, 'outcome': outcome,
                     'model': {'profile': trial.PROFILE, 'telemetry': dict(zip(trial.COUNTERS, [1, 2, 3, 4]))}}
                (runs / (str(n) + '.json')).write_text(json.dumps(r))
            r['model']['telemetry'].pop('input_tokens')
            (runs / 'unknown.json').write_text(json.dumps(r))
            manifest = {'id': 'five', 'cards': [{'name': 'Card', 'baseline_tickets': []}]}
            tickets = {k: {'production': {'trial_id': 'five', 'trial_card': 'Card', 'trial_phase': phase}}
                       for k, phase in [('map', 'mapping'), ('verify', 'verification')]}
            with mock.patch.object(trial, 'OPS', root), mock.patch.object(trial, 'DIRECTORY', root):
                report = trial.report(manifest, tickets, {'map': {'state': 'completed'}, 'verify': {'state': 'awaiting_integration'}})
                card = report['cards'][0]
                self.assertFalse(card['complete'])
                self.assertEqual(card['trial_known_raw_claude_tokens'], 20)
                self.assertEqual(card['trial_unknown_or_non_claude_attempts'], 1)
                report = trial.report(manifest, tickets, {'verify': {'state': 'completed'}})
                self.assertFalse(report['cards'][0]['complete'])
                report = trial.report(manifest, tickets, {'verify': {'state': 'completed', 'integration_receipt': 'full-gate.json'}})
                self.assertTrue(report['cards'][0]['complete'])

    def test_verification_has_fresh_card_obligation_and_test_only_scope(self):
        trial = module('trial_verifier_test', 'factory-ng-staged-trial.py')
        manifest = trial.read(trial.MANIFEST)
        card = manifest['cards'][0]
        parent = {'id': 'map', 'execution': {'parser_probes': [{'card': card['name']}]}}
        with mock.patch.object(trial.subprocess, 'check_output', return_value='a' * 40):
            ticket = trial.verification(card, manifest, parent)['ticket']
        self.assertEqual(ticket['scope']['allowed_paths'], ['backend/cards/shape_staged_trial_siegfried_test.go'])
        self.assertIn('reparse_card', ticket['required_behavior'][0])
        self.assertNotIn('parser_probes', ticket['execution'])
        self.assertEqual(ticket['execution']['compatible_profiles'], [trial.PROFILE])
        self.assertIn("'^TestShape_StagedTrial_siegfried$'", ticket['gates'][0])
        self.assertTrue(all(item in ticket['required_behavior'] for item in card['acceptance']))

    def test_all_producer_paths_honor_two_job_trial_reserve(self):
        c = module('trial_admission_test', 'factory-ng-controller.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for n in range(2):
                (root / (str(n) + '.json')).write_text(json.dumps({'id': str(n), 'production': {'trial_id': 'five'}}))
            candidate = {'id': 'ticket:trial.third/v1', 'production': {'trial_id': 'five'}}
            with mock.patch.object(c, 'TICKETS', root), mock.patch.object(c, 'load_jobs', return_value={'jobs': {'0': {'state': 'working'}, '1': {'state': 'integrating'}}}):
                self.assertEqual(c.persist_ready({'ticket': candidate}), ('trial_reserve_full', candidate['id']))
                self.assertEqual(len(list(root.glob('*.json'))), 2)

    def test_busy_staged_worker_is_not_reported_as_usage_paused(self):
        c = module('trial_busy_worker_test', 'factory-ng-controller.py')
        profile = 'claude-staged@1.0.0'
        worker = {'id': 'secondary', 'profile': profile, 'enabled': True, 'routing_mode': 'auto'}
        queued = {'ticket_id': 'queued', 'state': 'queued', 'profile': profile, 'work_type': 'map'}
        jobs = {'jobs': {'queued': queued, 'busy': {'state': 'working', 'worker': 'secondary'}}}
        self.assertEqual(c.next_dispatch(jobs, c.configured_workers_by_profile([worker]),
                                        {profile: {'secondary': {'allowed': True}}}), [])
        self.assertIn('busy', queued['waiting_reason'])


if __name__ == '__main__':
    unittest.main()
