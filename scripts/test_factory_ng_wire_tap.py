"""Wire tap tests: inert when off, correlated when on, self-expiring, quota-free."""
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import factory_ng_wire_tap as tap


class TapSwitchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wiretap-test-"))
        self.switch = self.tmp / "state" / "factory-ng-wire-tap.json"
        self.dir = self.tmp / "state" / "wire-tap"
        patch = mock.patch.object(tap, "SWITCH", self.switch)
        patch.start()
        self.addCleanup(patch.stop)
        patch2 = mock.patch.object(tap, "DEFAULT_DIR", self.dir)
        patch2.start()
        self.addCleanup(patch2.stop)
        tap._state_cache.update({"mtime": None, "config": None})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_absent_switch_means_off(self):
        self.assertFalse(tap.enabled())
        self.assertIsNone(tap.record("request", prompt="x"))
        self.assertFalse(self.dir.exists())

    def test_disabled_switch_means_off(self):
        self.switch.parent.mkdir(parents=True, exist_ok=True)
        self.switch.write_text(json.dumps({"enabled": False}))
        self.assertFalse(tap.enabled())

    def test_enable_records_a_correlated_round_trip(self):
        tap.enable(minutes=5, directory=self.dir)
        self.assertTrue(tap.enabled())
        call = tap.call_id()
        tap.record("request", call_id=call, prompt="PROMPT BODY", prompt_bytes=11)
        tap.record("response", call_id=call, raw='{"result":"ANSWER"}', raw_bytes=20)
        tap.record("summary", call_id=call, exit=0, duration_ms=1234)
        rows = tap.by_call(call)
        self.assertEqual([r["event"] for r in rows], ["request", "response", "summary"])
        self.assertEqual({r["call_id"] for r in rows}, {call})
        self.assertEqual(rows[0]["prompt"], "PROMPT BODY")

    def test_expired_switch_reports_off_and_persists_disable(self):
        cfg = tap.enable(minutes=5, directory=self.dir)
        cfg["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        self.switch.write_text(json.dumps(cfg))
        tap._state_cache.update({"mtime": None, "config": None})
        self.assertFalse(tap.enabled())
        self.assertFalse(json.loads(self.switch.read_text())["enabled"])
        self.assertIn("expired", json.loads(self.switch.read_text())["disabled_reason"])

    def test_disk_budget_disables_the_tap(self):
        tap.enable(minutes=5, directory=self.dir, max_total_bytes=100)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "wire-older.jsonl").write_text("x" * 500)
        self.assertTrue(tap.enabled())  # the budget is only checked when writing
        tap.record("request", prompt="should not land")
        self.assertFalse(tap.enabled())  # auto-disabled once over budget
        self.assertEqual(len(list(self.dir.glob("wire-*.jsonl"))), 1)
        self.assertIn("budget", json.loads(self.switch.read_text())["disabled_reason"])

    def test_ticket_filter_only_keeps_matching_tickets(self):
        tap.enable(minutes=5, directory=self.dir, ticket="ticket:map.frontier-42/v1")
        with mock.patch.dict(os.environ, {"KB_TICKET": "ticket:map.other-99/v1"}):
            self.assertIsNone(tap.record("request", prompt="nope"))
        with mock.patch.dict(os.environ, {"KB_TICKET": "ticket:map.frontier-42/v1"}):
            self.assertIsNotNone(tap.record("request", prompt="yes"))
        landed = [json.loads(line)
                 for line in next(self.dir.glob("wire-*.jsonl")).read_text().splitlines()]
        self.assertEqual(len(landed), 1)
        self.assertEqual(landed[0]["prompt"], "yes")

    def test_record_never_raises_into_the_worker(self):
        tap.enable(minutes=5, directory=self.dir)
        with mock.patch.object(tap, "tap_dir", side_effect=RuntimeError("boom")):
            self.assertIsNone(tap.record("request", prompt="still fine"))
        self.assertTrue(tap.enabled())

    def test_clip_keeps_head_and_tail_and_marks_the_omission(self):
        text = "A" * 5000
        clipped = tap.clip(text, 1000)
        self.assertLess(len(clipped), 1200)
        self.assertIn("clipped", clipped)
        self.assertTrue(clipped.startswith("AAA"))
        self.assertTrue(clipped.endswith("AAA"))

    def test_human_line_is_readable(self):
        line = tap.human({"ts": "2026-09-22T19:42:17Z", "event": "request",
                         "engine": "claude", "model": "claude-sonnet-5",
                         "call_id": "c1", "prompt_bytes": 64606,
                         "prompt_sha256": "b8363d6ae884" * 4})
        self.assertIn("19:42:17", line)
        self.assertIn("claude/claude-sonnet-5", line)
        self.assertIn("prompt=64606", line)


class ModelCallTapIntegrationTests(unittest.TestCase):
    """The tap must tee the prompt and replay it, so no engine path changes."""

    def setUp(self):
        import model_call
        self.model_call = model_call
        model_call.TAP.update({"call_id": None, "started": None, "spawns": 0,
                              "real_run": None})
        self.tmp = Path(tempfile.mkdtemp(prefix="wiretap-mc-"))
        self.records = []
        patch = mock.patch.object(model_call, "wire_tap")
        self.fake = patch.start()
        self.addCleanup(patch.stop)
        self.fake.enabled.return_value = False
        self.fake.record.side_effect = lambda event, **kw: self.records.append(
            dict(event=event, **kw))
        self.fake.call_id.return_value = "mc-call-1"
        self.fake.clip.side_effect = lambda text, limit=400000: text
        self.addCleanup(model_call.uninstall_wire_tap)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _set_stdin(self, text):
        import sys
        wrapper = io.TextIOWrapper(io.BytesIO(text.encode()), encoding="utf-8")
        patch = mock.patch.object(sys, "stdin", wrapper)
        patch.start()
        self.addCleanup(patch.stop)
        return wrapper

    def test_tap_off_leaves_stdin_untouched(self):
        wrapper = self._set_stdin("ORIGINAL PROMPT")
        self.model_call.install_wire_tap("claude", "claude-sonnet-5", "engine")
        self.assertFalse(self.model_call.TAP["call_id"])
        self.assertEqual(wrapper.read(), "ORIGINAL PROMPT")
        self.fake.record.assert_not_called()

    def test_tap_on_records_request_and_replays_identical_bytes(self):
        import sys
        self.fake.enabled.return_value = True
        self._set_stdin("PROMPT THAT MUST SURVIVE\nsecond line\n")
        self.model_call.install_wire_tap("claude", "claude-sonnet-5", "engine")
        seen = sys.stdin.read()
        self.assertEqual(seen, "PROMPT THAT MUST SURVIVE\nsecond line\n")
        self.assertEqual(self.model_call.TAP["call_id"], "mc-call-1")
        events = [r["event"] for r in self.records]
        self.assertIn("request", events)
        request = self.records[0]
        self.assertEqual(request["prompt"], "PROMPT THAT MUST SURVIVE\nsecond line\n")
        self.assertEqual(request["prompt_bytes"], 37)
        self.assertEqual(len(request["prompt_sha256"]), 64)

    def test_tap_on_records_provider_argv_via_spawn(self):
        import subprocess, sys
        self.fake.enabled.return_value = True
        self._set_stdin("P")
        self.model_call.install_wire_tap("claude", "claude-sonnet-5", "engine")
        self.assertEqual(sys.stdin.read(), "P")
        subprocess.run(["/bin/true"], capture_output=True)
        spawns = [r for r in self.records if r["event"] == "spawn"]
        self.assertEqual(len(spawns), 1)
        self.assertEqual(spawns[0]["argv"], ["/bin/true"])
        self.assertEqual(spawns[0]["call_id"], "mc-call-1")

    def test_uninstall_restores_subprocess_run(self):
        import subprocess, sys
        self.fake.enabled.return_value = True
        self._set_stdin("P")
        self.model_call.install_wire_tap("claude", "claude-sonnet-5", "engine")
        traced = subprocess.run
        self.model_call.uninstall_wire_tap()
        self.assertIsNot(subprocess.run, traced)
        self.assertIsNone(self.model_call.TAP["real_run"])
        self.assertEqual(subprocess.run(["/bin/echo", "clean"],
                                       capture_output=True).stdout, b"clean\n")

    def test_save_raw_records_the_response_under_the_same_call(self):
        import sys
        self.fake.enabled.return_value = True
        self._set_stdin("P")
        self.model_call.install_wire_tap("claude", "claude-sonnet-5", "engine")
        sys.stdin.read()
        with mock.patch.dict(os.environ, {"PIPE_RAW_ARTIFACT": str(self.tmp / "raw.json")}):
            self.model_call.save_raw({"result": "ANSWER"})
        responses = [r for r in self.records if r["event"] == "response"]
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["call_id"], "mc-call-1")
        self.assertIn("ANSWER", responses[0]["raw"])

    def test_summary_carries_exit_code_and_answer(self):
        import sys
        self.fake.enabled.return_value = True
        self._set_stdin("P")
        self.model_call.install_wire_tap("claude", "claude-sonnet-5", "engine")
        sys.stdin.read()
        self.model_call.tap_summary(0, "FINAL ANSWER")
        summary = [r for r in self.records if r["event"] == "summary"][0]
        self.assertEqual(summary["exit"], 0)
        self.assertEqual(summary["answer"], "FINAL ANSWER")
        self.assertEqual(summary["stdout_bytes"], len("FINAL ANSWER"))

    def test_missing_tap_module_does_not_break_the_call(self):
        import sys
        with mock.patch.object(self.model_call, "wire_tap", None):
            wrapper = self._set_stdin("STILL WORKS")
            self.model_call.install_wire_tap("claude", "m", "map")
            self.assertEqual(wrapper.read(), "STILL WORKS")
            self.model_call.save_raw("x")
            self.model_call.tap_summary(0, "x")


if __name__ == "__main__":
    unittest.main()
