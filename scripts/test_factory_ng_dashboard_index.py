"""Read-index parity, pagination, incremental updates and snapshot isolation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import factory_ng_dashboard_index as index


class DashboardIndexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="factory-ng-dashboard-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "state/index.sqlite3"
        for folder in ("docs/factory-ng/tickets", "docs/factory-ng/runs", "state"):
            (self.root / folder).mkdir(parents=True)
        self.write("state/factory-ng-jobs.json", {"jobs": {}})
        self.ticket = dict(schema="factory.ticket-spec/v1", id="map-one", parents=[], work_type="map", lifecycle="ready")
        self.write("docs/factory-ng/tickets/map-one.json", self.ticket)
        self.attempt = {"schema": "factory.observation-receipt/v1", "created_at": "2026-09-01T00:00:00Z",
                        "ticket": {"id": "map-one"}, "outcome": "accepted",
                        "model": {"profile": "test", "telemetry": {"input_tokens": 3, "cache_read_tokens": 99, "provider_cost_usd": None}},
                        "gates": [{"detail": "large evidence" * 10000}]}
        self.write("docs/factory-ng/runs/attempt.json", self.attempt)

    def write(self, path, value):
        (self.root / path).write_text(json.dumps(value))

    def refresh(self):
        return index.refresh(self.root, self.db)

    def query(self, **kwargs):
        return index.query(self.db, **kwargs)

    def test_test_queue_keeps_verification_fields_outside_paged_work_list(self):
        jobs = {str(i): dict(ticket_id=str(i), state='working', verification_resume=True,
                             verification_batch=True, pid=42, result_path='batch.json',
                             finished_at='2026-09-14T09:00:00Z', updated_at='2026-09-14T09:00:00Z')
                for i in range(95)}
        self.write('state/factory-ng-jobs.json', {'jobs': jobs})
        self.refresh()
        result = self.query(work_filter='attention', search='no-matching-ticket')
        self.assertEqual(result['jobs'], [])
        self.assertEqual(len(result['active_jobs']), 95)
        self.assertTrue(all(j['verification_resume'] and j['verification_batch'] and j['pid'] == 42
                            for j in result['active_jobs']))
        self.assertEqual(result['active_jobs'][0]['finished_at'], '2026-09-14T09:00:00Z')

    def test_projection_matches_legacy_without_embedding_gate_details(self):
        spec = importlib.util.spec_from_file_location("legacy_dashboard", Path(__file__).with_name("factory-ng-dashboard.py"))
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        legacy.ROOT = self.root
        legacy.TICKETS = self.root / "docs/factory-ng/tickets"
        legacy.RUNS = self.root / "docs/factory-ng/runs"
        self.refresh()
        result = self.query(attempts=True, focus="map-one")
        self.assertEqual(result["tickets"], list(legacy.ticket_specs().values()))
        receipt = result["attempts"][0]
        for key in ("outcome", "created_at", "profile", "telemetry", "receipt_path"):
            self.assertEqual(receipt[key], legacy.receipts()[0][key])
        self.assertNotIn("gates", receipt)
        self.assertLess(len(json.dumps(result)), 4000)
        self.assertEqual(self.query()["attempts"], [])

    def test_unchanged_artifacts_are_not_reparsed_and_changes_are_seen(self):
        self.refresh()
        with mock.patch.object(index, "project", side_effect=AssertionError("reparsed")):
            self.assertEqual(self.refresh()["changed"], 0)
        self.attempt["outcome"] = "gate_failed"
        self.write("docs/factory-ng/runs/attempt.json", self.attempt)
        self.assertEqual(self.refresh()["changed"], 1)
        self.assertEqual(self.query()["summary"]["accepted"], 0)

    def test_supersession_and_deletion_keep_historical_counts_honest(self):
        old = "docs/factory-ng/runs/old-integration.json"
        value = {"schema": "factory.integration-receipt/v1", "outcome": "full_gate_failed"}
        self.write(old, value)
        self.write("docs/factory-ng/runs/new-integration.json", dict(value, supersedes=old, outcome="pushed_full_production_gate_green"))
        self.refresh()
        self.assertEqual(self.query()["summary"]["integrations"], 1)
        self.assertEqual(self.query()["integrations"][0]["outcome"], "pushed_full_production_gate_green")
        (self.root / "docs/factory-ng/runs/new-integration.json").unlink()
        self.refresh()
        self.assertEqual(self.query()["integrations"][0]["outcome"], "full_gate_failed")

    def test_pages_counts_and_old_unresolved_failures(self):
        jobs = {f"job-{n:03}": dict(ticket_id=f"job-{n:03}", state="queued", updated_at="2026-09-01") for n in range(65)}
        jobs["old-failure"] = dict(ticket_id="old-failure", state="integration_failed", outcome="candidate_conflict", updated_at="2026-08-01")
        jobs["recovered"] = dict(ticket_id="recovered", state="completed", outcome="full_gate_failed")
        self.write("state/factory-ng-jobs.json", {"jobs": jobs})
        self.refresh()
        first, second = self.query(), self.query(jobs_offset=30)
        self.assertEqual(first["pages"]["jobs"]["total"], 65)
        self.assertEqual(len(first["jobs"]), 30)
        self.assertFalse({j["ticket_id"] for j in first["jobs"]} & {j["ticket_id"] for j in second["jobs"]})
        self.assertEqual(first["summary"]["problems"], 1)
        self.assertEqual(self.query(work_filter="attention")["jobs"][0]["ticket_id"], "old-failure")

    def test_graph_search_and_snapshot_isolation(self):
        self.write("docs/factory-ng/tickets/child.json", dict(self.ticket, id="child", parents=["map-one"]))
        self.refresh()
        result = self.query(focus="child", search="map-one")
        self.assertEqual({t["id"] for t in result["tickets"]}, {"map-one", "child"})
        self.assertEqual(self.query(search="' OR 1=1 --")["tickets"], [])
        writer = index.connect(self.db)
        try:
            writer.execute("DELETE FROM artifacts WHERE kind='attempt'")
            self.assertEqual(self.query()["summary"]["attempts"], 1)
            writer.commit()
            self.assertEqual(self.query()["summary"]["attempts"], 0)
        finally:
            writer.close()

    def test_replaced_failures_leave_current_count_but_remain_in_history(self):
        jobs = {
            'old': dict(ticket_id='old', state='integration_failed', outcome='full_gate_failed', superseded_by='next'),
            'next': dict(ticket_id='next', state='queued'),
            'other': dict(ticket_id='other', state='failed', outcome='infrastructure_failed', updated_at='2026-08-01')}
        self.write('state/factory-ng-jobs.json', {'jobs': jobs})
        self.refresh()
        self.assertEqual(self.query()['summary']['problems'], 1)
        self.assertEqual([j['ticket_id'] for j in self.query(work_filter='attention')['jobs']], ['other'])
        self.assertEqual(len(self.query(work_filter='recent')['jobs']), 3)
        jobs['next'].update(state='failed', outcome='infrastructure_failed_model_protocol')
        self.write('state/factory-ng-jobs.json', {'jobs': jobs})
        self.refresh()
        self.assertEqual(self.query()['summary']['problems'], 2)

    def test_failure_diagnostics_and_repair_budget_survive_projection(self):
        path = "docs/factory-ng/runs/integration.json"
        self.write(path, {"schema": "factory.integration-receipt/v1", "outcome": "full_gate_failed",
            "reason": "focused-go failed", "gates": [{"id": "focused-go", "outcome": "failed",
            "detail": '--- FAIL: TestVocabularyClosedOverCardDB\nUNREGISTERED effect "tap_choice"\n' + "noise\n" * 1000}]})
        job = dict(ticket_id="map-one", state="integration_failed", outcome="full_gate_failed",
                   integration_receipt=path, attempts=1, integration_attempts=2,
                   repair_blocker={"reason": "Map repair limit reached (2/2)"})
        self.write("state/factory-ng-jobs.json", {"jobs": {"map-one": job}})
        self.refresh()
        result = self.query(work_filter="attention")
        row = result["jobs"][0]
        self.assertIn('UNREGISTERED effect "tap_choice"', row["failure"]["detail"])
        self.assertNotIn("noise", row["failure"]["detail"])
        self.assertEqual(row["repair_blocker"], job["repair_blocker"])
        self.assertEqual(row["integration_attempts"], 2)
        self.assertEqual(result["summary"]["integration_failures"], 1)
        self.assertEqual(result["summary"]["worker_failures"], 0)

    def test_excluded_candidate_does_not_inherit_another_candidates_gate_failure(self):
        path = "docs/factory-ng/runs/wave.json"
        self.write(path, {"schema": "factory.integration-receipt/v1", "outcome": "full_gate_failed",
            "gates": [{"id": "focused-go", "outcome": "failed", "detail": "unrelated failure"}],
            "excluded_candidates": {"map-one": {"outcome": "candidate_conflict",
                "gates": [{"id": "candidate-apply", "outcome": "failed", "detail": "CONFLICT in reparse.py"}]}}})
        self.write("state/factory-ng-jobs.json", {"jobs": {"map-one": dict(ticket_id="map-one",
            state="integration_failed", outcome="candidate_conflict", integration_receipt=path)}})
        self.refresh()
        failure = self.query(work_filter="attention")["jobs"][0]["failure"]
        self.assertEqual(failure["gate"], "candidate-apply")
        self.assertNotIn("unrelated", failure["detail"])

    def test_no_receipt_job_keeps_reason_and_stale_receipt_is_not_a_current_diagnostic(self):
        self.write("state/factory-ng-jobs.json", {"jobs": {"map-one": dict(ticket_id="map-one",
            state="failed", outcome="infrastructure_failed", started_at="2026-09-02T00:00:00Z",
            receipt="docs/factory-ng/runs/attempt.json", reason="worker exited without a result", attempts=3)}})
        self.refresh()
        row = self.query(work_filter="attention")["jobs"][0]
        self.assertNotIn("failure", row)
        self.assertEqual(row["reason"], "worker exited without a result")
        self.assertEqual(row["attempts"], 3)

    def test_projection_upgrade_and_receipt_change_refresh_diagnostics(self):
        self.write("state/factory-ng-jobs.json", {"jobs": {"map-one": dict(ticket_id="map-one",
            state="failed", outcome="infrastructure_failed", receipt="docs/factory-ng/runs/attempt.json")}})
        self.refresh()
        writer = index.connect(self.db)
        with writer:
            writer.execute("DELETE FROM meta WHERE key='projection_version'")
        writer.close()
        self.assertGreater(self.refresh()["changed"], 0)
        self.attempt.update(gates=[dict(id="provider-call", outcome="failed", detail="provider unavailable")])
        self.write("docs/factory-ng/runs/attempt.json", self.attempt)
        self.refresh()
        self.assertEqual(self.query(work_filter="attention")["jobs"][0]["failure"]["detail"], "provider unavailable")

    def test_repaired_initial_patch_failure_is_not_the_current_failure(self):
        failure = index.failure_summary({"gates": [
            dict(id="initial-patch-apply", outcome="failed", detail="historical apply"),
            dict(id="patch-apply", outcome="passed"),
            dict(id="ticket-gate-0", outcome="failed", detail="AssertionError: final candidate") ]})
        self.assertEqual(failure["gate"], "ticket-gate-0")
        self.assertIn("final candidate", failure["detail"])

    def test_invalid_artifacts_visible_and_raw_transport_logs_ignored(self):
        self.refresh()
        (self.root / "docs/factory-ng/runs/attempt.json").write_text("partial")
        (self.root / "docs/factory-ng/runs/provider.raw.json").write_text("not json")
        self.refresh()
        result = self.query()
        self.assertEqual(result["summary"]["attempts"], 1)
        self.assertEqual(result["invalid_files"], ["docs/factory-ng/runs/attempt.json"])


if __name__ == "__main__":
    unittest.main()
