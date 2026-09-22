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
import factory_ng_verification as verification
from factory_ng_quiet import compilation_status

OPS = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, OPS / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


class VerificationTests(unittest.TestCase):
    def test_singleton_test_evidence_requires_a_declared_failed_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); ticket = root/'ticket.json'; proposal = root/'proposal.json'
            key = 'ticket:engine.fixture/v1'
            identity = {'worker': 'codex', 'model': 'model', 'profile': 'codex-constrained@1.1.0'}
            ticket.write_text(json.dumps({'id': key, 'source': {'revision': 'base'},
                'gates': ['cd backend && go test ./game ./cards -run ^TestFactoryNGBound$ -count=1']}))
            patch = 'saved exact patch'
            proposal.write_text(json.dumps({'schema': 'factory.untested-proposal/v1', 'ticket_id': key,
                'ticket_sha256': verification.checksum(ticket.read_bytes()), 'source_revision': 'base',
                'identity': identity, 'patch': patch, 'patch_sha256': verification.checksum(patch.encode()), 'context': {}}))
            result = root/'state/factory-ng-job-output/result.json'; result.parent.mkdir(parents=True)
            result.with_suffix('.manifest.json').write_text(json.dumps([{'ticket_id': key, 'ticket_path': 'ticket.json',
                'proposal': 'proposal.json', 'identity': identity}]))
            for detail, expected in [
                ('expected one counter, got zero\n--- FAIL: TestFactoryNGBound (0.00s)\nFAIL\tmagic-backend/cards\t0.005s', True),
                ('expected one counter\n--- FAIL: TestFactoryNGBound/subcase (0.00s)', True),
                ('--- FAIL: TestUnrelated (0.00s)', False),
                ('--- FAIL: TestFactoryNGBound (1.00s)\npanic: test timed out', False),
                ('--- FAIL: TestFactoryNGBound (1.00s)\nsignal: killed', False),
                ('PASS\nok magic-backend/cards [no tests to run]', False),
            ]:
                with self.subTest(detail=detail):
                    result.write_text(json.dumps({'ticket_results': {key: {'status': 'verification_pending',
                        'proposal': 'proposal.json', 'verification_isolate': True, 'verification_remote_failed': True,
                        'reason': 'Batch could not pass; verify individually: ' + key + ': ' + detail}}}))
                    evidence = verification.singleton_repair_evidence(root, result, ticket, proposal, identity)
                    self.assertEqual(evidence is not None, expected)
                    if expected:
                        self.assertEqual(evidence['failure_kind'], 'test')
                        self.assertEqual(evidence['failure']['outcome'], 'failed')

    def test_go_format_is_scoped_and_reports_syntax_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / 'candidate.go'
            candidate.write_text('package candidate\nfunc Value() int {return 1}\n')
            outside = root / 'outside.go'
            outside.write_text('package outside\nfunc Value() int {return 2}\n')
            original = outside.read_bytes()
            ticket = {'scope': {'allowed_paths': ['candidate.go', 'link.go']}}
            result = verification.normalize_go(root, ticket, ['candidate.go'])
            self.assertEqual(result['outcome'], 'passed')
            self.assertIn('{ return 1 }', candidate.read_text())
            self.assertEqual(outside.read_bytes(), original)
            with self.assertRaisesRegex(ValueError, 'scope'):
                verification.normalize_go(root, ticket, ['outside.go'])
            (root / 'link.go').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                verification.normalize_go(root, ticket, ['link.go'])
            candidate.write_text('package candidate\nfunc Broken(\n')
            result = verification.normalize_go(root, ticket, ['candidate.go'])
            self.assertEqual(result['outcome'], 'failed')
            self.assertIn('candidate.go:', result['detail'])

    def test_saved_go_proposal_is_formatted_before_hashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); clone = root / 'clone'; clone.mkdir()
            subprocess.run(['git', 'init', '-q', str(clone)], check=True)
            subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@local',
                            'commit', '--allow-empty', '-qm', 'base'], cwd=clone, check=True)
            revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=clone, text=True).strip()
            (clone / 'candidate.go').write_text('package candidate\nfunc Value() int {return 1}\n')
            ticket = root / 'ticket.json'
            ticket.write_text(json.dumps({'id': 'test', 'source': {'revision': revision},
                                         'scope': {'allowed_paths': ['candidate.go']}}))
            path = verification.save_proposal(root / 'proposals', clone, ticket, {}, {})
            proposal = verification.load_proposal(path, ticket, {})
            self.assertIn('{ return 1 }', proposal['patch'])
            self.assertEqual(proposal['context']['formatting']['outcome'], 'passed')
            self.assertEqual(proposal['patch_sha256'], verification.checksum(proposal['patch'].encode()))

    def test_manual_switch_has_no_clock_dependency(self):
        self.assertTrue(compilation_status({'work_schedule': {'enabled': True}})['allowed'])
        for value in (False, None, 'true', 1):
            self.assertFalse(compilation_status({'compilation': {'enabled': value}})['allowed'])
        self.assertTrue(compilation_status({'compilation': {'enabled': True}})['allowed'])

    def test_both_harnesses_resume_without_regenerating_and_keep_all_gates(self):
        for name in ('factory-ng-run-engine-ticket', 'factory-ng-run-map-ticket'):
            with self.subTest(harness=name):
                self.harness_roundtrip(name)

    def test_resume_retains_bounded_gate_repair(self):
        self.harness_roundtrip('factory-ng-run-engine-ticket', repair=True)

    def test_prior_compiler_failure_guides_repair_but_all_corrected_gates_run(self):
        self.harness_roundtrip('factory-ng-run-engine-ticket', repair=True, prior_compile_failure=True)

    def test_proven_singleton_failure_with_spent_budget_is_terminal_without_repeating_tests(self):
        self.harness_roundtrip('factory-ng-run-engine-ticket', repair=True,
                               prior_compile_failure=True, spent_repair=True)

    def test_spent_failure_finalization_does_not_need_a_test_slot(self):
        self.harness_roundtrip('factory-ng-run-engine-ticket', repair=True,
                               prior_compile_failure=True, spent_repair=True, evidence_only=True)

    def test_corrected_proposal_releases_worker_and_preserves_budget_for_batch_gates(self):
        self.harness_roundtrip('factory-ng-run-engine-ticket', repair=True,
                               prior_compile_failure=True, defer_repair=True)

    def test_both_harnesses_defer_for_batch_even_when_switch_is_on(self):
        for name in ('factory-ng-run-engine-ticket', 'factory-ng-run-map-ticket'):
            with self.subTest(harness=name):
                self.harness_roundtrip(name, defer=True)

    def test_deferred_scope_rejection_retains_terminal_receipt(self):
        self.harness_roundtrip('factory-ng-run-engine-ticket', defer=True, reject_scope=True)

    def harness_roundtrip(self, name, repair=False, defer=False, reject_scope=False, prior_compile_failure=False, defer_repair=False, spent_repair=False, evidence_only=False):
        m = load(name)
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            root = Path(tmp); source = root / 'source'; source.mkdir()
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            (source / 'a.py').write_text('old\n')
            subprocess.run(['git', 'add', '.'], cwd=source, check=True)
            subprocess.run(['git','-c','user.name=Test','-c','user.email=test@local','commit','-qm','base'],cwd=source,check=True)
            revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
            profile = 'claude-staged@1.0.0' if name.endswith('engine-ticket') else 'qwen-prepared-direct@1.0.2'
            ticket = root / 'ticket.json'
            ticket.write_text(json.dumps({'schema':'factory.ticket-spec/v1','id':'ticket:map.example/v1',
                'work_type':'map','source':{'revision':revision},'scope':{'allowed_paths':['a.py']},
                'skill':{}, 'execution':{'selected_profile':profile},
                'gates':["python3 -c \"from pathlib import Path; assert Path('a.py').read_text().strip() == 'new'\"",'git diff --check']}))
            policy = root / 'policy.json'; policy.write_text('{"compilation":{"enabled":false}}')
            for key,value in [('OPS',root),('SOURCE',source),('RUNS',root/'docs/factory-ng/runs'),('CANDIDATES',root/'candidates')]:
                stack.enter_context(mock.patch.object(m,key,value))
            stack.enter_context(mock.patch.object(verification,'POLICY',policy))
            stack.enter_context(mock.patch.object(m,'source_problem',return_value=None))
            stack.enter_context(mock.patch.object(m,'supports_profile',return_value=True))
            if hasattr(m,'preparation_problems'):stack.enter_context(mock.patch.object(m,'preparation_problems',return_value=[]))
            if hasattr(m,'requested_context'):stack.enter_context(mock.patch.object(m,'requested_context',return_value=''))
            call_name = 'call' if hasattr(m,'call') else 'run'; original = getattr(m,call_name)
            model_calls=[]; gate_calls=[]
            def run(command,cwd,**kwargs):
                text=' '.join(map(str,command))
                if 'model_call.py' in text or 'qwen-prepared-call.py' in text:
                    model_calls.append(text)
                    return {'exit_code':0,'stdout':'PATCH','stderr':'tokens: in=10 out=5 cache_r=0 cache_w=0','elapsed_ms':1}
                if 'map-ticket-spec-pack.py' in text:
                    return {'exit_code':0,'stdout':'fixture packet','stderr':'','elapsed_ms':1}
                if 'map-pipeline-apply.py' in text:
                    (Path(cwd)/'a.py').write_text('wrong\n' if repair and len(model_calls)==1 else 'new\n')
                    if reject_scope: (Path(cwd)/'outside.py').write_text('out of scope\n')
                    return {'exit_code':0,'stdout':'applied','stderr':'','elapsed_ms':1}
                if command[:2]==['bash','-lc']:gate_calls.append(text)
                return original(command,cwd,**kwargs)
            stack.enter_context(mock.patch.object(m,call_name,side_effect=run))
            args=['runner','--ticket',str(ticket),'--worker','test','--model','test-model']
            if name.endswith('engine-ticket'):args+=['--profile',profile]
            def invoke(extra=()):
                output=io.StringIO()
                with mock.patch.object(sys,'argv',args+list(extra)),contextlib.redirect_stdout(output):m.main()
                return json.loads(output.getvalue())
            if defer:
                policy.write_text('{"compilation":{"enabled":true}}')
            first=invoke(['--defer-verification'] if defer else [])
            if reject_scope:
                self.assertEqual(first['status'], 'gate_failed')
                receipt = json.loads((root / first['receipt']).read_text())
                self.assertEqual(receipt['integration'], 'observation_only')
                self.assertEqual(receipt['gates'][-1]['id'], 'proposal-contract')
                self.assertIn('scope', receipt['gates'][-1]['detail'])
                self.assertTrue(receipt['raw_artifacts'])
                self.assertEqual(receipt['model']['telemetry']['model_calls'], 1)
                self.assertFalse(list((root/'candidates').glob('proposal-*.json')))
                self.assertEqual((source/'a.py').read_text(), 'old\n')
                return
            policy.write_text('{"compilation":{"enabled":false}}')
            self.assertEqual(first['status'],'verification_pending')
            self.assertEqual(len(model_calls),1);self.assertEqual(gate_calls,[])
            self.assertNotIn('receipt',first)
            path=root/first['proposal'];self.assertTrue(path.exists())
            raw=path.read_bytes()
            identity={'worker':'test','model':'test-model','profile':profile}
            saved=verification.load_proposal(path,ticket,identity)
            self.assertEqual(saved['source_revision'],revision)
            # A controller restart while still off must save again, without a model call or gate.
            paused=invoke(['--resume-proposal',str(path)])
            self.assertEqual(paused['status'],'verification_pending')
            self.assertEqual(len(model_calls),1);self.assertEqual(gate_calls,[])
            policy.write_text('{"compilation":{"enabled":true}}')
            extra=['--resume-proposal',str(root/paused['proposal'])]
            if spent_repair:
                spent_path = root/paused['proposal']
                spent = json.loads(spent_path.read_text())
                spent['context']['telemetry']['bounded_repair_attempted'] = True
                spent['context']['model_calls'] = 2
                spent_path.write_text(json.dumps(spent))
            if prior_compile_failure:
                result = root/'state/factory-ng-job-output/prior.json'
                result.parent.mkdir(parents=True)
                key = 'ticket:map.example/v1'
                member = {'status': 'verification_pending', 'proposal': paused['proposal'],
                          'verification_isolate': True, 'verification_remote_failed': True,
                          'reason': 'Batch could not pass; verify individually: ' + key +
                                    ': game/example.go:1: undefined: previousSymbol\nFAIL\tmagic-backend/game [build failed]'}
                payload = {'ticket_results': {key: member}}
                result.write_text(json.dumps(payload))
                manifest = [{'ticket_id': key, 'ticket_path': 'ticket.json',
                             'proposal': paused['proposal'], 'identity': identity}]
                result.with_suffix('.manifest.json').write_text(json.dumps(manifest))
                def evidence():
                    return verification.singleton_repair_evidence(root, result, ticket, root/paused['proposal'], identity)
                self.assertIsNotNone(evidence())
                for field, value in [('proposal', first['proposal']), ('verification_remote_failed', False),
                                     ('reason', 'remote SSH unavailable')]:
                    original_member = dict(member)
                    member[field] = value
                    result.write_text(json.dumps(payload))
                    self.assertIsNone(evidence(), field)
                    member.clear(); member.update(original_member)
                result.write_text(json.dumps(payload))
                result.with_suffix('.manifest.json').write_text(json.dumps(manifest * 2))
                self.assertIsNone(evidence())
                result.with_suffix('.manifest.json').write_text(json.dumps(manifest))
                extra += ['--repair-evidence', str(result)]
            if defer_repair:
                extra += ['--defer-repaired-verification', '--repair-only']
                # A race or invalid evidence must never fall through to local tests.
                result_bytes = result.read_bytes()
                result.write_text('{}')
                invalid = invoke(extra)
                self.assertEqual(invalid['status'], 'verification_pending')
                self.assertFalse(invalid['repaired_proposal'])
                self.assertEqual(len(model_calls), 1)
                self.assertEqual(gate_calls, [])
                result.write_bytes(result_bytes)
                controller = load('factory-ng-controller')
                eligible_job = {'worker': 'test', 'model': 'test-model', 'dispatch_profile': profile,
                                'ticket_path': 'ticket.json', 'proposal': paused['proposal'],
                                'verification_remote_failed': True, 'verification_isolate': True,
                                'result_path': str(result.relative_to(root))}
                settings = {'verification': {'batch_size': 8, 'remote': {'enabled': True, 'id': 'remote'}}}
                with mock.patch.object(controller, 'OPS', root), mock.patch.object(controller, 'policy', return_value=settings):
                    self.assertTrue(controller.repair_only_ready(eligible_job))
                    with mock.patch.dict(settings['verification']['remote'], enabled=False):
                        self.assertFalse(controller.repair_only_ready(eligible_job))
            if evidence_only:
                extra += ['--repair-only', '--defer-repaired-verification']
                controller = load('factory-ng-controller')
                eligible_job = {'worker': 'test', 'model': 'test-model', 'dispatch_profile': profile,
                                'ticket_path': 'ticket.json', 'proposal': paused['proposal'],
                                'verification_remote_failed': True, 'verification_isolate': True,
                                'result_path': str(result.relative_to(root))}
                settings = {'verification': {'batch_size': 8, 'remote': {'enabled': True, 'id': 'remote'}}}
                with mock.patch.object(controller, 'OPS', root), mock.patch.object(controller, 'policy', return_value=settings):
                    self.assertTrue(controller.repair_only_ready(eligible_job))
            final=invoke(extra)
            if spent_repair:
                self.assertEqual(final['status'], 'gate_failed')
                self.assertEqual(len(model_calls), 1)
                self.assertEqual(gate_calls, [])
                receipt = json.loads((root/final['receipt']).read_text())
                self.assertEqual(receipt['model']['telemetry']['model_calls'], 2)
                self.assertEqual(receipt['integration'], 'observation_only')
                self.assertNotIn('candidate_patch', receipt['execution'])
                self.assertTrue(any(g['id'] == 'prior-remote-compile-failure' and g['outcome'] == 'failed'
                                    for g in receipt['gates']))
                self.assertTrue(any(a.get('kind') == 'prior_verification_failure' for a in receipt['raw_artifacts']))
                return
            if defer_repair:
                self.assertEqual(final['status'], 'verification_pending')
                self.assertTrue(final['repaired_proposal'])
                self.assertEqual(len(model_calls), 2)
                self.assertEqual(gate_calls, [])  # saved correction has no acceptance yet
                job = {'ticket_id': key, 'ticket_path': 'ticket.json', 'state': 'working', 'pid': -1,
                       'worker': 'test', 'model': 'test-model', 'dispatch_profile': profile,
                       'proposal': paused['proposal'], 'attempts': 1, 'verification_attempts': 1,
                       'verification_resume': True, 'verification_remote_failed': True,
                       'verification_isolate': True, 'result_path': 'result.json'}
                self.assertTrue(verification.corrected_proposal_can_reverify(root, job, final['proposal']))
                self.assertFalse(verification.corrected_proposal_can_reverify(root, job, paused['proposal']))
                corrected_path = root/final['proposal']; corrected_bytes = corrected_path.read_bytes()
                modified = json.loads(corrected_bytes); modified['context']['repair_parent']['sha256'] = 'changed'
                corrected_path.write_text(json.dumps(modified))
                self.assertFalse(verification.corrected_proposal_can_reverify(root, job, final['proposal']))
                corrected_path.write_bytes(corrected_bytes)
                controller = load('factory-ng-controller')
                with mock.patch.object(controller, 'OPS', root), mock.patch.object(controller, 'load_json', return_value=final), \
                     mock.patch.object(controller, 'save_jobs'):
                    controller.reconcile_running({'jobs': {key: job}}, [])
                self.assertEqual(job['state'], 'awaiting_verification')
                self.assertFalse(job.get('verification_remote_failed'))
                self.assertFalse(job['verification_isolate'])
                self.assertEqual(job['attempts'], 1)
                saved = verification.load_proposal(corrected_path, ticket, identity)
                self.assertFalse(m.repair_available(profile, saved['context']['telemetry']))
                batch = load('factory-ng-verify-batch')
                entries = [{'ticket_id': key, 'ticket_path': 'ticket.json',
                            'proposal': final['proposal'], 'identity': identity}]
                with mock.patch.object(batch, 'OPS', root), mock.patch.object(batch, 'SOURCE', source):
                    final = batch.verify(entries, m)['ticket_results'][key]
            self.assertEqual(final['status'],'accepted_for_dependent_observation',final)
            self.assertEqual(len(model_calls),2 if repair else 1)
            self.assertGreaterEqual(len(gate_calls),1 if defer_repair else 2)
            receipt=json.loads((root/final['receipt']).read_text())
            if prior_compile_failure:
                self.assertEqual(len(gate_calls), 1 if defer_repair else 2)
                self.assertEqual({g['id'] for g in receipt['gates'] if g.get('command') in json.loads(ticket.read_text())['gates']
                                  and g['outcome'] == 'passed'}, {'ticket-gate-0', 'ticket-gate-1'})
                self.assertTrue(any(g['id'] == 'prior-remote-compile-failure'
                                    for stage in receipt['attempt_history'] for g in stage['gates']))
                evidence_artifact = next(a for a in receipt['raw_artifacts'] if a.get('kind') == 'prior_verification_failure')
                self.assertEqual(evidence_artifact['sha256'], verification.checksum((root/evidence_artifact['path']).read_bytes()))
            self.assertEqual(receipt['integration'],'eligible_full_gate')
            self.assertTrue((root/receipt['execution']['candidate_patch']).exists())
            self.assertEqual(path.read_bytes(),raw)
            corrupted=json.loads(raw);corrupted['patch']+='tampered'
            path.write_text(json.dumps(corrupted))
            with self.assertRaises(ValueError):verification.load_proposal(path,ticket,identity)
            self.assertEqual((source/'a.py').read_text(),'old\n')

    def test_pending_state_frees_worker_and_preserves_attempt(self):
        m=load('factory-ng-controller')
        job={'ticket_id':'a','state':'working','worker':'w','pid':-1,'attempts':1,'result_path':'result.json'}
        jobs={'jobs':{'a':job}}
        with mock.patch.object(m,'load_json',return_value={'status':'verification_pending','proposal':'saved.json'}), \
             mock.patch.object(m,'save_jobs'):
            m.reconcile_running(jobs,[])
        self.assertEqual(job['state'],'awaiting_verification');self.assertEqual(job['attempts'],1)
        self.assertNotIn('pid',job);self.assertNotIn('receipt',job)

    def test_switch_off_keeps_writing_but_blocks_resume_and_integration(self):
        m=load('factory-ng-controller')
        worker={'id':'w','profile':'p','model':'m','enabled':True,'routing_mode':'auto'}
        ready={'ticket_id':'new','ticket_path':'new.json','state':'queued','profile':'p','work_type':'map'}
        pending={**ready,'ticket_id':'saved','ticket_path':'saved.json','state':'awaiting_verification',
                 'worker':'w','dispatch_profile':'p','proposal':'saved.json'}
        jobs={'jobs':{'new':ready,'saved':pending}}
        availability={'p':{'w':{'allowed':True}}}
        with mock.patch.object(m,'policy',return_value={'compilation':{'enabled':False}}), \
             mock.patch.object(m,'worker_supports_job',return_value=True), \
             mock.patch.object(m.subprocess,'Popen') as spawn:
            selected=m.next_dispatch(jobs,{'p':[worker]},availability)
            self.assertEqual([job['ticket_id'] for _,job,_ in selected],['new'])
            m.dispatch_integration(jobs,[]);spawn.assert_not_called()
        with mock.patch.object(m,'policy',return_value={'compilation':{'enabled':True}}), \
             mock.patch.object(m,'worker_supports_job',return_value=True):
            selected=m.next_dispatch(jobs,{'p':[worker]},availability)
            self.assertEqual([job['ticket_id'] for _,job,_ in selected],['saved'])

    def test_batch_verifier_frees_author_but_individual_repair_owns_lease(self):
        m = load('factory-ng-controller')
        worker = {'id': 'w', 'profile': 'p', 'model': 'm', 'enabled': True}
        ready = {'ticket_id': 'new', 'ticket_path': 'new.json', 'state': 'queued',
                 'profile': 'p', 'work_type': 'map'}
        running = {'state': 'working', 'worker': 'w', 'verification_resume': True}
        jobs = {'jobs': {'new': ready, 'verifier': running}}
        with mock.patch.object(m, 'worker_supports_job', return_value=True):
            for batch, expected in ((True, 1), (False, 0)):
                running['verification_batch'] = batch
                selected = m.next_dispatch(jobs, {'p': [worker]}, {'p': {'w': {'allowed': True}}})
                self.assertEqual(len(selected), expected)
            # A second real model job must still prevent duplicate ownership.
            running['verification_batch'] = True
            jobs['jobs']['draft'] = {'state': 'working', 'worker': 'w'}
            self.assertEqual(m.next_dispatch(jobs, {'p': [worker]}, {'p': {'w': {'allowed': True}}}), [])

    def test_resume_dispatch_does_not_consume_another_model_attempt(self):
        m=load('factory-ng-controller')
        worker={'id':'w','profile':'claude-staged@1.0.0','model':'current-model','enabled':True}
        job={'ticket_id':'saved','ticket_path':'saved.json','state':'awaiting_verification',
             'worker':'w','dispatch_profile':worker['profile'],'proposal':'saved-proposal.json',
             'model':'original-model','attempts':1}
        jobs={'jobs':{'saved':job}}
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(m,'OPS',Path(tmp)), \
             mock.patch.object(m,'sync_jobs',return_value=(jobs,{})), \
             mock.patch.object(m,'reconcile_running'), \
             mock.patch.object(m,'source_problem',return_value=None), \
             mock.patch.object(m,'next_dispatch',return_value=[(Path('saved.json'),job,worker)]), \
             mock.patch.object(m,'policy',return_value={'compilation':{'enabled':True}}), \
             mock.patch.object(m,'job_files',return_value=(Path(tmp)/'out',Path(tmp)/'err')), \
             mock.patch.object(m,'save_jobs'),mock.patch.object(m,'log'), \
             mock.patch.object(m.subprocess,'Popen') as spawn:
            spawn.return_value.pid=123
            m.dispatch_one([],[],{'available':True})
        self.assertEqual(job['attempts'],1)
        self.assertEqual(job['verification_attempts'],1)
        self.assertEqual(job['model'],'original-model')
        self.assertIn('--resume-proposal',spawn.call_args.args[0])

    def test_interrupted_verification_retains_proposal_without_spending_retry(self):
        m=load('factory-ng-controller')
        job={'ticket_id':'a','state':'working','worker':'w','pid':-1,'attempts':1,
             'verification_resume':True,'verification_attempts':2,'result_path':'result.json'}
        with mock.patch.object(m,'load_json',return_value={'status':'verification_pending','proposal':'saved-new.json'}), \
             mock.patch.object(m,'save_jobs'):
            m.reconcile_running({'jobs':{'a':job}},[])
        self.assertEqual(job['state'],'awaiting_verification')
        self.assertEqual(job['verification_attempts'],1)
        self.assertEqual(job['proposal'],'saved-new.json')


if __name__=='__main__':unittest.main()
