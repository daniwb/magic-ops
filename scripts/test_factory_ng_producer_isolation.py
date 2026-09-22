"""A failed card measurement cannot starve independent producer candidates."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from test_factory_ng_producer_performance import load


class CandidateIsolationTest(unittest.TestCase):
    def run_scan(self, all_broken=False):
        m = load('factory-ng-produce-capability-dependency')
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            runs, tickets = root/'runs', root/'tickets'
            runs.mkdir(); tickets.mkdir()
            jobs = {}
            for number in range(2):
                parent, engine = 'ticket:map.p%d/v1' % number, 'ticket:engine.e%d/v1' % number
                (tickets/('p%d.json' % number)).write_text(json.dumps({'id': parent, 'production': {}, 'gates': ['complete original gate'], 'evidence': [{'fact': 'full contract evidence'}]}))
                (tickets/('e%d.json' % number)).write_text(json.dumps({'id': engine, 'production': {}}))
                (runs/('r%d.json' % number)).write_text(json.dumps({'ticket': {'id': parent}, 'capability_demand': {'key': 'e%d' % number}}))
                jobs[engine] = {'state': 'completed'}
            jobs_path = root/'jobs.json'
            original_jobs = json.dumps({'jobs': jobs})
            jobs_path.write_text(original_jobs)
            stack.enter_context(mock.patch.multiple(m, OPS=root, RUNS=runs, TICKETS=tickets, JOBS=jobs_path))
            for name, value in [('source_clean', True), ('source_revision', 'pinned'), ('engine_lane_likely_full', False)]:
                stack.enter_context(mock.patch.object(m, name, return_value=value))
            stack.enter_context(mock.patch.object(m.attention_recovery, 'prioritized_dependency_receipts', side_effect=lambda paths,*args: sorted(paths)))
            stack.enter_context(mock.patch.object(m, 'engine_identity', side_effect=lambda c: ('ticket:engine.'+c['key']+'/v1', b'')))
            def resume(parent, *args):
                self.assertEqual(parent['gates'], ['complete original gate'])
                self.assertEqual(parent['evidence'], [{'fact': 'full contract evidence'}])
                if all_broken or parent['id']=='ticket:map.p0/v1':
                    raise UnboundLocalError("typed is not initialized")
                return {'id': 'ticket:map.p1/v2', 'production': {}}, {'members': ['good']}
            resumed = stack.enter_context(mock.patch.object(m, 'resumed_map', side_effect=resume))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):m.main()
            self.assertEqual(jobs_path.read_text(), original_jobs)
            self.assertEqual(resumed.call_count, 2)
            return json.loads(out.getvalue())

    def test_failed_card_retained_in_evidence_and_later_candidate_produced(self):
        result = self.run_scan()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['ticket_id'], 'ticket:map.p1/v2')
        self.assertEqual(result['candidate_error_count'], 1)
        error = result['candidate_errors'][0]
        self.assertEqual(error['ticket_id'], 'ticket:map.p0/v1')
        self.assertEqual(error['source_revision'], 'pinned')
        self.assertEqual(error['error_type'], 'UnboundLocalError')

    def test_all_measurement_failures_remain_error_not_exhaustion(self):
        result = self.run_scan(all_broken=True)
        self.assertEqual(result['status'], 'producer_error')
        self.assertEqual(result['candidate_error_count'], 2)
        self.assertNotIn('ticket', result)

    def test_compact_index_checks_changed_lineage_and_omits_large_evidence(self):
        from factory_ng_producer_cache import ProducerCache
        m = load('factory-ng-produce-capability-dependency')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ticket = root/'ticket.json'
            payload = {'id': 'ticket:test/v1', 'parents': ['ticket:parent/v1'],
                       'production': {'integration_repair_generation': 1},
                       'evidence': [{'huge': 'x'*100000}], 'gates': ['original']}
            ticket.write_text(json.dumps(payload))
            cache = ProducerCache(root/'cache.db')
            try:
                first = cache.files('dependency-ticket-lifecycle-v1', root, m.ticket_lifecycle)[0][1]
                self.assertNotIn('evidence', first)
                self.assertNotIn('gates', first)
                with mock.patch.object(Path, 'read_text', side_effect=AssertionError('unchanged ticket reread')):
                    self.assertEqual(cache.files('dependency-ticket-lifecycle-v1', root, m.ticket_lifecycle)[0][1], first)
                payload['supersedes'] = 'ticket:older/v1'
                replacement = root/'replacement'
                replacement.write_text(json.dumps(payload)); replacement.replace(ticket)
                latest = cache.files('dependency-ticket-lifecycle-v1', root, m.ticket_lifecycle)[0][1]
                self.assertEqual(latest['supersedes'], 'ticket:older/v1')
                self.assertEqual(latest['production']['integration_repair_generation'], 1)
                ticket.unlink()
                self.assertEqual(cache.files('dependency-ticket-lifecycle-v1', root, m.ticket_lifecycle), [])
            finally:
                cache.close()

    def test_controller_and_watchdog_retain_partial_error_on_success(self):
        controller, watchdog = load('factory-ng-controller'), load('factory-ng-watchdog')
        payload = {'status': 'ready', 'ticket_id': 'ticket:good/v1',
                   'candidate_errors': [{'ticket_id': 'ticket:broken/v1', 'reason': 'parser crash'}],
                   'candidate_error_count': 1}
        results, queued = [], []
        with mock.patch.object(controller, 'write_status'), mock.patch.object(controller, 'log'), \
             mock.patch.object(controller, 'producer_command', return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')), \
             mock.patch.object(controller, 'persist_ready', return_value=('queued','ticket:good/v1')):
            self.assertEqual(controller.run_producer('dependencies', [], 60, results, queued), 'queued')
        self.assertEqual(results[0]['candidate_errors'], payload['candidate_errors'])
        self.assertEqual(queued, ['ticket:good/v1'])
        self.assertEqual(watchdog.runtime_producer_errors({'results': results}), results)


if __name__ == '__main__':
    unittest.main()
