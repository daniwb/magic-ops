#!/usr/bin/env python3
"""Repair ancestry, admission and immutable successor regression fixtures."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from factory_ng_recovery import map_repair_history, annotate_repair_blockers, engine_repair_used

OPS = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, OPS / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tidal_chain(generation=2):
    return {
        'ticket:map.tidal/v3': {'id': 'ticket:map.tidal/v3', 'production': {'integration_repair_generation': generation}},
        'ticket:map.tidal/v4': {'id': 'ticket:map.tidal/v4', 'supersedes': 'ticket:map.tidal/v3', 'production': {'integration_recovery_parent': 'ticket:map.tidal/v3'}},
        'ticket:map.tidal/v5': {'id': 'ticket:map.tidal/v5', 'supersedes': 'ticket:map.tidal/v4', 'production': {'integration_recovery_parent': 'ticket:map.tidal/v4'}},
    }


class RecoveryTests(unittest.TestCase):
    def test_map_repair_producer_recovers_legacy_counter_and_stops_at_limit(self):
        producer = load('factory-ng-produce-build-plan')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; tickets = root / 'tickets'
            tickets.mkdir(); (source / 'scripts/paragraph').mkdir(parents=True)
            (source / 'backend/data/carddb').mkdir(parents=True)
            (root / 'docs/factory-ng/measurements').mkdir(parents=True)
            (source / 'scripts/paragraph/reparse.py').write_text("def map_atom():\n    if verb == 'tap':\n        pass\n")
            card = {'status': 'review', 'text': 'Tap target creature.'}
            (source / 'backend/data/carddb/t.json').write_text(json.dumps({'Test': card}))
            (root / 'docs/factory-ng/measurements/pinned.json').write_text(json.dumps({
                'schema': 'factory.targeted-demand/v1', 'shape': 'verb_unmapped:tap',
                'members': [{'name': 'Test', 'text_sha256': producer.digest_bytes(card['text'].encode())}]}))
            chain = tidal_chain(1)
            current = chain['ticket:map.tidal/v5']
            current.update(title='Test', work_type='map', source={'revision': 'old'},
                           gates=['full-card-check'], scope={'allowed_paths': ['scripts/paragraph/reparse.py', 'test.py']},
                           execution={}, required_behavior=['Full card semantics.'],
                           evidence=[{'path': 'docs/factory-ng/measurements/pinned.json'}])
            for i, ticket in enumerate(chain.values()):
                (tickets / ('%d.json' % i)).write_text(json.dumps(ticket))
            (root / 'failed.json').write_text(json.dumps({'outcome': 'gate_failed',
                'ticket': {'sha256': producer.digest_file(tickets / '2.json')},
                'gates': [{'outcome': 'failed', 'detail': 'complete-card spell_seq_targeted failure'}]}))
            job = {'ticket_id': current['id'], 'ticket_path': 'tickets/2.json', 'work_type': 'map',
                   'state': 'failed', 'outcome': 'gate_failed', 'receipt': 'failed.json'}
            jobs = root / 'jobs.json'; jobs.write_text(json.dumps({'jobs': {current['id']: job}}))
            parser = mock.Mock(); parser.reparse_card.return_value = {'eligible': False, 'misses': [('spell_seq_targeted', 'tap')]}
            with mock.patch.object(producer, 'OPS', root), mock.patch.object(producer, 'source_revision', return_value='fresh'):
                successor = producer.integration_repair_candidate(source, tickets, jobs, parser)
                self.assertEqual(successor['production']['integration_repair_generation'], 2)
                self.assertEqual(successor['gates'], current['gates'])
                self.assertEqual(successor['scope'], current['scope'])
                self.assertIn('spell_seq_targeted', successor['required_behavior'][-1])
                # Tidal's real ancestor has already used both attempts.
                chain['ticket:map.tidal/v3']['production']['integration_repair_generation'] = 2
                (tickets / '0.json').write_text(json.dumps(chain['ticket:map.tidal/v3']))
                self.assertIsNone(producer.integration_repair_candidate(source, tickets, jobs, parser))

    def test_dependency_handoff_preserves_recovered_generation(self):
        producer = load('factory-ng-produce-capability-dependency')
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory); (root / 'backend/data/carddb').mkdir(parents=True)
            (root / 'scripts/paragraph').mkdir(parents=True)
            (root / 'scripts/paragraph/reparse.py').write_text('# fixture\n')
            (root / 'backend/data/carddb/t.json').write_text(json.dumps({'Test': {'text': 'Original', 'status': 'review'}}))
            (root / 'pinned.json').write_text(json.dumps({'shape': 'verb_unmapped:tap', 'members': [
                {'name': 'Test', 'text_sha256': producer.digest_bytes(b'Original')}]}))
            chain = tidal_chain(1); parent = chain['ticket:map.tidal/v5']
            parent.update(title='Test', evidence=[{'path': 'pinned.json'}])
            parser = mock.Mock(); parser.reparse_card.return_value = {'eligible': True, 'misses': []}
            import sys
            stack.enter_context(mock.patch.dict(sys.modules, {'reparse': parser}))
            stack.enter_context(mock.patch.multiple(producer, OPS=root, SOURCE=root))
            stack.enter_context(mock.patch.object(producer, 'source_revision', return_value='fresh'))
            stack.enter_context(mock.patch.object(producer, 'source_evidence', return_value=[]))
            ticket, measurement = producer.resumed_map(parent, {'id': 'ticket:engine.test/v1'}, {'key': 'needed'}, chain)
            self.assertEqual(ticket['production']['integration_repair_generation'], 1)
            self.assertEqual(ticket['production']['integration_recovery_parent'], parent['id'])
            self.assertEqual(measurement['member_count'], 1)

    def test_legacy_dependency_hops_do_not_reset_budget(self):
        tickets = tidal_chain()
        result = map_repair_history(tickets['ticket:map.tidal/v5'], tickets)
        self.assertEqual(result['generation'], 2)
        self.assertTrue(result['obligation'])
        self.assertEqual(result['error'], '')
        job = {'work_type': 'map', 'state': 'failed', 'outcome': 'gate_failed', 'receipt': 'failure.json'}
        annotate_repair_blockers({'ticket:map.tidal/v5': job}, tickets)
        self.assertIn('(2/2)', job['repair_blocker']['reason'])
        self.assertEqual(job['state'], 'failed')
        self.assertEqual(job['outcome'], 'gate_failed')
        job['state'] = 'completed'
        annotate_repair_blockers({'ticket:map.tidal/v5': job}, tickets)
        self.assertNotIn('repair_blocker', job)
        self.assertNotIn('waiting_reason', job)

    def test_missing_and_cyclic_ancestry_fail_closed(self):
        tickets = tidal_chain()
        del tickets['ticket:map.tidal/v3']
        self.assertIn('missing', map_repair_history(tickets['ticket:map.tidal/v5'], tickets)['error'])
        tickets = tidal_chain()
        tickets['ticket:map.tidal/v3']['supersedes'] = 'ticket:map.tidal/v5'
        self.assertIn('cyclic', map_repair_history(tickets['ticket:map.tidal/v5'], tickets)['error'])

    def test_engine_repair_survives_later_refresh_and_is_visible_when_exhausted(self):
        ticket = {'id': 'ticket:engine.test/v3', 'production': {'key': 'capability:test:hash:integration-repair-v1:evidence-refresh-v1'}}
        self.assertTrue(engine_repair_used([ticket]))
        job = {'work_type': 'engine', 'state': 'integration_failed', 'outcome': 'candidate_conflict'}
        annotate_repair_blockers({ticket['id']: job}, {ticket['id']: ticket})
        self.assertIn('(1/1)', job['repair_blocker']['reason'])

    def test_full_queue_still_runs_restricted_engine_repair_producer(self):
        controller = load('factory-ng-controller')
        jobs = {'jobs': {str(i): {'state': 'queued', 'work_type': 'engine'} for i in range(215)}}
        jobs['jobs']['failed'] = {'state': 'integration_failed', 'work_type': 'engine'}
        producers = [('capability-dependencies', ['python3', 'producer.py'], 90)]
        with mock.patch.object(controller, 'run_producer') as run:
            self.assertTrue(controller.reserve_engine_integration_repair(producers, jobs, 2, [], []))
            self.assertEqual(run.call_args.args[1][-1], '--engine-integration-repairs-only')
            self.assertIsNone(run.call_args.kwargs['admission'])
            for i, state in enumerate(('working', 'awaiting_integration')):
                jobs['jobs']['repair%d' % i] = {'work_type': 'engine', 'state': state,
                    'production': {'key': 'capability:x:hash:integration-repair-v1'}}
            self.assertFalse(controller.reserve_engine_integration_repair(producers, jobs, 2, [], []))
            jobs['jobs']['repair0']['superseded_by'] = 'other'
            self.assertTrue(controller.reserve_engine_integration_repair(producers, jobs, 2, [], []))
            self.assertFalse(controller.reserve_engine_integration_repair(producers, jobs, 0, [], []))
        repair = jobs['jobs']['repair1']
        self.assertLess(controller.dispatch_priority(('repair', repair)),
                        controller.dispatch_priority(('ordinary', {'work_type': 'engine'})))

    def test_engine_repair_binds_receipts_preserves_contract_and_never_duplicates(self):
        producer = load('factory-ng-produce-capability-dependency')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = 'ticket:engine.test/v1'
            ticket = {'id': key, 'title': 'test', 'work_type': 'engine', 'parents': ['ticket:map.test/v1'],
                      'source': {'revision': 'old'}, 'evidence': [], 'execution': {},
                      'production': {'key': 'capability:test:hash'}, 'gates': ["go test ./game -run '^TestRequired$'"],
                      'required_behavior': ['Keep exact behavior.'], 'scope': {'allowed_paths': ['backend/game/test.go']}}
            path = root / 'ticket.json'; path.write_text(json.dumps(ticket))
            observation = {'ticket': {'id': key, 'sha256': producer.digest_file(path)}, 'outcome': 'accepted_for_dependent_observation'}
            (root / 'observation.json').write_text(json.dumps(observation))
            detail = ('package output\n' * 1000) + "required test filter '^TestRequired$' executed no passing tests"
            failure = {'excluded_candidates': {key: {'status': 'full_gate_failed', 'gates': [
                {'id': 'composed-ticket-1', 'outcome': 'failed', 'detail': detail}]}}}
            (root / 'failure.json').write_text(json.dumps(failure))
            job = {'ticket_id': key, 'work_type': 'engine', 'state': 'integration_failed', 'outcome': 'full_gate_failed',
                   'ticket_path': 'ticket.json', 'receipt': 'observation.json', 'integration_receipt': 'failure.json'}
            with mock.patch.object(producer, 'OPS', root), mock.patch.object(producer, 'source_revision', return_value='fresh'):
                retry = producer.integration_repair_candidate({key: job}, {key: ticket})
                self.assertEqual(retry['supersedes'], key)
                self.assertEqual(retry['gates'], ticket['gates'])
                self.assertEqual(retry['scope'], ticket['scope'])
                self.assertEqual(retry['source']['revision'], 'fresh')
                self.assertIn('executed no passing tests', retry['evidence'][-1]['fact'])
                self.assertEqual(json.loads(path.read_text()), ticket)
                self.assertIsNone(producer.integration_repair_candidate({key: job}, {key: ticket, retry['id']: retry}))
                patch = root / 'docs/factory-ng/candidates/old.patch'
                patch.parent.mkdir(parents=True)
                patch.write_text('historical patch for review')
                observation['execution'] = {'candidate_patch': str(patch.relative_to(root)),
                                            'candidate_patch_sha256': producer.digest_file(patch)}
                (root / 'observation.json').write_text(json.dumps(observation))
                retained = producer.integration_repair_candidate({key: job}, {key: ticket})
                self.assertIn('historical patch for review', retained['evidence'][-1]['fact'])
                patch.write_text('changed after receipt')
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    producer.integration_repair_candidate({key: job}, {key: ticket})
                job['state'] = 'completed'
                self.assertIsNone(producer.integration_repair_candidate({key: job}, {key: ticket}))
                job['state'] = 'integration_failed'
                observation['ticket']['sha256'] = 'wrong'
                (root / 'observation.json').write_text(json.dumps(observation))
                self.assertIsNone(producer.integration_repair_candidate({key: job}, {key: ticket}))

    def test_restricted_mode_cannot_create_fresh_engine_demand(self):
        producer = load('factory-ng-produce-capability-dependency')
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory); (root / 'tickets').mkdir(); (root / 'runs').mkdir()
            (root / 'jobs.json').write_text('{"jobs":{}}')
            for name, value in [('OPS', root), ('TICKETS', root / 'tickets'), ('RUNS', root / 'runs'), ('JOBS', root / 'jobs.json')]:
                stack.enter_context(mock.patch.object(producer, name, value))
            stack.enter_context(mock.patch.object(producer, 'source_clean', return_value=True))
            new = stack.enter_context(mock.patch.object(producer, 'engine_ticket', side_effect=AssertionError('fresh demand forbidden')))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                producer.main(engine_integration_repairs_only=True)
            self.assertEqual(json.loads(out.getvalue())['status'], 'no_integration_repair')
            new.assert_not_called()


if __name__ == '__main__':
    unittest.main()
