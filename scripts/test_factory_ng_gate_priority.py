"""Regression coverage for accepted work starved by isolated verification."""
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock


class GatePriorityTests(unittest.TestCase):
    def test_two_local_slots_count_processes_not_batch_members(self):
        self.settings['verification'].update(overlap_integration=True, local_slots=2)
        jobs={'jobs':{'a':{'state':'working','verification_resume':True,'pid':10},
                      'b':{'state':'working','verification_resume':True,'pid':10}}}
        self.assertFalse(self.m.verification_slot_busy(jobs))
        jobs['jobs']['c']={'state':'working','verification_resume':True,'pid':20}
        self.assertTrue(self.m.verification_slot_busy(jobs))
        jobs['jobs']['c']['verification_host']='ryzen-395-1'
        self.assertFalse(self.m.verification_slot_busy(jobs))
        self.assertTrue(self.m.verification_slot_busy(jobs,'ryzen-395-1'))

    def setUp(self):
        path = Path(__file__).with_name('factory-ng-controller.py')
        spec = importlib.util.spec_from_file_location('controller_gate_priority', path)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.settings = {'compilation': {'enabled': True},
                         'integration': {'automatic': True, 'collect_seconds': 0},
                         'verification': {'batch_size': 8}}
        self.worker = {'id': 'w', 'profile': 'p', 'model': 'm', 'routing_mode': 'auto'}
        self.pending = {'ticket_id': 'pending', 'ticket_path': 'pending.json',
                        'state': 'awaiting_verification', 'verification_isolate': True,
                        'worker': 'w', 'dispatch_profile': 'p', 'profile': 'p',
                        'work_type': 'map', 'proposal': 'proposal.json'}
        self.accepted = {'ticket_id': 'accepted', 'state': 'awaiting_integration',
                         'receipt': 'receipt.json', 'work_type': 'map'}
        self.jobs = {'jobs': {'pending': self.pending, 'accepted': self.accepted}}
        self.availability = {'p': {'w': {'allowed': True}}}
        self.enterContext(mock.patch.object(self.m, 'policy', return_value=self.settings))
        self.enterContext(mock.patch.object(self.m, 'worker_supports_job', return_value=True))

    def select(self):
        return self.m.next_dispatch(self.jobs, {'p': [self.worker]}, self.availability)

    def test_collection_reserves_gate_but_drafting_continues(self):
        fresh = {'ticket_id': 'fresh', 'ticket_path': 'fresh.json', 'state': 'queued',
                 'profile': 'p', 'work_type': 'map'}
        self.jobs['jobs']['fresh'] = fresh
        self.assertEqual([job['ticket_id'] for _, job, _ in self.select()], ['fresh'])
        self.assertEqual(self.pending['state'], 'awaiting_verification')

    def test_ineligible_acceptances_do_not_starve_verification(self):
        for change in ({'superseded_by': 'replacement'}, {'receipt': None},
                       {'integration_retry_after_epoch': int(time.time()) + 300}):
            with self.subTest(change=change), mock.patch.dict(self.accepted, change):
                self.assertEqual([job['ticket_id'] for _, job, _ in self.select()], ['pending'])
        self.settings['integration']['automatic'] = False
        self.assertEqual([job['ticket_id'] for _, job, _ in self.select()], ['pending'])

    def test_dispatch_admits_integration_before_isolated_resume(self):
        m = self.m
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(m, 'OPS', Path(tmp)), \
             mock.patch.object(m, 'sync_jobs', return_value=(self.jobs, {'p': [self.worker]})), \
             mock.patch.object(m, 'reconcile_running'), \
             mock.patch.object(m, 'source_problem', return_value=None), \
             mock.patch.object(m, 'job_files', return_value=(Path(tmp)/'out', Path(tmp)/'err')), \
             mock.patch.object(m, 'save_jobs'), mock.patch.object(m, 'log'), \
             mock.patch.object(m.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 123
            m.dispatch_one([], [], self.availability)
        self.assertEqual(spawn.call_count, 1)
        self.assertTrue(any(str(arg).endswith('factory-ng-integrate.py')
                            for arg in spawn.call_args.args[0]))
        self.assertEqual(self.accepted['state'], 'integrating')
        self.assertEqual(self.pending['state'], 'awaiting_verification')

    def test_overlap_allows_one_isolated_verifier_with_integration(self):
        self.settings['verification']['overlap_integration'] = True
        self.accepted['state'] = 'integrating'
        self.assertEqual([job['ticket_id'] for _, job, _ in self.select()], ['pending'])
        self.jobs['jobs']['running-verifier'] = {
            'state': 'working', 'verification_resume': True, 'worker': 'other'}
        self.assertEqual(self.select(), [])
        del self.jobs['jobs']['running-verifier']
        self.settings['verification']['overlap_integration'] = False
        self.assertEqual(self.select(), [])

    def test_overlap_never_admits_two_integrations(self):
        self.settings['verification']['overlap_integration'] = True
        self.pending.update(state='working', verification_resume=True)
        m = self.m
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(m, 'OPS', Path(tmp)), \
             mock.patch.object(m, 'source_problem', return_value=None), \
             mock.patch.object(m, 'job_files', return_value=(Path(tmp)/'out', Path(tmp)/'err')), \
             mock.patch.object(m, 'save_jobs'), mock.patch.object(m, 'log'), \
             mock.patch.object(m.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 123
            m.dispatch_integration(self.jobs, [])
            self.assertEqual(self.accepted['state'], 'integrating')
            self.jobs['jobs']['another'] = {**self.accepted, 'state': 'awaiting_integration'}
            m.dispatch_integration(self.jobs, [])
            spawn.assert_called_once()

    def test_overlap_respects_manual_switch(self):
        self.settings['verification']['overlap_integration'] = True
        self.settings['compilation']['enabled'] = False
        with mock.patch.object(self.m.subprocess, 'Popen') as spawn:
            self.assertEqual(self.select(), [])
            self.m.dispatch_verification_batch(self.jobs, [])
            self.m.dispatch_integration(self.jobs, [])
            spawn.assert_not_called()

    def test_four_proven_repairs_use_model_leases_while_local_slots_are_full(self):
        self.settings['verification'].update(overlap_integration=True, local_slots=2)
        workers = [{**self.worker, 'id': 'w' + str(i)} for i in range(4)]
        jobs = {'jobs': {str(i): {**self.pending, 'ticket_id': str(i), 'worker': w['id']}
                         for i, w in enumerate(workers)}}
        jobs['jobs'].update({str(i): {'state': 'working', 'verification_resume': True,
                                    'worker': 'local' + str(i), 'pid': i} for i in (10, 11)})
        jobs['jobs']['duplicate'] = {**jobs['jobs']['0'], 'ticket_id': 'duplicate'}
        availability = {'p': {w['id']: {'allowed': True} for w in workers}}
        self.assertTrue(self.m.verification_slot_busy(jobs))
        with mock.patch.object(self.m, 'repair_only_ready', return_value=True):
            selected = self.m.next_dispatch(jobs, {'p': workers}, availability)
        self.assertEqual(len(selected), 4)
        self.assertEqual(len({w['id'] for _, _, w in selected}), 4)
        self.assertTrue(all(j['verification_repair_only'] for _, j, _ in selected))
        with mock.patch.object(self.m, 'repair_only_ready', return_value=False):
            self.assertEqual(self.m.next_dispatch(jobs, {'p': workers}, availability), [])
        # Model-only corrections do not consume either local compilation slot.
        jobs['jobs']['10']['verification_host'] = 'model-repair'
        self.assertFalse(self.m.verification_slot_busy(jobs))

    def test_dispatch_repair_only_uses_guarded_runner_and_model_host(self):
        m = self.m
        profile = 'codex-constrained@1.1.0'
        self.worker['profile'] = profile
        self.pending.update(profile=profile, dispatch_profile=profile, model='m',
                            verification_remote_failed=True, result_path='prior.json')
        self.settings['verification']['remote'] = {'enabled': True, 'id': 'remote'}
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(m, 'OPS', Path(tmp)), \
             mock.patch.object(m, 'sync_jobs', return_value=(self.jobs, {profile: [self.worker]})), \
             mock.patch.object(m, 'reconcile_running'), \
             mock.patch.object(m, 'source_problem', return_value=None), \
             mock.patch.object(m, 'dispatch_integration'), \
             mock.patch.object(m, 'dispatch_verification_batch'), \
             mock.patch.object(m.attention_recovery, 'admit'), \
             mock.patch.object(m, 'repair_only_ready', return_value=True), \
             mock.patch.object(m, 'job_files', return_value=(Path(tmp)/'out', Path(tmp)/'err')), \
             mock.patch.object(m, 'save_jobs'), mock.patch.object(m, 'log'), \
             mock.patch.object(m.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 123
            m.dispatch_one([], [], {profile: {'w': {'allowed': True}}})
        command = spawn.call_args.args[0]
        for arg in ('--repair-only', '--repair-evidence', '--resume-proposal', '--defer-repaired-verification'):
            self.assertIn(arg, command)
        self.assertEqual(self.pending['verification_host'], 'model-repair')
        self.assertTrue(self.pending['verification_resume'])


if __name__ == '__main__':
    unittest.main()
