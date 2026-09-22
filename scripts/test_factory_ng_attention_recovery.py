import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import factory_ng_attention_recovery as recovery
from factory_ng_provider_failure import codex_capacity_failure, CAPACITY_EXIT


class AttentionRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'ticket.json').write_text('{}')
        (self.root / 'failure.json').write_text('{"outcome":"infrastructure_failed"}')
        self.job = dict(ticket_id='ticket:test/v1', ticket_path='ticket.json',
                        state='failed', outcome='infrastructure_failed', attempts=3,
                        receipt='failure.json', started_at='before',
                        compatible_profiles=['current'], failed_profiles=['current'])
        self.item = dict(ticket_id='ticket:test/v1', attempts=3, receipt='failure.json',
                         started_at='before', ticket_sha256=recovery.digest(self.root/'ticket.json'),
                         evidence_path='failure.json', evidence_sha256=recovery.digest(self.root/'failure.json'),
                         reason='Reviewed repaired startup', profiles=['current'])
        self.manifest = dict(schema='factory.reviewed-attention-recovery/v1', batch='test',
                             max_active=6, tickets=[self.item])

    def admit(self, jobs=None, **kwargs):
        path = self.root / recovery.MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest))
        return recovery.admit(self.root, jobs or {'ticket:test/v1': self.job}, 'now', **kwargs)

    def test_one_supplemental_attempt_preserves_history(self):
        self.assertEqual(self.admit(), 1)
        self.assertEqual(self.job['attempts'], 3)
        self.assertEqual(self.job['failed_profiles'], ['current'])
        self.assertEqual(recovery.failed_profiles(self.job), set())
        self.assertEqual(recovery.profiles(self.job, ['current', 'other']), ['current'])
        self.assertEqual(recovery.attempt_limit(self.job, 3), 4)
        self.job.update(state='failed', attempts=4)
        self.assertEqual(self.admit(), 0)
        self.assertEqual(recovery.failed_profiles(self.job), {'current'})
        self.assertEqual(recovery.profiles(self.job, ['current', 'other']), ['current', 'other'])
        self.assertEqual(recovery.attempt_limit(self.job, 3), 4)
        self.assertEqual((self.root/'failure.json').read_text(), '{"outcome":"infrastructure_failed"}')

    def test_never_reopens_semantic_active_superseded_or_changed_jobs(self):
        for change in ({'state':'working'}, {'state':'integration_failed'},
                       {'state':'completed'}, {'state':'parked'},
                       {'superseded_by':'next'}, {'outcome':'gate_failed'},
                       {'attempts':4}, {'receipt':'new.json'}, {'started_at':'later'},
                       {'compatible_profiles':['different']}):
            with self.subTest(change=change):
                original = copy.deepcopy(self.job)
                self.job.update(change)
                self.assertEqual(self.admit(), 0)
                self.job = original

    def test_tampered_evidence_and_contract_fail_closed(self):
        for filename in ('failure.json', 'ticket.json'):
            path = self.root / filename
            before = path.read_bytes()
            path.write_text('changed')
            self.assertEqual(self.admit(), 0)
            path.write_bytes(before)

    def test_deferred_protocol_recovery_requires_explicit_review_and_failed_profile(self):
        self.job.update(state='queued', outcome='infrastructure_failed_model_protocol')
        self.assertEqual(self.admit(), 0)
        self.item['reviewed_state'] = 'queued'
        self.job['failed_profiles'] = []
        self.assertEqual(self.admit(), 0)
        self.job['failed_profiles'] = ['current']
        self.assertEqual(self.admit(), 1)
        self.assertEqual(self.job['attempts'], 3)
        self.assertEqual(self.job['failed_profiles'], ['current'])
        self.assertEqual(self.admit(), 0)

    def test_review_cannot_authorize_active_or_semantic_recovery(self):
        for state, outcome in [('working', 'infrastructure_failed_model_protocol'),
                               ('queued', 'gate_failed'), ('queued', 'infrastructure_failed')]:
            with self.subTest(state=state, outcome=outcome):
                self.item['reviewed_state'] = state
                self.job.update(state=state, outcome=outcome)
                self.assertEqual(self.admit(), 0)

    def test_capacity_followup_requires_new_bound_review_and_keeps_history(self):
        self.assertEqual(self.admit(), 1)
        prior = copy.deepcopy(self.job['attention_recovery'])
        self.job.update(state='failed', attempts=4, receipt='capacity.json', started_at='new',
                        model='old-model', outcome='infrastructure_failed_provider_capacity')
        (self.root/'capacity.json').write_text('{"error":"capacity"}')
        self.item.update(attempts=4, receipt='capacity.json', started_at='new',
                         evidence_path='capacity.json', evidence_sha256=recovery.digest(self.root/'capacity.json'))
        self.assertEqual(self.admit(), 0)
        self.item.update(prior_recovery_sha256=recovery.review_digest(prior),
                         required_model='old-model', reviewed_outcome=self.job['outcome'])
        self.assertEqual(self.admit(), 0)
        self.item['required_model'] = 'fallback'
        self.assertEqual(self.admit(), 1)
        self.assertEqual(self.job['attention_recovery_history'], [prior])
        self.assertEqual(self.job['attempts'], 4)
        self.assertEqual(recovery.attempt_limit(self.job, 3), 5)
        self.assertEqual(self.admit(), 0)
        self.job.update(state='failed', attempts=5)
        self.assertEqual(self.admit(), 0)

    def test_reviewed_saved_proposal_can_finish_on_its_original_profile(self):
        self.assertEqual(self.admit(), 1)
        self.job.update(state='awaiting_verification', attempts=4,
                        proposal='saved.json', dispatch_profile='current')
        self.assertEqual(recovery.failed_profiles(self.job), set())
        self.assertEqual(self.job['failed_profiles'], ['current'])
        for change in ({'state': 'queued'}, {'state': 'failed'}, {'attempts': 5},
                       {'proposal': None}, {'dispatch_profile': 'other'}):
            with self.subTest(change=change):
                changed = dict(self.job, **change)
                self.assertEqual(recovery.failed_profiles(changed), {'current'})

    def test_controller_dispatches_reviewed_verification_without_new_draft_allowance(self):
        path = Path(__file__).with_name('factory-ng-controller.py')
        spec = importlib.util.spec_from_file_location('reviewed_verification_controller', path)
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        self.admit()
        self.job.update(state='awaiting_verification', attempts=4, work_type='engine',
                        proposal='saved.json', dispatch_profile='current', worker='owner',
                        verification_isolate=True)
        worker = {'id': 'owner', 'profile': 'current', 'model': 'configured-model'}
        settings = {'compilation': {'enabled': True}, 'verification': {
            'batch_size': 8, 'local_slots': 2, 'overlap_integration': True}}
        with patch.object(controller, 'policy', return_value=settings), \
             patch.object(controller, 'worker_supports', return_value=True):
            args = ({'jobs': {'ticket:test/v1': self.job}}, {'current': [worker]},
                    {'current': {'owner': {'allowed': True}}})
            self.assertEqual(len(controller.next_dispatch(*args)), 1)
            self.assertEqual(self.job['attempts'], 4)
            self.job['state'] = 'queued'
            self.assertEqual(controller.next_dispatch(*args), [])

    def test_queue_and_batch_capacity(self):
        jobs = {'ticket:test/v1': self.job}
        jobs.update({str(i): {'state':'queued'} for i in range(12)})
        self.assertEqual(self.admit(jobs), 0)

    def test_review_does_not_grant_unused_ordinary_attempts(self):
        job = {'attention_recovery': {'previous_attempts': 1}}
        self.assertEqual(recovery.attempt_limit(job, 3), 2)
        jobs = {'ticket:test/v1': self.job}
        jobs.update({str(i): {'state':'awaiting_verification', 'attention_recovery':{'batch':'test'}} for i in range(6)})
        self.assertEqual(self.admit(jobs), 0)

    def test_deferred_inventory_does_not_block_reviewed_recovery(self):
        jobs = {'ticket:test/v1': self.job}
        jobs.update({str(i): {'state':'queued'} for i in range(100)})
        self.assertEqual(self.admit(jobs, runnable_count=11), 1)

    def test_review_dependencies_share_the_six_active_limit(self):
        jobs = {'ticket:test/v1': self.job}
        jobs.update({str(i): {'state': 'working', 'production': {
            'attention_recovery_parent': 'ticket:test/v1'}} for i in range(6)})
        self.assertEqual(self.admit(jobs), 0)
        jobs['0']['state'] = 'completed'
        self.assertEqual(self.admit(jobs), 1)

    def test_blocked_review_reserves_one_producer_slot(self):
        jobs = {'ticket:test/v1': self.job,
                'blocked': {'state': 'blocked', 'attention_recovery': {'batch': 'test'}}}
        jobs.update({str(i): {'state': 'working', 'attention_recovery': {'batch': 'test'}} for i in range(5)})
        self.assertEqual(self.admit(jobs), 0)
        jobs['0']['state'] = 'completed'
        self.assertEqual(self.admit(jobs), 1)

    def test_dependency_production_waits_for_a_review_slot(self):
        jobs = {'ticket:test/v1': self.job}
        self.admit(jobs)
        jobs.update({str(i): {'state': 'working', 'production': {
            'attention_recovery_parent': 'ticket:test/v1'}} for i in range(5)})
        payload = {'ticket_id': 'child', 'ticket': {'production': {
            'attention_recovery_parent': 'ticket:test/v1'}}}
        self.assertFalse(recovery.dependency_admission(self.root, jobs, payload))
        jobs['0']['state'] = 'completed'
        self.assertTrue(recovery.dependency_admission(self.root, jobs, payload))
        payload['ticket']['production']['attention_recovery_parent'] = 'unreviewed'
        self.assertFalse(recovery.dependency_admission(self.root, jobs, payload))
        self.assertTrue(recovery.dependency_admission(self.root, jobs, {'ticket': {}}))

    def test_only_current_blocked_review_receipts_receive_priority(self):
        jobs = {
            'review': {'state': 'blocked', 'attention_recovery': {'batch': 'test'}, 'receipt': 'z-new.json'},
            'ordinary': {'state': 'blocked', 'receipt': 'a-old.json'},
            'done': {'state': 'completed', 'attention_recovery': {'batch': 'test'}, 'receipt': 'b-done.json'},
            'superseded': {'state': 'blocked', 'attention_recovery': {'batch': 'test'}, 'superseded_by': 'review', 'receipt': 'c-stale.json'},
        }
        paths = [self.root / name for name in ('a-old.json', 'b-done.json', 'c-stale.json', 'z-new.json')]
        ordered = recovery.prioritized_dependency_receipts(paths, self.root, jobs)
        self.assertEqual(ordered, [paths[-1]] + paths[:-1])
        roots = recovery.dependency_roots(jobs)
        self.assertEqual(roots, {'review': 'review'})
        child = recovery.promote_dependency({'ticket': {'production': {'key': 'unchanged'}}}, 'review', roots)
        self.assertEqual(child['ticket']['production'], {'key': 'unchanged', 'attention_recovery_parent': 'review'})
        self.assertEqual(recovery.promote_dependency({'ticket': {}}, 'ordinary', roots), {'ticket': {}})
        self.assertEqual(recovery.dependency_roots({'child': {'state': 'blocked', 'production': child['ticket']['production']}}), {'child': 'review'})

    def test_dependency_priority_preserves_verification_first(self):
        spec = importlib.util.spec_from_file_location('attention_priority_controller', Path(__file__).with_name('factory-ng-controller.py'))
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        review = {'state': 'queued', 'attempts': 3, 'attention_recovery': {'previous_attempts': 3}}
        child = {'state': 'queued', 'production': {'attention_recovery_parent': 'review'}}
        verification = dict(child, state='awaiting_verification')
        key = controller.dispatch_priority
        self.assertLess(key(('verify', verification)), key(('child', child)))
        self.assertLess(key(('child', child)), key(('review', review)))

    def test_capacity_requires_transport_error_without_work(self):
        error = json.dumps({'type':'error', 'message':'Selected model is at capacity. Please try a different model.'})
        self.assertTrue(codex_capacity_failure(error))
        self.assertFalse(codex_capacity_failure('Selected model is at capacity.'))
        self.assertFalse(codex_capacity_failure(error+'\n'+json.dumps({'type':'item.completed'})))
        self.assertFalse(codex_capacity_failure(error+'\n'+json.dumps({'type':'turn.completed'})))

    def test_capacity_exit_propagates_from_adapter(self):
        import model_call
        raw = json.dumps({'type':'turn.failed', 'error':{'message':'Selected model is at capacity.'}})
        import io
        from types import SimpleNamespace
        with patch.object(model_call.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'prompt'))), \
             patch.object(model_call.subprocess, 'run', return_value=SimpleNamespace(stdout=raw.encode(), returncode=1)), \
             patch.object(model_call, 'save_raw'), patch.dict(model_call.os.environ, {'PIPE_FACTORY_CODEX_HOST_ACCESS':'0'}):
            with self.assertRaises(SystemExit) as raised:
                model_call.call_codex('model', 'map')
            self.assertEqual(raised.exception.code, CAPACITY_EXIT)

    def test_staged_claude_has_no_builtin_or_inherited_mcp_tools(self):
        import io
        import model_call
        from types import SimpleNamespace
        reply = json.dumps({'result': 'VERDICT: AMBIGUOUS', 'usage': {}})
        with patch.object(model_call.sys, 'stdin', io.StringIO('prompt')), \
             patch.object(model_call.subprocess, 'run', return_value=SimpleNamespace(stdout=reply)) as call, \
             patch.object(model_call, 'save_raw'):
            self.assertEqual(model_call.call_claude('model', 'engine'), 'VERDICT: AMBIGUOUS')
        command = call.call_args.args[0]
        self.assertEqual(command[command.index('--tools') + 1], '')
        self.assertIn('--strict-mcp-config', command)
        self.assertEqual(json.loads(command[command.index('--mcp-config') + 1]), {'mcpServers': {}})


if __name__ == '__main__':
    unittest.main()
