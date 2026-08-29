#!/usr/bin/env python3
"""Deterministic control-plane tests for Factory NG policy wiring."""
import datetime
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]


class FactoryNGControlTest(unittest.TestCase):
    def run_gate(self, script, function, cache_env, cache_value, off_env):
        with tempfile.TemporaryDirectory(prefix="factory-ng-pace-test-") as directory:
            cache = Path(directory) / "usage.json"
            cache.write_text(json.dumps(cache_value))
            env = os.environ.copy()
            env.update({cache_env: str(cache), off_env: str(Path(directory) / "off"),
                        "USAGE_GATE_TTL": "86400", "CODEX_USAGE_GATE_TTL": "86400"})
            return subprocess.run(
                ["bash", "-c", 'source "$1"; "$2"', "test", str(OPS / script), function],
                env=env, capture_output=True, text=True,
            ).returncode

    def test_claude_day_one_stops_at_fourteen_percent(self):
        reset = time.time() + 604800 - 3600
        iso = datetime.datetime.fromtimestamp(reset, datetime.timezone.utc).isoformat()
        base = {"five_hour": {"utilization": 0, "resets_at": iso},
                "seven_day": {"utilization": 13, "resets_at": iso}}
        self.assertEqual(self.run_gate("scripts/lib-pace-gate.sh", "pace_ok",
                                      "USAGE_CACHE", base, "PACE_OFF_FILE"), 0)
        base["seven_day"]["utilization"] = 14
        self.assertEqual(self.run_gate("scripts/lib-pace-gate.sh", "pace_ok",
                                      "USAGE_CACHE", base, "PACE_OFF_FILE"), 1)

    def test_codex_day_one_stops_at_fourteen_percent(self):
        reset = int(time.time() + 604800 - 3600)
        base = {"used_pct": 13, "resets_at": reset, "window_mins": 10080}
        self.assertEqual(self.run_gate("scripts/lib-pace-gate-codex.sh", "pace_ok_codex",
                                      "CODEX_USAGE_CACHE", base, "CODEX_PACE_OFF_FILE"), 0)
        base["used_pct"] = 14
        self.assertEqual(self.run_gate("scripts/lib-pace-gate-codex.sh", "pace_ok_codex",
                                      "CODEX_USAGE_CACHE", base, "CODEX_PACE_OFF_FILE"), 1)

    def test_runtime_policy_has_safe_push_deploy_split(self):
        policy = json.loads((OPS / "config/factory-ng-policy.json").read_text())
        self.assertTrue(policy["integration"]["automatic"])
        self.assertTrue(policy["integration"]["push_when_full_gate_green"])
        self.assertFalse(policy["integration"]["deploy_after_push"])
        self.assertEqual(policy["retry"]["infrastructure_attempts"], 3)

    def test_every_worker_has_known_usage_policy(self):
        workers = json.loads((OPS / "config/factory-ng-workers.json").read_text())["workers"]
        self.assertEqual({item["usage_policy"] for item in workers},
                         {"unmetered", "claude-weekly", "codex-weekly"})

    def test_enqueue_rejects_incomplete_ticket(self):
        result = subprocess.run(["python3", str(OPS / "scripts/factory-ng-enqueue.py")],
                                input='{"schema":"factory.ticket-spec/v1"}', text=True,
                                capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
