#!/usr/bin/env python3
"""Tests that the daily mail uses the dashboard's definitions."""
import datetime as dt
import importlib.util
import unittest
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "factory_ng_daily_report", OPS / "scripts/factory-ng-daily-report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class FactoryNGDailyReportTest(unittest.TestCase):
    def test_summary_uses_card_delta_and_only_unresolved_failures_for_health(self):
        now = dt.datetime(2026, 8, 31, 8, 0, tzinfo=dt.timezone.utc)
        snapshot = {
            "cards": {"current": {"corpus_total": 100, "corpus_classified": 90,
                                    "imported": 80, "auto": 44, "review": 35, "manual": 1},
                      "change_24h": {"imported": 0, "auto": 4, "review": -4, "manual": 0}},
            "status": {"state": "running", "active": [{"id": "producer", "kind": "producer"}],
                       "queue": {"runnable": 2, "deferred": 1},
                       "cache_maintenance": {"state": "idle", "cache_path": "/cache"}},
            "data": {
                "tickets": [{}, {}],
                "attempts": [
                    {"created_at": "2026-08-31T07:00:00Z", "outcome": "accepted_candidate"},
                    {"created_at": "2026-08-31T07:10:00Z", "outcome": "gate_failed"},
                    {"created_at": "2026-08-31T07:20:00Z", "outcome": "infrastructure_failed_model_protocol"},
                ],
                "integrations": [{"created_at": "2026-08-31T07:30:00Z",
                                  "outcome": "pushed_full_production_gate_green"}],
                "jobs": [
                    {"state": "working"},
                    # A retried infrastructure attempt is not a current red failure.
                    {"state": "queued", "outcome": "infrastructure_failed_model_protocol",
                     "updated_at": "2026-08-31T07:40:00Z"},
                ],
            },
            "limits": {}, "errors": [],
        }
        value = report.summarize(snapshot, now)
        self.assertEqual(value["health"], "OK")
        self.assertEqual(value["metrics"], {
            "enabled": 44, "enabled_delta_24h": 4, "running": 2,
            "accepted_24h": 1, "integrations_24h": 1, "system_problems": 0,
        })
        self.assertIn("Not accepted by gate:  1  (expected decisions, not system failures)",
                      value["body"])

    def test_terminal_recent_infrastructure_failure_marks_review(self):
        now = dt.datetime(2026, 8, 31, 8, 0, tzinfo=dt.timezone.utc)
        snapshot = {"cards": {}, "status": {"state": "running"}, "limits": {}, "errors": [],
                    "data": {"attempts": [], "integrations": [], "tickets": [], "jobs": [
                        {"state": "failed", "outcome": "full_gate_failed",
                         "updated_at": "2026-08-31T07:30:00Z"},
                    ]}}
        value = report.summarize(snapshot, now)
        self.assertEqual(value["health"], "REVIEW")
        self.assertEqual(value["metrics"]["system_problems"], 1)


if __name__ == "__main__":
    unittest.main()
