#!/usr/bin/env python3
"""Regressions from the September 7 production outage; no live mutations."""
import contextlib
import ast
import glob
import re
import importlib.util
import json
import io
import os
import hashlib
import sys
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from factory_ng_safety import (source_problem, final_gates_pass,
                               require_executed_test, test_json_command)

OPS = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, OPS / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReliabilityTest(unittest.TestCase):
    def test_watchdog_utc_timestamps_on_non_utc_host(self):
        watchdog = load('factory-ng-watchdog')
        try:
            with mock.patch.dict(os.environ, {'TZ': 'Europe/Zurich'}):
                time.tzset()
                self.assertEqual(watchdog.parse_time('1970-01-01T00:00:00Z'), 0)
                self.assertLess(abs(watchdog.parse_time(watchdog.iso_now()) - time.time()), 2)
        finally:
            time.tzset()

    def test_watchdog_recognizes_absolute_controller_path(self):
        watchdog = load('factory-ng-watchdog')
        argv = b'python3\0' + os.fsencode(OPS / 'scripts/factory-ng-controller.py') + b'\0--interval\015\0'
        with mock.patch.object(watchdog.subprocess, 'run', return_value=mock.Mock(stdout='12345')):
            with mock.patch.object(Path, 'read_bytes', return_value=argv):
                self.assertEqual(watchdog.controller_pids(), [12345])

    def test_recovery_dependencies_are_scoped_and_prioritized(self):
        producer = load('factory-ng-produce-capability-dependency')
        controller = load('factory-ng-controller')
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            runs, tickets = root / 'runs', root / 'tickets'
            runs.mkdir(); tickets.mkdir()
            jobs = root / 'jobs.json'
            jobs.write_text(json.dumps({'jobs': {}}))
            for name, value in [('OPS', root), ('RUNS', runs), ('TICKETS', tickets), ('JOBS', jobs)]:
                stack.enter_context(mock.patch.object(producer, name, value))
            stack.enter_context(mock.patch.object(producer, 'source_clean', return_value=True))
            stack.enter_context(mock.patch.object(producer, 'engine_lane_likely_full', return_value=True))
            stack.enter_context(mock.patch.object(producer, 'engine_identity', return_value=('ticket:engine.needed/v1', '{}')))
            stack.enter_context(mock.patch.object(producer, 'engine_ticket', return_value={
                'id': 'ticket:engine.needed/v1', 'work_type': 'engine', 'production': {}}))
            for index, recovery in enumerate((False, True)):
                parent = {'id': 'ticket:map.parent%d/v1' % index, 'production': {}}
                if recovery:
                    parent['production']['integration_repair_generation'] = 1
                (tickets / ('map%d.json' % index)).write_text(json.dumps(parent))
                (runs / ('receipt%d.json' % index)).write_text(json.dumps({
                    'outcome': 'blocked_by_capability', 'ticket': {'id': parent['id']},
                    'capability_demand': {'key': 'needed'}}))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                producer.main(integration_recovery_only=True)
            result = json.loads(output.getvalue())
            self.assertEqual(result['ticket']['production']['integration_recovery_parent'], 'ticket:map.parent1/v1')
            (tickets / 'engine.json').write_text(json.dumps({'id': 'ticket:engine.needed/v1', 'production': {}}))
            jobs.write_text(json.dumps({'jobs': {'ticket:engine.needed/v1': {'state': 'queued'}}}))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                producer.main(integration_recovery_only=True)
            self.assertEqual(json.loads(output.getvalue())['status'], 'recovery_dependency')
            ordinary = controller.dispatch_priority(('engine', {'work_type': 'engine', 'production': {'retry_reason': 'semantic_gate_repair'}}))
            recovery = controller.dispatch_priority(('engine', {'work_type': 'engine', 'priority_recovery_parent': 'map'}))
            self.assertLess(recovery, ordinary)

    def test_dependency_resume_does_not_close_a_migrated_miss(self):
        producer = load('factory-ng-produce-capability-dependency')
        producer.source_evidence = mock.Mock(return_value=[])
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            (root / 'backend/data/carddb').mkdir(parents=True)
            (root / 'scripts/paragraph').mkdir(parents=True)
            (root / 'scripts/paragraph/reparse.py').write_text('# fixture\n')
            card_path = root / 'backend/data/carddb/t.json'
            card_path.write_text(json.dumps({'Test': {'text': 'Original', 'status': 'review'}}))
            (root / 'pinned.json').write_text(json.dumps({'shape': 'verb_unmapped:tap', 'members': [
                {'name': 'Test', 'text_sha256': producer.digest_bytes(b'Original')}]}))
            parser = mock.Mock()
            parser.reparse_card.return_value = {'eligible': False, 'misses': [('spell_seq_targeted', 'remaining clause')]}
            stack.enter_context(mock.patch.dict(sys.modules, {'reparse': parser}))
            for name, value in [('OPS', root), ('SOURCE', root)]:
                stack.enter_context(mock.patch.object(producer, name, value))
            stack.enter_context(mock.patch.object(producer, 'source_revision', return_value='base'))
            stack.enter_context(mock.patch.object(producer, 'next_version', return_value='ticket:map.test/v3'))
            parent = {'id': 'ticket:map.test/v2', 'title': 'test', 'evidence': [{'path': 'pinned.json'}],
                      'production': {'integration_repair_generation': 1}}
            ticket, measurement = producer.resumed_map(parent, {'id': 'ticket:engine.test/v1'}, {'key': 'needed'})
            self.assertIsNotNone(ticket)
            self.assertEqual(measurement['members'][0]['all_miss_shapes'], ['spell_seq_targeted'])
            self.assertEqual(ticket['production']['retry_reason'], 'integration_conflict_repair')
            parser.reparse_card.return_value = {'eligible': True, 'misses': []}
            ticket, measurement = producer.resumed_map(parent, {'id': 'ticket:engine.test/v1'}, {'key': 'needed'})
            self.assertIsNotNone(ticket)
            self.assertEqual(measurement['members'][0]['name'], 'Test')
            self.assertIn('not proof', ticket['required_behavior'][-1])
            parent['production'] = {}
            ticket, measurement = producer.resumed_map(parent, {'id': 'ticket:engine.test/v1'}, {'key': 'needed'})
            self.assertIsNotNone(ticket)
            self.assertEqual(measurement['member_count'], 1)
            self.assertTrue(any('every ability' in text for text in ticket['required_behavior']))

    def test_integration_repair_does_not_depend_on_discovery_frontier(self):
        producer = load('factory-ng-produce-build-plan')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, tickets = root / 'source', root / 'tickets'
            (source / 'scripts/paragraph').mkdir(parents=True)
            (source / 'backend/data/carddb').mkdir(parents=True)
            tickets.mkdir()
            (root / 'docs/factory-ng/measurements').mkdir(parents=True)
            (source / 'scripts/paragraph/reparse.py').write_text("def map_atom():\n    if verb == 'tap':\n        pass\n")
            card = {'status': 'auto', 'text': 'Tap target creature.'}
            (source / 'backend/data/carddb/t.json').write_text(json.dumps({'Test Card': card}))
            measurement = {'schema': 'factory.targeted-demand/v1', 'shape': 'verb_unmapped:tap',
                           'members': [{'name': 'Test Card', 'text_sha256': producer.digest_bytes(card['text'].encode())}]}
            (root / 'docs/factory-ng/measurements/pinned.json').write_text(json.dumps(measurement))
            original = {'id': 'ticket:map.test/v1', 'title': 'Test', 'work_type': 'map',
                        'source': {'revision': 'old'}, 'gates': ['original-test', 'original-measurement'],
                        'scope': {'allowed_paths': ['scripts/paragraph/reparse.py', 'test.py']},
                        'execution': {'profile_policy': 'exact', 'compatible_profiles': ['claude-staged@1.0.0']},
                        'production': {'key': 'same-obligation', 'trial_id': 'five', 'trial_card': 'Test Card'},
                        'required_behavior': ['Preserve full Oracle behavior.'],
                        'evidence': [{'path': 'docs/factory-ng/measurements/pinned.json'}]}
            old_path = tickets / 'old.json'
            old_path.write_text(json.dumps(original))
            (root / 'accepted.json').write_text(json.dumps({'outcome': 'accepted_for_dependent_observation',
                'ticket': {'sha256': producer.digest_file(old_path)}}))
            job = {'ticket_id': original['id'], 'ticket_path': 'tickets/old.json', 'work_type': 'map',
                   'state': 'integration_failed', 'outcome': 'candidate_conflict',
                   'receipt': 'accepted.json', 'integration_receipt': 'failure.json'}
            jobs_path = root / 'jobs.json'
            jobs_path.write_text(json.dumps({'jobs': {original['id']: job}}))
            parser = mock.Mock()
            parser.reparse_card.return_value = {'eligible': False, 'misses': [('spell_seq_targeted', 'tap')]}
            with mock.patch.object(producer, 'OPS', root), mock.patch.object(producer, 'source_revision', return_value='new'):
                self.assertIsNone(producer.integration_repair_candidate(source, tickets, jobs_path, parser, trial_id='different'))
                self.assertIsNone(producer.integration_repair_candidate(source, tickets, jobs_path, parser, only_ids=['unselected']))
                retry = producer.integration_repair_candidate(source, tickets, jobs_path, parser, trial_id='five')
                self.assertEqual(retry['production']['trial_id'], 'five')
                self.assertEqual(retry['execution']['profile_policy'], 'exact')
                self.assertEqual(retry['execution']['compatible_profiles'], ['claude-staged@1.0.0'])
                self.assertEqual(retry['supersedes'], original['id'])
                self.assertEqual(retry['source']['revision'], 'new')
                self.assertEqual(retry['gates'], original['gates'])
                self.assertEqual(retry['scope'], original['scope'])
                self.assertIn('spell_seq_targeted', retry['evidence'][-1]['fact'])
                (tickets / 'new.json').write_text(json.dumps(retry))
                self.assertIsNone(producer.integration_repair_candidate(source, tickets, jobs_path, parser))
                # A recovery worker's gate failure gets the one remaining
                # bounded revision, even though it never reached integration.
                retry_path = tickets / 'new.json'
                (root / 'failed.json').write_text(json.dumps({'outcome': 'gate_failed',
                    'ticket': {'sha256': producer.digest_file(retry_path)},
                    'gates': [{'id': 'semantic', 'outcome': 'failed', 'detail': 'optional clause missing'}]}))
                failed_job = {'ticket_id': retry['id'], 'ticket_path': 'tickets/new.json',
                    'work_type': 'map', 'state': 'failed', 'outcome': 'gate_failed', 'receipt': 'failed.json'}
                jobs_path.write_text(json.dumps({'jobs': {retry['id']: failed_job}}))
                last_retry = producer.integration_repair_candidate(source, tickets, jobs_path, parser)
                self.assertEqual(last_retry['production']['integration_repair_generation'], 2)
                self.assertEqual(last_retry['gates'], original['gates'])
                self.assertIn('optional clause missing', last_retry['required_behavior'][-1])
                self.assertEqual(last_retry['evidence'][-1]['path'], 'failed.json')
                # Exhaustion and unrelated generic failures must stay closed.
                for generation in (2, 0):
                    retry['production']['integration_repair_generation'] = generation
                    retry_path.write_text(json.dumps(retry))
                    (root / 'failed.json').write_text(json.dumps({'outcome': 'gate_failed',
                        'ticket': {'sha256': producer.digest_file(retry_path)}}))
                    self.assertIsNone(producer.integration_repair_candidate(source, tickets, jobs_path, parser))

    def test_pinned_measurement_checks_auto_text_and_migrated_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts/paragraph').mkdir(parents=True)
            (root / 'cards').mkdir()
            (root / 'scripts/paragraph/reparse.py').write_text(
                "from pathlib import Path\nCARDDB = Path(__file__).resolve().parents[2] / 'cards'\n"
                "def reparse_card(card):\n return {'eligible': not card.get('misses'), 'misses': card.get('misses', [])}\n")
            for command in (['git', 'init', '-q'], ['git', '-c', 'user.name=Test', '-c', 'user.email=test@local', 'commit', '--allow-empty', '-qm', 'base']):
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            text_hash = 'sha256:' + hashlib.sha256(b'Original text').hexdigest()
            pinned = root / 'pinned.json'
            pinned.write_text(json.dumps({'schema': 'factory.targeted-demand/v1', 'shape': 'verb_unmapped:tap',
                                         'members': [{'name': 'Test', 'text_sha256': text_hash}]}))
            def measure(card):
                (root / 'cards/t.json').write_text(json.dumps({'Test': card}))
                return subprocess.run([sys.executable, str(OPS / 'scripts/factory-ng-targeted-demand.py'),
                    '--repo', str(root), '--members-from', str(pinned)], capture_output=True, text=True)
            result = measure({'status': 'auto', 'text': 'Original text'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['pinned_unresolved_count'], 0)
            self.assertNotEqual(measure({'status': 'auto', 'text': 'Changed text'}).returncode, 0)
            self.assertNotEqual(measure({'status': 'manual', 'text': 'Original text'}).returncode, 0)
            result = measure({'status': 'review', 'text': 'Original text', 'misses': [['spell_seq_targeted', 'moved']]})
            value = json.loads(result.stdout)
            self.assertEqual(value['member_count'], 0)
            self.assertEqual(value['pinned_unresolved_count'], 1)
            command = 'python3 factory-ng-targeted-demand.py --members-from pinned.json reports zero remaining pinned members'
            for module_name, function, call_name in [('factory-ng-run-map-ticket', 'run_ticket_gate', 'run'),
                                                      ('factory-ng-run-engine-ticket', 'ticket_gate', 'call')]:
                runner = load(module_name)
                with mock.patch.object(runner, call_name, return_value={'exit_code': 0, 'stdout': result.stdout, 'stderr': '', 'elapsed_ms': 0}):
                    gated = getattr(runner, function)(command, root, {'work_type': 'map'})
                    self.assertNotEqual(gated['exit_code'], 0)

    def test_staged_resolver_locates_real_function_and_qualified_name(self):
        source = (OPS / 'scripts/engine-pipeline-pack.py').read_text()
        node = next(item for item in ast.parse(source).body
                    if isinstance(item, ast.FunctionDef) and item.name == '_resolve_named_function')
        namespace = {'re': re, 'glob': glob, 'os': os, 'Path': Path}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<staged-resolver-test>', 'exec'), namespace)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backend/game').mkdir(parents=True)
            (root / 'backend/game/effects.go').write_text('package game\n\n// A real seam.\nfunc (g *Game) GetPowerWithEffects() int {\n return 1\n}\n')
            hit = namespace['_resolve_named_function'](directory, 'Game.GetPowerWithEffects')
            self.assertEqual(hit, ('backend/game/effects.go', 2, 6))
            self.assertIsNone(namespace['_resolve_named_function'](directory, 'missingSymbol'))

    def test_shunt_records_treatment_and_scoped_passthrough(self):
        shunt = load('shunt-bulk-read')
        with tempfile.TemporaryDirectory() as directory:
            path, log = Path(directory) / 'large.go', Path(directory) / 'decisions.jsonl'
            path.write_text('line\n' * 400)
            with mock.patch.dict(os.environ, {'SHUNT_TELEMETRY_PATH': str(log)}):
                for scoped in (True, False):
                    event = {'tool_name': 'Read', 'session_id': 'test', 'tool_input': {'file_path': str(path)}}
                    if scoped:
                        event['tool_input']['limit'] = 10
                    with mock.patch('sys.stdin', io.StringIO(json.dumps(event))), \
                         mock.patch.object(shunt, 'summarize', return_value='A summary'), \
                         contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                        shunt.main()
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([row['decision'] for row in rows], ['pass_through', 'summarized'])
            self.assertEqual(rows[0]['reason'], 'scoped_read')

    def test_wave_isolates_conflict_and_lands_only_included_parents(self):
        integration = load('factory-ng-integrate')
        real_call = integration.call
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin, source = root / 'origin.git', root / 'source'
            def git(repo, *args):
                result = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()
            git(root, 'init', '--bare', '-q', str(origin))
            git(root, 'clone', '-q', str(origin), str(source))
            git(source, 'checkout', '-b', 'main')
            git(source, 'config', 'user.name', 'Test')
            git(source, 'config', 'user.email', 'test@local')
            (source / 'a').write_text('base\n')
            (source / 'b').write_text('base\n')
            (source / 'corpus').mkdir()
            (source / 'corpus/keep').write_text('base\n')
            (source / 'backend/data/carddb').mkdir(parents=True)
            (source / '.gitignore').write_text('corpus/AtomicCards.json.gz\n')
            (source / 'backend/data/carddb/keep').write_text('base\n')
            git(source, 'add', '.')
            git(source, 'commit', '-qm', 'base')
            git(source, 'push', '-qu', 'origin', 'main')
            (source / 'corpus/AtomicCards.json.gz').write_bytes(b'test input')
            revision = git(source, 'rev-parse', 'HEAD')
            receipts = []
            for number, filename in enumerate(('a', 'a', 'b')):
                candidate = root / ('candidate%d' % number)
                git(root, 'clone', '-q', str(source), str(candidate))
                (candidate / filename).write_text('candidate%d\n' % number)
                git(candidate, '-c', 'user.name=Test', '-c', 'user.email=test@local',
                    'commit', '-am', 'candidate')
                patch = root / ('candidate%d.patch' % number)
                patch.write_text(git(candidate, 'format-patch', '-1', '--stdout') + '\n')
                receipt = root / ('receipt%d.json' % number)
                receipt.write_text(json.dumps({'schema': 'factory.observation-receipt/v1',
                    'outcome': 'accepted_for_dependent_observation', 'ticket': {'id': 'ticket:test%d/v1' % number},
                    'execution': {'source_revision': revision, 'candidate_patch': patch.name,
                                  'candidate_patch_sha256': integration.digest(patch)}}))
                receipts.append(receipt)
            policy = root / 'policy.json'
            policy.write_text(json.dumps({'integration': {'automatic': True, 'push_when_full_gate_green': False}}))
            def call(command, cwd, **kwargs):
                if command[0] == 'git':
                    return real_call(command, cwd, **kwargs)
                return {'exit_code': 0, 'stdout': '', 'stderr': '', 'elapsed_ms': 0}
            output = io.StringIO()
            with contextlib.ExitStack() as stack:
                for name, value in [('OPS', root), ('SOURCE', source), ('RUNS', root / 'runs'), ('POLICY', policy)]:
                    stack.enter_context(mock.patch.object(integration, name, value))
                stack.enter_context(mock.patch.object(integration, 'call', side_effect=call))
                stack.enter_context(mock.patch.object(integration, 'semantic_gates', return_value=True))
                stack.enter_context(mock.patch.object(integration, 'lock', return_value=mock.Mock()))
                stack.enter_context(mock.patch.object(integration, 'stamp', return_value='2026-09-09T000000Z'))
                stack.enter_context(mock.patch('sys.argv', ['integrate'] + [word for path in receipts for word in ('--receipt', str(path))]))
                stack.enter_context(contextlib.redirect_stdout(output))
                code = integration.main()
                self.assertEqual(code, 0, output.getvalue())
                first_output = output.getvalue()
                first_head = git(source, 'rev-parse', 'HEAD')
                output.seek(0)
                output.truncate()
                # A push retry sees the landed patches, not their original commit IDs.
                # It must revalidate them without replay conflicts or duplicate commits.
                code = integration.main()
                self.assertEqual(code, 0, output.getvalue())
                self.assertEqual(git(source, 'rev-parse', 'HEAD'), first_head)
                retry = json.loads(output.getvalue())
                self.assertNotEqual(retry['receipt'], json.loads(first_output)['receipt'])
                self.assertEqual(retry['ticket_results']['ticket:test0/v1']['status'],
                                 'committed_locally_full_production_gate_green')
                retry_receipt = json.loads((root / retry['receipt']).read_text())
                self.assertTrue(any(g['id'] == 'candidate-already-present' for g in retry_receipt['gates']))
            result = json.loads(first_output)
            self.assertEqual(result['ticket_results']['ticket:test1/v1']['status'], 'candidate_conflict')
            landed = json.loads((root / result['receipt']).read_text())
            self.assertNotIn('ticket:test1/v1', landed['parents'])
            self.assertIn('ticket:test0/v1', landed['parents'])
            self.assertIn('ticket:test2/v1', landed['parents'])
            self.assertEqual((source / 'a').read_text(), 'candidate0\n')
            self.assertEqual((source / 'b').read_text(), 'candidate2\n')
            self.assertEqual(source_problem(source), '')

    def test_wave_reconciliation_keeps_individual_outcomes(self):
        controller = load('factory-ng-controller')
        jobs = {'jobs': {name: {'ticket_id': name, 'state': 'integrating', 'pid': -1,
                               'result_path': 'result.json'} for name in ('good', 'conflict')}}
        result = {'ticket_results': {
            'good': {'status': 'pushed_full_production_gate_green'},
            'conflict': {'status': 'candidate_conflict', 'gates': [{'outcome': 'failed'}]}}}
        with mock.patch.object(controller, 'load_json', return_value=result), \
             mock.patch.object(controller, 'save_jobs'), mock.patch.object(controller, 'log'):
            controller.reconcile_running(jobs, [])
        self.assertEqual(jobs['jobs']['good']['state'], 'completed')
        self.assertEqual(jobs['jobs']['conflict']['state'], 'integration_failed')

    def test_integration_keeps_consumed_verification_receipt(self):
        controller = load('factory-ng-controller')
        job = {'ticket_id': 'conflict', 'state': 'integrating', 'pid': -1,
               'result_path': 'result.json', 'verification_resume': True,
               'receipt': 'accepted.json', 'processed_receipt': 'accepted.json',
               'integration_attempts': 1}
        jobs = {'jobs': {'conflict': job}}
        result = {'status': 'candidate_conflict', 'receipt': 'integration-failure.json',
                  'gates': [{'outcome': 'failed'}]}
        with mock.patch.object(controller, 'load_json', return_value=result), \
             mock.patch.object(controller, 'save_jobs'), mock.patch.object(controller, 'log'):
            controller.reconcile_running(jobs, [])
            controller.recover_integration_failures(jobs, {'integration': {'automatic': True}})
        self.assertEqual(job['state'], 'integration_failed')
        self.assertEqual(job['processed_receipt'], 'accepted.json')
        self.assertEqual(job['receipt'], 'accepted.json')
        self.assertEqual(job['integration_receipt'], 'integration-failure.json')
        self.assertEqual(job['integration_attempts'], 1)

    def test_empty_porcelain_does_not_hide_unfinished_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            self.assertEqual(source_problem(repo), '')
            (repo / '.git/MERGE_HEAD').write_text('0' * 40 + '\n')
            status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True)
            self.assertEqual(status, '')
            self.assertIn('MERGE_HEAD', source_problem(repo))

    def test_git_failure_is_not_a_clean_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('git status failed', source_problem(directory))

    def test_source_probe_avoids_optional_index_writes_but_respects_real_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            real_run = subprocess.run
            with mock.patch('factory_ng_safety.subprocess.run', wraps=real_run) as run:
                self.assertEqual(source_problem(repo), '')
                status = next(c for c in run.call_args_list if c.args[0][:2] == ['git', 'status'])
                self.assertEqual(status.kwargs['env']['GIT_OPTIONAL_LOCKS'], '0')
            (repo / '.git/index.lock').touch()
            self.assertIn('index.lock', source_problem(repo))

    def test_repaired_candidate_is_judged_on_final_checks(self):
        gates = [{'id': 'initial-patch-apply', 'outcome': 'failed'},
                 {'id': 'patch-apply', 'outcome': 'passed'},
                 {'id': 'scope', 'outcome': 'passed'},
                 {'id': 'ticket-gate-1', 'outcome': 'passed'}]
        self.assertTrue(final_gates_pass(gates))
        gates[-1]['outcome'] = 'failed'
        self.assertFalse(final_gates_pass(gates))
        self.assertFalse(final_gates_pass(gates[:1]))

    def test_named_gate_rejects_zero_tests_and_skips(self):
        command = "cd backend && go test ./game ./cards -run '^TestRequired$' -count=1"
        for events in ([{'Action': 'pass', 'Package': 'game'}],
                       [{'Action': 'skip', 'Test': 'TestRequired'}]):
            result = {'exit_code': 0, 'stdout': '\n'.join(map(json.dumps, events)), 'stderr': ''}
            self.assertEqual(require_executed_test(command, result)['exit_code'], 1)
        result = {'exit_code': 0, 'stdout': json.dumps({'Action': 'pass', 'Test': 'TestRequired'}), 'stderr': ''}
        self.assertEqual(require_executed_test(command, result)['exit_code'], 0)
        self.assertIn('go test -json', test_json_command(command))

    def test_both_runners_enforce_named_test_execution(self):
        command = "cd backend && go test ./game ./cards -run '^TestRequired$'"
        for name, function, call in [('factory-ng-run-engine-ticket', 'ticket_gate', 'call'),
                                     ('factory-ng-run-map-ticket', 'run_ticket_gate', 'run')]:
            runner = load(name)
            with mock.patch.object(runner, call, return_value={
                    'exit_code': 0, 'stdout': '{"Action":"pass","Package":"game"}\n', 'stderr': ''}) as invoked:
                result = getattr(runner, function)(command, Path('/unused'), {})
                self.assertEqual(result['exit_code'], 1)
                self.assertIn('go test -json', invoked.call_args.args[0][-1])

    def test_receipt_order_does_not_depend_on_directory_listing(self):
        controller = load('factory-ng-controller')
        with tempfile.TemporaryDirectory() as directory:
            controller.OPS = Path(directory)
            newer = Path(directory) / '2026-09-07T110000Z-new.json'
            older = Path(directory) / '2026-09-07T090000Z-old.json'
            for path, outcome in [(newer, 'accepted_for_dependent_observation'),
                                  (older, 'infrastructure_failed')]:
                path.write_text(json.dumps({'schema': 'factory.observation-receipt/v1',
                    'ticket': {'id': 'ticket:test/v1'}, 'outcome': outcome}))
            controller.RUNS = Path(directory)
            with controller.os.scandir(directory) as entries:
                unordered = sorted(entries, key=lambda entry: entry.name, reverse=True)
            listing = mock.MagicMock()
            listing.__enter__.return_value = iter(unordered)
            with mock.patch.object(controller.os, 'scandir', return_value=listing):
                self.assertEqual(controller.observed_ticket_ids()['ticket:test/v1']['outcome'],
                                 'accepted_for_dependent_observation')

    def test_landing_retry_does_not_spend_model_attempts(self):
        controller = load('factory-ng-controller')
        job = {'state': 'integration_failed', 'outcome': 'infrastructure_failed',
               'attempts': 2, 'receipt': 'accepted.json'}
        settings = {'integration': {'automatic': True}, 'retry': {'infrastructure_attempts': 3}}
        receipt = {'outcome': 'accepted_for_dependent_observation', 'integration': 'eligible_full_gate'}
        with mock.patch.object(controller, 'load_json', return_value=receipt):
            controller.recover_integration_failures({'jobs': {'ticket:test/v1': job}}, settings)
        self.assertEqual(job['state'], 'awaiting_integration')
        self.assertEqual(job['attempts'], 2)
        self.assertGreater(job['integration_retry_after_epoch'], time.time())
        for change in ({'integration_attempts': 3}, {'superseded_by': 'ticket:test/v2'},
                       {'outcome': 'candidate_conflict'}):
            excluded = dict(job, state='integration_failed', **change)
            with mock.patch.object(controller, 'load_json', return_value=receipt):
                controller.recover_integration_failures({'jobs': {'test': excluded}}, settings)
            self.assertEqual(excluded['state'], 'integration_failed')

    def test_producer_snapshot_preserves_inventory(self):
        controller = load('factory-ng-controller')
        with tempfile.TemporaryDirectory() as directory:
            controller.STATE = Path(directory) / 'runtime.json'
            controller.STATE.write_text(json.dumps({'queue': {'runnable': 0, 'deferred': 348},
                'deferred': ['ticket:test/v1']}))
            controller.write_status(state='running', phase='producing_ticket')
            self.assertEqual(json.loads(controller.STATE.read_text())['queue']['deferred'], 348)

    def test_watchdog_does_not_hide_unknown_queue_or_old_integration_failure(self):
        watchdog = load('factory-ng-watchdog')
        signature = {'accepted_receipts': 1, 'completed_jobs': 0, 'integrations': 0,
                     'latest_productive_epoch': 100}
        data = {watchdog.RUNTIME: {'updated_at': watchdog.iso_now(), 'phase': 'producing_ticket'},
                watchdog.JOBS: {'jobs': {'q': {'state': 'queued'}, 'f': {'state': 'integration_failed'}}},
                watchdog.STATE: {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time()-600)),
                                 'productive_signature': signature}}
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            watchdog.LOG = Path(directory) / 'log'
            stack.enter_context(mock.patch.object(watchdog, 'load_json', side_effect=lambda p,d=None: data.get(p,d)))
            for name, value in [('controller_pids', [1]), ('source_problem', ''), ('latest_mtime', 100),
                                ('productive_signature', signature), ('card_progress', {'available': False})]:
                stack.enter_context(mock.patch.object(watchdog, name, return_value=value))
            stack.enter_context(mock.patch.object(watchdog, 'atomic_write'))
            stack.enter_context(mock.patch.object(watchdog, 'record_queue_trend', side_effect=OSError('isolated test')))
            response = stack.enter_context(mock.patch.object(watchdog.urllib.request, 'urlopen'))
            response.return_value.__enter__.return_value.status = 200
            result = watchdog.poll(restart=False)
            response.assert_any_call('http://127.0.0.1:9999/factory-ng/cards', timeout=15)
        self.assertFalse(result['healthy'])
        self.assertIn('unknown', ' '.join(result['problems']))
        self.assertIn('unresolved integration', ' '.join(result['problems']))

    def test_empty_supply_alert_does_not_restart_a_healthy_controller(self):
        watchdog = load('factory-ng-watchdog')
        signature = {'accepted_receipts': 0, 'completed_jobs': 0, 'integrations': 0}
        data = {watchdog.RUNTIME: {'updated_at': watchdog.iso_now(), 'queue': {'runnable': 0, 'deferred': 0}},
                watchdog.JOBS: {'jobs': {}}, watchdog.WORKERS: {'workers': [{'enabled': True}]},
                watchdog.POLICY: {'compilation': {'enabled': True}},
                watchdog.STATE: {'checked_at': watchdog.iso_now(), 'productive_signature': signature,
                                 'supply_empty_since_epoch': time.time() - 700}}
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            watchdog.LOG = Path(directory) / 'log'
            stack.enter_context(mock.patch.object(watchdog, 'load_json', side_effect=lambda p,d=None: data.get(p,d)))
            for name, value in [('controller_pids', [1]), ('source_problem', ''), ('latest_mtime', 100),
                                ('productive_signature', signature), ('card_progress', {'available': False})]:
                stack.enter_context(mock.patch.object(watchdog, name, return_value=value))
            stack.enter_context(mock.patch.object(watchdog, 'atomic_write'))
            stack.enter_context(mock.patch.object(watchdog, 'record_queue_trend', return_value={}))
            response = stack.enter_context(mock.patch.object(watchdog.urllib.request, 'urlopen'))
            response.return_value.__enter__.return_value.status = 200
            kill = stack.enter_context(mock.patch.object(watchdog.os, 'kill'))
            result = watchdog.poll(restart=True)
            self.assertIn('ticket supply exhausted', ' '.join(result['problems']))
            kill.assert_not_called()
            # A saved proposal owned by a disabled/quota-held worker is not
            # runnable supply and must not suppress the empty-reserve alert.
            data[watchdog.JOBS]['jobs'] = {'held': {'state': 'awaiting_verification'}}
            result = watchdog.poll(restart=True)
            self.assertIn('ticket supply exhausted', ' '.join(result['problems']))
            kill.assert_not_called()
            data[watchdog.POLICY]['compilation']['enabled'] = False
            result = watchdog.poll(restart=True)
            self.assertIsNone(result['supply_empty_since_epoch'])
            self.assertNotIn('ticket supply exhausted', ' '.join(result['problems']))

    def test_daily_failure_does_not_age_out(self):
        report = load('factory-ng-daily-report')
        value = report.summarize({'status': {'state': 'running'}, 'data': {'jobs': [
            {'state': 'integration_failed', 'outcome': 'infrastructure_failed', 'updated_at': '2020-01-01T00:00:00Z'}]}})
        self.assertEqual(value['health'], 'REVIEW')

    def test_paced_percentage_is_used(self):
        script = ('source scripts/lib-pace-gate.sh; date() { echo 1788775200; }; '
                  'for review_pct in 5 95; do WEEKLY_GATE_PCT=$review_pct; '
                  '_pace_day_bounds 1788976800; echo "$_P_ALLOWED"; done')
        result = subprocess.check_output(['bash', '-c', script], cwd=OPS, text=True)
        self.assertEqual(result.split(), ['4', '68'])


if __name__ == '__main__':
    unittest.main()
