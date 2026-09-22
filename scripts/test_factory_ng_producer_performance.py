"""Scan performance must preserve discovery, dependency ordering and single-writer state."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from factory_ng_producer_cache import ProducerCache, receipt_demand

OPS = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, OPS / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScanTest(unittest.TestCase):
    def run_refill_sweep(self, behavior, producer_set=None, burst_limits=None, source_problem=None):
        m = load('factory-ng-controller')
        workers = [{'id': 'w%d' % i, 'profile': 'test', 'enabled': True} for i in range(5)]
        profiles = m.configured_workers_by_profile(workers)
        jobs = {'jobs': {}}
        calls, snapshots = [], []
        def inventory(*args):
            ready = [key for key, job in jobs['jobs'].items() if job['state'] == 'queued']
            return {'runnable': ready, 'deferred': [], 'total': len(ready)}
        def produce(producer_id, command, timeout, results, queued, admission=None):
            calls.append(producer_id)
            status = behavior(producer_id, jobs, calls)
            item = status if isinstance(status, dict) else {'status': status}
            status = item['status']
            results.append({'producer': producer_id, **item})
            return status
        with contextlib.ExitStack() as stack:
            patches = {
                'producers': producer_set or [('capability-dependencies', [], 1), ('fresh', [], 1)],
                'policy': {'queue': {'target_ready': 3, 'ready_per_worker': 2, 'max_queued': 12}},
                'sync_jobs': (jobs, profiles), 'dispatch_one': jobs, 'load_jobs': jobs,
                'worker_availability': {'test': {w['id']: {'allowed': True} for w in workers}},
                'load_json': {'workers': workers}, 'load_worker_pauses': {'workers': {}},
                'source_problem': source_problem,
            }
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(m, name, return_value=value))
            stack.enter_context(mock.patch.object(m, 'queue_inventory', side_effect=inventory))
            stack.enter_context(mock.patch.object(m, 'run_producer', side_effect=produce))
            if burst_limits is not None:
                stack.enter_context(mock.patch.object(m, 'producer_burst_limit',
                    side_effect=lambda producer: burst_limits.get(producer, 1)))
            stack.enter_context(mock.patch.object(m, 'write_status', side_effect=lambda **s: snapshots.append(s)))
            stack.enter_context(mock.patch.object(m, 'dispatch_integration'))
            stack.enter_context(mock.patch.object(m, 'log'))
            m.run_once()
        return calls, snapshots[-1]

    def test_clean_source_advance_retries_ready_supply_before_slow_scan(self):
        def behavior(producer, jobs, calls):
            if producer == 'ready':
                if calls.count('ready') == 1:
                    return {'status': 'source_unavailable', 'reason': 'source changed during reviewed production'}
                key = 'new-' + str(len(jobs['jobs']))
                jobs['jobs'][key] = {'ticket_id': key, 'state': 'queued', 'work_type': 'engine'}
                return 'queued'
            return 'exhausted_supported_plan'
        calls, snapshot = self.run_refill_sweep(behavior, [('ready', [], 1), ('slow', [], 1)], {'ready': 12})
        self.assertEqual(calls[:2], ['ready', 'ready'])
        self.assertEqual(snapshot['queue']['runnable'], 12)
        self.assertLessEqual(len(calls), 14)

    def test_dependency_source_advance_retries_with_same_bounded_budget(self):
        def behavior(producer, jobs, calls):
            if calls.count('capability-dependencies') == 1:
                return {'status': 'source_unavailable',
                        'reason': 'canonical source changed during producer scan; retry on current source'}
            key = 'new-' + str(len(jobs['jobs']))
            jobs['jobs'][key] = {'ticket_id': key, 'state': 'queued', 'work_type': 'map'}
            return 'queued'
        calls, snapshot = self.run_refill_sweep(behavior,
            [('capability-dependencies', [], 1)], {'capability-dependencies': 24})
        self.assertEqual(snapshot['queue']['runnable'], 12)
        self.assertEqual(len(calls), 13)

    def test_source_retry_is_once_per_sweep_and_never_ignores_dirty_source(self):
        def behavior(producer, *_):
            return ({'status': 'source_unavailable', 'reason': 'source changed during reviewed production'}
                    if producer == 'ready' else 'exhausted_supported_plan')
        producers = [('ready', [], 1), ('slow', [], 1)]
        calls, _ = self.run_refill_sweep(behavior, producers, {'ready': 12})
        self.assertEqual(calls, ['ready', 'ready', 'slow'])
        calls, _ = self.run_refill_sweep(behavior, producers, {'ready': 12}, source_problem='dirty source')
        self.assertEqual(calls, ['ready', 'slow'])

    def test_source_retry_requires_budget_and_exact_race_evidence(self):
        m = load('factory-ng-controller')
        for budget, reason in [(1, 'source changed during reviewed production'), (3, 'source has uncommitted changes')]:
            with self.subTest(budget=budget, reason=reason), \
                 mock.patch.object(m, 'producer_burst_limit', return_value=12), \
                 mock.patch.object(m, 'source_problem', return_value=None), \
                 mock.patch.object(m, 'run_producer', return_value='source_unavailable') as run:
                results = [{'producer': 'ready', 'status': 'source_unavailable', 'reason': reason}]
                status, remaining = m.run_supply_producer('ready', [], 1, results, [], {}, budget, set())
                self.assertEqual(status, 'source_unavailable')
                self.assertEqual(remaining, budget - 1)
                run.assert_called_once()

    def test_drained_review_capacity_refills_before_next_slow_scan(self):
        def behavior(producer, jobs, calls):
            if producer == 'ready':
                if calls.count('ready') == 1:
                    jobs['jobs']['old'] = {'ticket_id': 'old', 'state': 'working', 'work_type': 'engine'}
                    return 'reviewed_harness_reserve_full'
                key = 'new-' + str(len(jobs['jobs']))
                jobs['jobs'][key] = {'ticket_id': key, 'state': 'queued', 'work_type': 'engine'}
                return 'queued'
            if producer == 'slow-one':
                jobs['jobs']['old']['state'] = 'completed'
            return 'exhausted_supported_plan'
        calls, snapshot = self.run_refill_sweep(behavior, [
            ('ready', [], 1), ('slow-one', [], 1), ('slow-two', [], 1)], {'ready': 12})
        self.assertEqual(calls[:3], ['ready', 'slow-one', 'ready'])
        self.assertNotIn('slow-two', calls)  # replenished queue reached its admission cap
        self.assertEqual(snapshot['queue']['runnable'], 12)
        self.assertLessEqual(len(calls), 15)  # ordinary twelve-slot + three-producer budget

    def test_unchanged_backpressure_does_not_repeat_ready_producer(self):
        def behavior(producer, jobs, calls):
            jobs['jobs']['old'] = {'ticket_id': 'old', 'state': 'working', 'work_type': 'engine'}
            return 'reviewed_harness_reserve_full' if producer == 'ready' else 'exhausted_supported_plan'
        calls, _ = self.run_refill_sweep(behavior, [
            ('ready', [], 1), ('slow-one', [], 1), ('slow-two', [], 1)], {'ready': 12})
        self.assertEqual(calls, ['ready', 'slow-one', 'slow-two'])

    def test_ready_reserve_precedes_slow_cohorts_without_starving_them_at_capacity(self):
        def behavior(producer, jobs, calls):
            if producer != 'ready':
                return 'no_retry_candidate'
            key = 'ticket-' + str(len(jobs['jobs']))
            jobs['jobs'][key] = {'ticket_id': key, 'state': 'queued', 'work_type': 'engine'}
            return 'queued'
        calls, snapshot = self.run_refill_sweep(behavior, [
            ('staged-five-card-trial', [], 1), ('context-retry-batch', [], 1), ('ready', [], 1)])
        self.assertEqual(calls[0], 'ready')
        self.assertEqual(snapshot['queue']['runnable'], 12)
        self.assertEqual(calls[-2:], ['staged-five-card-trial', 'context-retry-batch'])
        self.assertEqual(calls.count('staged-five-card-trial'), 1)
        self.assertEqual(calls.count('context-retry-batch'), 1)

    def test_pending_scan_continues_and_new_dependency_is_revisited_in_same_sweep(self):
        def behavior(producer, jobs, calls):
            if producer == 'fresh':
                return 'scan_pending' if calls.count('fresh') == 1 else 'exhausted_supported_plan'
            if calls.count(producer) == 2:
                jobs['jobs']['engine'] = {'ticket_id': 'engine', 'state': 'queued', 'work_type': 'engine'}
                return 'queued'
            return 'awaiting_dependency'
        calls, snapshot = self.run_refill_sweep(behavior)
        self.assertEqual(calls[:4], ['capability-dependencies', 'fresh'] * 2)
        self.assertEqual(snapshot['queue']['runnable'], 1)
        self.assertEqual(snapshot['queue']['target_ready'], 10)
        self.assertEqual(calls.count('fresh'), 2)

    def test_pending_scan_sweep_is_bounded_and_exhaustion_does_not_spin(self):
        calls, snapshot = self.run_refill_sweep(
            lambda producer, *_: 'scan_pending' if producer == 'fresh' else 'awaiting_dependency')
        self.assertEqual(len(calls), 14)  # twelve admission slots plus two producers
        self.assertEqual(snapshot['queue']['runnable'], 0)
        calls, _ = self.run_refill_sweep(
            lambda producer, *_: 'exhausted_supported_plan' if producer == 'fresh' else 'awaiting_dependency')
        self.assertEqual(calls, ['capability-dependencies', 'fresh'])

    def test_cached_projection_tracks_changes_and_retries_partial_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); path = root / 'receipt.json'; cache = ProducerCache(root / 'cache.db')
            path.write_text(json.dumps({'outcome': 'accepted', 'large_raw_output': 'ignored'}))
            self.assertIsNone(cache.file('demand', path, receipt_demand))
            path.write_text('')
            self.assertIsNone(cache.file('demand', path, receipt_demand))
            path.write_text(json.dumps({'ticket': {'id': 'map'}, 'capability_demand': {'key': 'tap'}}))
            self.assertEqual(cache.file('demand', path, receipt_demand)['capability_demand']['key'], 'tap')
            cache.close()
            cache = ProducerCache(root / 'cache.db')
            with mock.patch.object(Path, 'read_text', side_effect=AssertionError('unchanged source reread')):
                self.assertEqual(cache.file('demand', path, receipt_demand)['ticket']['id'], 'map')
            cache.close()

    def test_controller_receipt_cache_tracks_publication_replacement_and_removal(self):
        m = load('factory-ng-controller')
        with tempfile.TemporaryDirectory() as d:
            m.OPS = m.RUNS = Path(d)
            receipt = Path(d) / 'a.json'
            receipt.write_text('')
            self.assertEqual(m.observed_ticket_ids(), {})
            value = {'schema': 'factory.observation-receipt/v1',
                     'ticket': {'id': 'ticket:test/v1'}, 'outcome': 'accepted',
                     'large_raw_output': 'not retained'}
            receipt.write_text(json.dumps(value))
            self.assertEqual(m.observed_ticket_ids()['ticket:test/v1']['outcome'], 'accepted')
            with mock.patch.object(m, 'load_json', side_effect=AssertionError('unchanged receipt reread')):
                self.assertEqual(m.integrated_ticket_ids(), {})
                self.assertEqual(len(m.observed_ticket_ids()), 1)
            self.assertNotIn('large_raw_output', m._receipt_projection_cache[str(receipt)][1])
            value = {'schema': 'factory.integration-receipt/v1',
                     'parents': ['ticket:test/v1'], 'outcome': 'pushed_full_production_gate_green'}
            replacement = Path(d) / 'replacement'
            replacement.write_text(json.dumps(value)); replacement.replace(receipt)
            self.assertEqual(m.observed_ticket_ids(), {})
            self.assertIn('ticket:test/v1', m.integrated_ticket_ids())
            receipt.unlink()
            self.assertEqual(m.integrated_ticket_ids(), {})
            self.assertEqual(m._receipt_projection_cache, {})

    def test_version_lookup_uses_all_existing_versions_without_file_scan(self):
        m = load('factory-ng-produce-capability-dependency')
        with mock.patch.object(Path, 'glob', side_effect=AssertionError('directory rescan')):
            self.assertEqual(m.next_version('ticket:engine.tap/v1', {
                'old': {'id': 'ticket:engine.tap/v1'}, 'later': {'id': 'ticket:engine.tap/v7'},
                'other': {'id': 'ticket:engine.other/v99'}}), 'ticket:engine.tap/v8')

    def run_saturated(self, with_map):
        m = load('factory-ng-produce-capability-dependency')
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            root = Path(d); runs = root / 'runs'; tickets = root / 'tickets'
            runs.mkdir(); tickets.mkdir(); jobs = {}
            for i in range(6):
                parent = 'ticket:map.p%d/v1' % i; engine = 'ticket:engine.e%d/v1' % i
                (tickets / ('p%d.json' % i)).write_text(json.dumps({'id': parent, 'production': {}}))
                (tickets / ('e%d.json' % i)).write_text(json.dumps({'id': engine, 'production': {}}))
                (runs / ('r%d.json' % i)).write_text(json.dumps({'ticket': {'id': parent}, 'capability_demand': {'key': 'e%d' % i}}))
                jobs[engine] = {'state': 'completed' if with_map and i == 5 else 'parked'}
            (root / 'jobs.json').write_text(json.dumps({'jobs': jobs}))
            stack.enter_context(mock.patch.multiple(m, OPS=root, RUNS=runs, TICKETS=tickets, JOBS=root/'jobs.json'))
            for name, value in [('source_clean', True), ('source_revision', 'pinned'), ('engine_lane_likely_full', True), ('receipt_verdict', 'AMBIGUOUS')]:
                stack.enter_context(mock.patch.object(m, name, return_value=value))
            stack.enter_context(mock.patch.object(m, 'engine_identity', side_effect=lambda c: ('ticket:engine.' + c['key'] + '/v1', b'')))
            prepare = stack.enter_context(mock.patch.object(m, 'engine_successor', return_value={'id': 'ticket:engine.e0/v2', 'production': {}}))
            stack.enter_context(mock.patch.object(m, 'resumed_map', return_value=({'id': 'ticket:map.p5/v2'}, {'members': ['p5']})))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):m.main()
            return json.loads(out.getvalue()), prepare.call_count

    def test_saturated_engine_lane_reaches_map_without_preparing_engine_retries(self):
        result, calls = self.run_saturated(True)
        self.assertEqual(result['ticket_id'], 'ticket:map.p5/v2')
        self.assertEqual(calls, 0)

    def test_saturated_lane_prepares_only_one_fallback(self):
        result, calls = self.run_saturated(False)
        self.assertEqual(result['ticket_id'], 'ticket:engine.e0/v2')
        self.assertEqual(calls, 1)

    def test_reviewed_blocked_receipt_precedes_historical_demand_and_tags_child(self):
        m = load('factory-ng-produce-capability-dependency')
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            root = Path(d); runs = root / 'runs'; tickets = root / 'tickets'
            runs.mkdir(); tickets.mkdir()
            for prefix, parent in [('a', 'old'), ('z', 'review')]:
                (tickets / (parent + '.json')).write_text(json.dumps({'id': parent, 'production': {}}))
                (runs / (prefix + '.json')).write_text(json.dumps({'ticket': {'id': parent}, 'capability_demand': {'key': parent}}))
            jobs = {'review': {'state': 'blocked', 'attention_recovery': {'batch': 'test'}, 'receipt': 'runs/z.json'}}
            (root / 'jobs.json').write_text(json.dumps({'jobs': jobs}))
            stack.enter_context(mock.patch.multiple(m, OPS=root, RUNS=runs, TICKETS=tickets, JOBS=root/'jobs.json'))
            for name, value in [('source_clean', True), ('source_revision', 'pinned'), ('engine_lane_likely_full', True)]:
                stack.enter_context(mock.patch.object(m, name, return_value=value))
            stack.enter_context(mock.patch.object(m, 'engine_identity', side_effect=lambda c: ('ticket:engine.' + c['key'] + '/v1', b'')))
            prepare = stack.enter_context(mock.patch.object(m, 'prepare_engine', side_effect=lambda kind,parent,*args: {'ticket_id': 'child-'+parent, 'ticket': {'production': {}}}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):m.main()
            value = json.loads(out.getvalue())
            self.assertEqual(value['ticket_id'], 'child-review')
            self.assertEqual(value['ticket']['production']['attention_recovery_parent'], 'review')
            self.assertEqual(prepare.call_count, 1)

    def test_enabled_families_survive_a_truncated_historical_plan(self):
        m = load('factory-ng-produce-build-plan')
        with tempfile.TemporaryDirectory() as d:
            plan = Path(d) / 'plan.jsonl'
            plan.write_text('{"item":"verb_unmapped:damage","rank":1,"examples":[]}\n')
            rows = m.coverage_rows(plan)
            self.assertEqual(len(rows), len(m.VERB_EFFECT))
            self.assertEqual({r['item'] for r in rows}, {'verb_unmapped:' + v for v in m.VERB_EFFECT})
            self.assertEqual(m.VERB_EFFECT['fight'], 'fight')
            self.assertEqual(m.VERB_EFFECT['damage_by'], 'damage')
            self.assertNotIn('counter_unless', m.VERB_EFFECT)

    def test_fresh_scan_resumes_and_invalidates_on_revision_and_card_change(self):
        m = load('factory-ng-produce-build-plan')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); carddb = root / 'backend/data/carddb'; carddb.mkdir(parents=True)
            cards = {name: {'name': name, 'status': 'review', 'text': 'Tap.'} for name in ['A', 'B', 'C']}
            path = carddb / 'a.json'; path.write_text(json.dumps(cards))
            parser = mock.Mock(); parser.reparse_card.return_value = {'misses': [('unsupported', 'x')]}
            cache = ProducerCache(root / 'cache.db'); rows = [{'item': 'verb_unmapped:tap'}]
            with self.assertRaises(m.ScanPending):m.discover_fresh_example(root, parser, rows, {'tap': {}}, {}, cache, 'r1', 0)
            self.assertEqual(parser.reparse_card.call_args[0][0]['name'], 'A')
            with self.assertRaises(m.ScanPending):m.discover_fresh_example(root, parser, rows, {'tap': {}}, {}, cache, 'r1', 0)
            self.assertEqual(parser.reparse_card.call_args[0][0]['name'], 'B')
            self.assertIsNone(m.discover_fresh_example(root, parser, rows, {'tap': {}}, {}, cache, 'r1', 100))
            self.assertEqual(parser.reparse_card.call_count, 3)
            m.discover_fresh_example(root, parser, rows, {'tap': {}}, {}, cache, 'r1', 100)
            self.assertEqual(parser.reparse_card.call_count, 3)
            m.discover_fresh_example(root, parser, rows, {'tap': {}}, {}, cache, 'r2', 100)
            self.assertEqual(parser.reparse_card.call_count, 6)
            cards['B']['text'] = 'New text'; path.write_text(json.dumps(cards))
            parser.reparse_card.return_value = {'misses': [('verb_unmapped:tap', 'tap it')]}
            result = m.discover_fresh_example(root, parser, rows, {'tap': {}}, {}, cache, 'r2', 100)
            self.assertEqual(result[1], 'B')
            self.assertEqual(parser.reparse_card.call_count, 7)
            cache.close()

    def test_dispatch_continues_during_slow_producer_on_the_owning_thread(self):
        m = load('factory-ng-controller'); owner = threading.get_ident(); threads = []
        def dispatch(*args):threads.append(threading.get_ident());return {'jobs': {}}
        with mock.patch.object(m, 'dispatch_one', side_effect=dispatch), mock.patch.object(m, 'dispatch_integration') as integrate:
            result = m.producer_command([sys.executable, '-c', 'import time; time.sleep(.12); print("done")'], 3, [], [], .02)
        self.assertEqual(result.stdout.strip(), 'done')
        self.assertGreaterEqual(len(threads), 2)
        self.assertEqual(set(threads), {owner})
        self.assertEqual(integrate.call_count, len(threads))

    def test_timeout_still_bounds_producer_with_dispatch_ticks(self):
        m = load('factory-ng-controller')
        with mock.patch.object(m, 'dispatch_one'), mock.patch.object(m, 'dispatch_integration'):
            with self.assertRaises(subprocess.TimeoutExpired):
                m.producer_command([sys.executable, '-c', 'import time; time.sleep(5)'], .08, [], [], .02)

    def test_stop_during_production_does_not_publish_ticket(self):
        m = load('factory-ng-controller')
        with mock.patch.object(m, 'write_status'), mock.patch.object(m, 'producer_command', return_value=subprocess.CompletedProcess([], 0, '{"status":"ready"}', '')), mock.patch.object(m, 'stopping', True), mock.patch.object(m, 'persist_ready') as persist:
            self.assertEqual(m.run_producer('fixture', [], 1, [], []), 'stopping')
            persist.assert_not_called()


if __name__ == '__main__':unittest.main()
