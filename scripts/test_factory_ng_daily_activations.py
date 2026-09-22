import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('daily', Path(__file__).with_name('factory-ng-daily-activations.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class DailyActivationsTest(unittest.TestCase):
    def test_midnight_boundaries_idle_days_and_today(self):
        now = dt.datetime(2026, 9, 12, 12, tzinfo=dt.timezone.utc)
        ts = lambda day, hour=0: int(dt.datetime(2026, 9, day, hour, tzinfo=dt.timezone.utc).timestamp())
        commits = [('today', ts(12, 10)), ('midnight', ts(11)), ('old', ts(8))]
        counts = {'today': 25, 'midnight': 30, 'old': 10}
        rows = m.daily_rows(commits, now, 3, counts.__getitem__)
        self.assertEqual([r['net_activated'] for r in rows], [0, 0, 20, -5])
        self.assertEqual([r['partial_day'] for r in rows], [False, False, False, True])

    def test_missing_baseline_is_unknown_not_zero(self):
        now = dt.datetime(2026, 9, 12, 12, tzinfo=dt.timezone.utc)
        rows = m.daily_rows([('only', int(now.timestamp())-3600)], now, 2, lambda sha: 5)
        self.assertTrue(all(r['net_activated'] is None for r in rows))

    def test_git_snapshot_ignores_dirty_checkout_and_reuses_blob_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);db=repo/'backend/data/carddb';db.mkdir(parents=True)
            shard=db/'a.json';shard.write_text(json.dumps({'A': {'status':'auto'}, 'B':{'status':'review'}},indent=2))
            (db/'_handlers.json').write_text('{"ignored":{"status":"auto"}}')
            def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
            git('init','-q');git('add','.');git('-c','user.name=Test','-c','user.email=test@local','commit','-qm','first')
            head=git('rev-parse','HEAD');cache={}
            self.assertEqual(m.auto_count(repo,head,cache),1)
            shard.write_text('{}')
            original=m.git
            def no_blob(repo,*args):
                self.assertNotIn('cat-file',args)
                return original(repo,*args)
            with mock.patch.object(m,'git',side_effect=no_blob):self.assertEqual(m.auto_count(repo,head,cache),1)

    def test_thresholds_missing_causes_and_partial_day(self):
        for value,expected in [(99,'below_target'),(100,'on_target'),(149,'on_target'),(150,'high')]:
            r=m.explain_day({'net_activated':value,'partial_day':False},{},[])
            self.assertEqual(r['category'],expected)
        self.assertIn('do not establish',m.explain_day({'net_activated':15,'partial_day':False},{},[])['text'])
        r=m.explain_day({'net_activated':15,'partial_day':True},{'producer_errors':3},[])
        self.assertEqual(r['category'],'in_progress');self.assertIn('not assessed',r['text'])

    def test_high_day_attribution_and_documented_context(self):
        waves=[{'revision':'a'*40,'net_activated':215},{'revision':'b'*40,'net_activated':176}]
        r=m.explain_day({'net_activated':391,'partial_day':False},{},waves,{'text':'Documented recovery.','source':'review.md'})
        self.assertIn('+215',r['text']);self.assertIn('Documented recovery.',r['evidence'])
        self.assertEqual(r['largest_imports'][0]['revision'],'a'*40)

    def test_log_signals_do_not_treat_exhausted_repairs_as_exhausted_fresh_supply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); log=root/'controller'; watchdog=root/'watchdog'
            log.write_text('[2026-09-10T00:00:00Z] producer=build-plan-paid-repair status=exhausted_supported_plan ticket=-\n'
                '[2026-09-10T00:01:00Z] producer=build-plan-fresh-local status=exhausted_supported_plan ticket=-\n')
            watchdog.write_text('partial json\n'+json.dumps({'checked_at':'2026-09-10T00:00:00Z','active':False})+'\n')
            signals=m.operational_signals(log,watchdog)['2026-09-10']
            self.assertEqual(signals['fresh_exhausted'],1);self.assertEqual(signals['idle_samples'],1)

    def test_import_attribution_ignores_metadata_and_caches_commits(self):
        log = b"abc 1788177600\n"
        patch = b'''diff --git a/backend/data/carddb/_handlers.json b/backend/data/carddb/_handlers.json
+    "status": "auto",
diff --git a/backend/data/carddb/a.json b/backend/data/carddb/a.json
-    "status": "review",
+    "status": "auto",
'''
        cache = {}
        with mock.patch.object(m, 'git', side_effect=[log, patch]) as call:
            result = m.activation_waves(Path('.'), 'head', '2026-08-29', cache)
            self.assertEqual(sum(w['net_activated'] for rows in result.values() for w in rows), 1)
            self.assertEqual(call.call_count, 2)
        with mock.patch.object(m, 'git', return_value=log) as call:
            self.assertEqual(m.activation_waves(Path('.'), 'head', '2026-08-29', cache), result)
            self.assertEqual(call.call_count, 1)


if __name__=='__main__':unittest.main()
