#!/usr/bin/env python3
"""Deterministic control-plane tests for Factory NG policy wiring."""
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import contextlib
import io
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path
from factory_ng_paths import SOURCE


OPS = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, OPS / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def by_profile_of(mapping):
    """Build a `configured_workers_by_profile`-shaped {profile: [worker, ...]}
    fixture from a terse {profile: worker_dict} mapping (one worker per profile)."""
    return {profile: [worker] for profile, worker in mapping.items()}


def availability_of(workers, flat):
    """Expand a terse {profile: {"allowed": ..., "detail": ...}} fixture into the
    real {profile: {worker_id: {...}}} shape `worker_availability` returns, using
    `workers` (a `configured_workers_by_profile`-shaped by_profile) for worker ids."""
    out = {}
    for profile, entry in flat.items():
        leases = workers.get(profile, [])
        out[profile] = ({(w.get("id") or profile): entry for w in leases} if leases
                         else {profile: entry})
    return out


class FactoryNGControlTest(unittest.TestCase):
    def test_all_workers_pace_paused_is_a_scheduled_supply_pause(self):
        controller = load_script('factory_ng_controller_pace_pause_test', 'factory-ng-controller.py')
        workers = {
            'claude-staged@1.0.0': [{'id': 'claude', 'profile': 'claude-staged@1.0.0'}],
            'codex-constrained@1.1.0': [{'id': 'codex', 'profile': 'codex-constrained@1.1.0'}],
        }
        paused = availability_of(workers, {
            'claude-staged@1.0.0': {'allowed': False, 'detail': 'PACE-PAUSE bis 20:00 CEST'},
            'codex-constrained@1.1.0': {'allowed': False, 'detail': 'PACE-PAUSE bis 19:18 UTC'},
        })
        self.assertTrue(controller.all_workers_pace_paused(workers, paused))
        paused['codex-constrained@1.1.0']['codex']['detail'] = 'authentication paused'
        self.assertFalse(controller.all_workers_pace_paused(workers, paused))

    def test_producer_burst_is_opt_in_and_bounded(self):
        controller = load_script('bounded_refill', 'factory-ng-controller.py')
        with mock.patch.object(controller, 'load_json', return_value={'producers': [
                {'id': 'normal'}, {'id': 'fast', 'refill_burst': 12},
                {'id': 'too-many', 'refill_burst': 1000}, {'id': 'bad', 'refill_burst': '12'}]}):
            for key, expected in [('normal', 1), ('fast', 12), ('too-many', 24), ('bad', 1), ('absent', 1)]:
                self.assertEqual(controller.producer_burst_limit(key), expected)

    def test_reviewed_capacity_fallback_cannot_dispatch_to_rejected_model(self):
        controller = load_script('capacity_fallback_model', 'factory-ng-controller.py')
        job = {'work_type': 'engine', 'attempts': 2, 'attention_recovery': {
            'previous_attempts': 2, 'required_model': 'fallback'}}
        with mock.patch.object(controller, 'worker_supports', return_value=True):
            self.assertFalse(controller.worker_supports_job({'model': 'old'}, job))
            self.assertTrue(controller.worker_supports_job({'model': 'fallback'}, job))
    def test_codex_worker_is_offline_but_keeps_local_shell_capability(self):
        model_call = load_script("factory_ng_model_call_offline_test", "model_call.py")
        command = model_call.codex_exec_command("gpt-test", 900)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("read-only", command)
        self.assertIn('web_search="disabled"', command)
        disabled = {command[index + 1] for index, value in enumerate(command[:-1])
                    if value == "--disable"}
        self.assertTrue({"apps", "browser_use", "browser_use_external",
                         "computer_use", "image_generation", "plugins",
                         "remote_plugin", "skill_mcp_dependency_install"}.issubset(disabled))
        # These are the local capabilities the Factory profile relies on.
        self.assertNotIn("shell_tool", disabled)
        self.assertNotIn("unified_exec", disabled)
        self.assertEqual(command[-2:], ["-m", "gpt-test"])

    def test_openrouter_cooldown_uses_1_3_5_minute_stages_and_resets(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-openrouter-cooldown-") as directory:
            state = Path(directory) / "cooldown.json"
            with mock.patch.dict(os.environ, {"OPENROUTER_COOLDOWN_STATE": str(state)}):
                cooldown = load_script("factory_ng_openrouter_cooldown_test", "openrouter_cooldown.py")
                first = cooldown.record_rate_limit("model-a", now_epoch=100)
                second = cooldown.record_rate_limit("model-a", now_epoch=200)
                third = cooldown.record_rate_limit("model-b", now_epoch=400)
                capped = cooldown.record_rate_limit("model-b", now_epoch=800)
                self.assertEqual(
                    [(first["cooldown_seconds"], first["paused_until_epoch"]),
                     (second["cooldown_seconds"], second["paused_until_epoch"]),
                     (third["cooldown_seconds"], third["paused_until_epoch"]),
                     (capped["cooldown_seconds"], capped["paused_until_epoch"])],
                    [(60, 160), (180, 380), (300, 700), (300, 1100)],
                )
                stale = cooldown.record_success(request_started_epoch=750, now_epoch=810)
                self.assertFalse(stale["allowed"])
                reset = cooldown.record_success(request_started_epoch=801, now_epoch=810)
                self.assertTrue(reset["allowed"])
                self.assertEqual(reset["consecutive_429s"], 0)

    def test_openrouter_cooldown_holds_worker_and_rate_limit_refunds_once(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-openrouter-worker-") as directory:
            state = Path(directory) / "cooldown.json"
            with mock.patch.dict(os.environ, {"OPENROUTER_COOLDOWN_STATE": str(state)}):
                cooldown = load_script("factory_ng_openrouter_cooldown_worker_test", "openrouter_cooldown.py")
                controller = load_script("factory_ng_controller_openrouter_test", "factory-ng-controller.py")
                cooldown.record_rate_limit("minimax/minimax-m3:free")
                allowed, detail = controller.usage_gate({"usage_policy": "openrouter-cooldown"})
                self.assertFalse(allowed)
                self.assertIn("429 stage 1", detail)
                job = {"attempts": 2}
                self.assertTrue(controller.refund_rate_limit_attempt(job, "receipt.json"))
                self.assertFalse(controller.refund_rate_limit_attempt(job, "receipt.json"))
                self.assertEqual(job["attempts"], 1)

    def test_openrouter_direct_call_records_429_and_exits_rate_limited(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-openrouter-call-") as directory:
            state = Path(directory) / "cooldown.json"
            environment = {"OPENROUTER_COOLDOWN_STATE": str(state),
                           "OPENROUTER_API_KEY": "test-key"}
            with mock.patch.dict(os.environ, environment):
                model_call = load_script("factory_ng_model_call_429_test", "model_call.py")
                error = model_call.urllib.error.HTTPError(
                    "https://openrouter.ai/api/v1/chat/completions", 429,
                    "Too Many Requests", {}, io.BytesIO(b'{"error":"limited"}'))
                with mock.patch.object(model_call.sys, "stdin", io.StringIO("test prompt")), \
                     mock.patch.object(model_call.urllib.request, "urlopen", side_effect=error), \
                     self.assertRaises(SystemExit) as raised:
                    model_call.call_openrouter("minimax/minimax-m3:free", "map")
                self.assertEqual(raised.exception.code, model_call.OPENROUTER_RATE_LIMIT_EXIT)
                value = json.loads(state.read_text())
                self.assertEqual(value["consecutive_429s"], 1)
                self.assertEqual(value["cooldown_seconds"], 60)

    def test_openrouter_direct_call_without_key_is_refundable_auth_failure(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            model_call = load_script("factory_ng_model_call_missing_key_test", "model_call.py")
            with self.assertRaises(SystemExit) as raised:
                model_call.call_openrouter("minimax/minimax-m3:free", "map")
        self.assertEqual(raised.exception.code, model_call.AUTHENTICATION_EXIT)

    def test_remote_runner_loads_only_openrouter_key_from_gitignored_env(self):
        runner = load_script("factory_ng_runner_dotenv_test", "factory-ng-run-engine-ticket.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-runner-env-") as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text("OPENROUTER_API_KEY='test-key'\nUNRELATED_SECRET=do-not-copy\n")
            with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
                environment = runner.model_environment("raw.json", dotenv)
        self.assertEqual(environment["OPENROUTER_API_KEY"], "test-key")
        self.assertNotIn("UNRELATED_SECRET", environment)
        self.assertEqual(environment["PIPE_RAW_ARTIFACT"], "raw.json")

    def test_integration_retries_only_vanished_go_cache_artifacts(self):
        integration = load_script("factory_ng_integration_cache_test", "factory-ng-integrate.py")
        vanished = {"stdout": "", "stderr":
                    "open /home/dev/.cache/go-build/ab/file.a: no such file or directory"}
        compile_error = {"stdout": "", "stderr": "cards/foo.go:12: undefined: missing"}
        self.assertTrue(integration.cache_artifact_failure(vanished))
        self.assertFalse(integration.cache_artifact_failure(compile_error))

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

    def test_codex_factory_capacity_mode_uses_real_headroom(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-codex-capacity-") as directory:
            cache = Path(directory) / "usage.json"
            reset = int(time.time() + 604800)
            env = os.environ.copy()
            env.update({"CODEX_USAGE_CACHE": str(cache), "CODEX_USAGE_GATE_TTL": "86400",
                        "CODEX_PACE_OFF_FILE": str(Path(directory) / "off"),
                        "CODEX_PACE_MODE": "capacity", "CODEX_HARD_PRIMARY": "95"})
            cache.write_text(json.dumps({"used_pct": 25, "resets_at": reset,
                                         "window_mins": 10080}))
            allowed = subprocess.run(
                ["bash", "-c", 'source "$1"; pace_ok_codex', "test",
                 str(OPS / "scripts/lib-pace-gate-codex.sh")], env=env)
            self.assertEqual(allowed.returncode, 0)
            cache.write_text(json.dumps({"used_pct": 95, "resets_at": reset,
                                         "window_mins": 10080}))
            held = subprocess.run(
                ["bash", "-c", 'source "$1"; pace_ok_codex', "test",
                 str(OPS / "scripts/lib-pace-gate-codex.sh")], env=env)
            self.assertEqual(held.returncode, 1)

    def test_claude_weekly_gate_modes(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-claude-weekly-") as directory:
            root = Path(directory)
            cache = root / "usage.json"
            reset = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
            cache.write_text(json.dumps({
                "five_hour": {"utilization": 0, "resets_at": reset.isoformat()},
                "seven_day": {"utilization": 60, "resets_at": reset.isoformat()},
            }))
            base = os.environ.copy()
            base.update({"USAGE_CACHE": str(cache), "USAGE_GATE_TTL": "86400",
                         "PACE_OFF_FILE": str(root / "off"), "PACE_HARD5": "95"})
            script = str(OPS / "scripts/lib-pace-gate.sh")
            for mode, percentage, expected in (("paced", "95", 1), ("fixed", "70", 0),
                                                ("fixed", "50", 1), ("none", "95", 0)):
                env = dict(base, WEEKLY_GATE_MODE=mode, WEEKLY_GATE_PCT=percentage)
                result = subprocess.run(["bash", "-c", 'source "$1"; pace_ok', "test", script], env=env)
                self.assertEqual(result.returncode, expected, (mode, percentage))

    def test_codex_weekly_gate_modes(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-codex-weekly-") as directory:
            root = Path(directory)
            cache = root / "usage.json"
            cache.write_text(json.dumps({"used_pct": 60, "resets_at": int(time.time()) + 604800,
                                         "window_mins": 10080}))
            base = os.environ.copy()
            base.update({"CODEX_USAGE_CACHE": str(cache), "CODEX_USAGE_GATE_TTL": "86400",
                         "CODEX_PACE_OFF_FILE": str(root / "off")})
            script = str(OPS / "scripts/lib-pace-gate-codex.sh")
            for mode, percentage, expected in (("paced", "95", 1), ("fixed", "70", 0),
                                                ("fixed", "50", 1), ("none", "95", 0)):
                env = dict(base, WEEKLY_GATE_MODE=mode, WEEKLY_GATE_PCT=percentage)
                result = subprocess.run(["bash", "-c", 'source "$1"; pace_ok_codex', "test", script], env=env)
                self.assertEqual(result.returncode, expected, (mode, percentage))

    def test_claude_status_reports_five_hour_pause(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-pace-status-") as directory:
            cache = Path(directory) / "usage.json"
            reset = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
            week = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=4)
            cache.write_text(json.dumps({
                "five_hour": {"utilization": 100, "resets_at": reset.isoformat()},
                "seven_day": {"utilization": 10, "resets_at": week.isoformat()},
            }))
            env = os.environ.copy()
            env.update({"USAGE_CACHE": str(cache), "USAGE_GATE_TTL": "86400",
                        "PACE_OFF_FILE": str(Path(directory) / "off"), "PACE_HARD5": "95"})
            result = subprocess.run(["bash", str(OPS / "scripts/lib-pace-gate.sh"), "status"],
                                    env=env, capture_output=True, text=True, check=True)
            self.assertIn("5H-PAUSE", result.stdout)

    def test_runtime_policy_has_safe_push_deploy_split(self):
        policy = json.loads((OPS / "config/factory-ng-policy.json").read_text())
        self.assertTrue(policy["integration"]["automatic"])
        self.assertTrue(policy["integration"]["push_when_full_gate_green"])
        self.assertFalse(policy["integration"]["deploy_after_push"])
        self.assertEqual(policy["retry"]["infrastructure_attempts"], 3)
        self.assertEqual(policy["queue"]["target_ready"], 3)
        self.assertEqual(policy["queue"]["ready_per_worker"], 2)
        self.assertEqual(policy["queue"]["map_reserve"], 2)
        self.assertEqual(policy["queue"]["max_queued"], 12)

    def test_runnable_reserve_is_twice_enabled_worker_count(self):
        controller = load_script("factory_ng_dynamic_reserve_test", "factory-ng-controller.py")
        workers = by_profile_of({"qwen": {}, "claude": {}, "codex": {}})
        self.assertEqual(controller.effective_target_ready(
            {"target_ready": 3, "ready_per_worker": 2}, workers), 6)
        self.assertEqual(controller.effective_target_ready(
            {"target_ready": 8, "ready_per_worker": 2}, workers), 8)

    def test_producer_replaces_leases_before_dispatch(self):
        controller = load_script("factory_ng_fill_target_test", "factory-ng-controller.py")
        workers = by_profile_of({
            "qwen": {"id": "qwen"}, "claude": {"id": "claude"}, "codex": {"id": "codex"},
        })
        availability = availability_of(workers, {profile: {"allowed": True} for profile in workers})
        self.assertEqual(controller.producer_fill_target(
            6, 12, workers, availability), 9)

    def test_active_jobs_reserve_retry_capacity(self):
        controller = load_script("factory_ng_queue_cap_test", "factory-ng-controller.py")
        jobs = {"jobs": {
            "a": {"state": "working"}, "b": {"state": "working"},
            "c": {"state": "working"}, "done": {"state": "completed"},
        }}
        self.assertEqual(controller.producer_queue_cap(12, jobs), 9)

    def test_five_busy_workers_cannot_shrink_the_ten_ticket_reserve(self):
        controller = load_script("factory_ng_reserve_floor_test", "factory-ng-controller.py")
        jobs = {"jobs": {str(i): {"state": "working"} for i in range(5)}}
        self.assertEqual(controller.producer_queue_cap(12, jobs, 10), 10)
        jobs['jobs'].clear()
        self.assertEqual(controller.producer_queue_cap(12, jobs, 10), 12)

    def test_successful_supply_refills_immediately_after_leases(self):
        controller = load_script("factory_ng_refill_due_test", "factory-ng-controller.py")
        runtime = {"queue": {"runnable": 6, "total": 6, "fill_target": 9,
                              "max_queued": 12, "admission_cap": 9},
                   "results": [{"producer": "build-plan", "status": "queued"}]}
        self.assertTrue(controller.reserve_refill_due(runtime))
        runtime["queue"]["total"] = 99
        runtime["queue"]["deferred"] = 93
        self.assertTrue(controller.reserve_refill_due(runtime))
        runtime["queue"]["runnable"] = 9
        self.assertFalse(controller.reserve_refill_due(runtime))
        runtime["queue"]["runnable"] = 6
        runtime["results"][0]["status"] = "exhausted_supported_plan"
        self.assertFalse(controller.reserve_refill_due(runtime))

    def test_pending_scan_refills_but_latest_exhaustion_or_error_stops_it(self):
        controller = load_script("factory_ng_pending_refill_test", "factory-ng-controller.py")
        runtime = {'queue': {'runnable': 0, 'target_ready': 10, 'admission_cap': 10},
                   'results': [{'producer': 'fresh', 'status': 'scan_pending'}]}
        self.assertTrue(controller.reserve_refill_due(runtime))
        runtime['queue']['runnable'] = 10
        self.assertFalse(controller.reserve_refill_due(runtime))
        runtime['queue']['runnable'] = 0
        for status in ('exhausted_supported_plan', 'producer_error', 'active_frontier_limit'):
            runtime['results'] = [{'producer': 'fresh', 'status': 'queued'},
                                  {'producer': 'fresh', 'status': status}]
            self.assertFalse(controller.reserve_refill_due(runtime))

    def test_producer_timeout_is_recorded_without_escaping_sweep(self):
        controller = load_script("factory_ng_producer_timeout_test", "factory-ng-controller.py")
        results = []
        with mock.patch.object(controller, "write_status"), mock.patch.object(controller, "log"), \
             mock.patch.object(controller.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(["slow-producer"], 90)):
            status = controller.run_producer("slow", ["slow-producer"], 90, results, [])
        self.assertEqual(status, "producer_error")
        self.assertEqual(results[0]["producer"], "slow")
        self.assertIn("timed out", results[0]["reason"])

    def test_engine_production_preserves_map_queue_reserve(self):
        controller = load_script("factory_ng_lane_reserve_test", "factory-ng-controller.py")
        engine = {"ticket": {"work_type": "engine"}}
        allowed, reason = controller.producer_lane_admission(
            engine, {"max_runnable": 10, "map_reserve": 2, "runnable_engine": 8})
        self.assertFalse(allowed)
        self.assertIn("Engine queue is at its cap of 8", reason)

        allowed, reason = controller.producer_lane_admission(
            engine, {"max_runnable": 10, "map_reserve": 2, "runnable_engine": 7})
        self.assertTrue(allowed)
        self.assertIsNone(reason)

        allowed, reason = controller.producer_lane_admission(
            {"ticket": {"work_type": "map"}},
            {"max_runnable": 10, "map_reserve": 2, "runnable_engine": 8})
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_deferred_inventory_does_not_consume_runnable_capacity(self):
        controller = load_script("factory_ng_producer_sweep_test", "factory-ng-controller.py")
        inventory = {"runnable": ["a", "b", "c", "d", "e", "f"],
                     "deferred": ["old-%d" % item for item in range(20)], "total": 26}
        self.assertTrue(controller.producer_loop_needed(inventory, 3, 12, first_round=True))
        self.assertFalse(controller.producer_loop_needed(inventory, 3, 12, first_round=False))
        inventory["runnable"] = ["ready-%d" % item for item in range(12)]
        self.assertFalse(controller.producer_loop_needed(inventory, 3, 12, first_round=True))

    def test_every_worker_has_known_usage_policy(self):
        workers = json.loads((OPS / "config/factory-ng-workers.json").read_text())["workers"]
        self.assertEqual({item["usage_policy"] for item in workers},
                         {"unmetered", "openrouter-cooldown", "claude-weekly", "codex-weekly"})

    def test_minimax_worker_is_registered_for_bounded_map_work_only(self):
        workers = json.loads((OPS / "config/factory-ng-workers.json").read_text())["workers"]
        minimax = next(item for item in workers if item["id"] == "minimax-m3-free")
        self.assertIsInstance(minimax["enabled"], bool)
        self.assertEqual(minimax["model"], "minimax/minimax-m3:free")
        self.assertEqual(minimax["profile"], "minimax-prepared-direct@1.0.0")
        self.assertEqual(minimax["usage_policy"], "openrouter-cooldown")
        profile = json.loads((OPS / "docs/factory-ng/model-profiles/v1/minimax-prepared-direct-1.0.0.json").read_text())
        self.assertEqual((profile["id"], profile["version"]),
                         ("minimax-prepared-direct", "1.0.0"))
        self.assertEqual(profile["adapter"]["engine"], "openrouter")
        self.assertEqual(profile["adapter"]["max_completion_tokens"], 16000)
        controller = load_script("factory_ng_minimax_worker_test", "factory-ng-controller.py")
        self.assertTrue(controller.worker_supports(minimax, "map"))
        self.assertFalse(controller.worker_supports(minimax, "engine"))
        legacy_engine = {"work_type": "engine", "execution": {
            "selected_profile": "claude-staged@1.0.0",
            "compatible_profiles": ["claude-staged@1.0.0", "minimax-prepared-direct@1.0.0",
                                    "codex-constrained@1.0.0"],
        }}
        self.assertNotIn("minimax-prepared-direct@1.0.0",
                         controller.compatible_profiles_for(legacy_engine, "claude-staged@1.0.0"))
        runner = load_script("factory_ng_minimax_runner_test", "factory-ng-run-engine-ticket.py")
        self.assertEqual(runner.PROFILE_ENGINES[minimax["profile"]], "openrouter")
        self.assertFalse(runner.supports_profile(legacy_engine, minimax["profile"]))

    def test_qwen_worker_uses_goose_and_drains_legacy_agentic(self):
        workers = json.loads((OPS / "config/factory-ng-workers.json").read_text())["workers"]
        qwen = dict(next(item for item in workers if item["id"] == "qwen-local"), enabled=True)
        self.assertEqual(qwen["profile"], "qwen-goose-staged@1.0.0")
        self.assertEqual(qwen["alternate_profiles"], ["qwen-prepared-local@1.0.1"])
        self.assertEqual(qwen["draining_profiles"], ["qwen-prepared-local@1.0.1"])
        controller = load_script("factory_ng_qwen_engine_worker_test", "factory-ng-controller.py")
        routed = controller.configured_workers_by_profile([qwen])
        staged = routed[controller.QWEN_GOOSE_PROFILE][0]
        agentic = routed[controller.QWEN_AGENTIC_PROFILE][0]
        self.assertEqual(staged["id"], agentic["id"])
        for work_type in ('map', 'engine'):
            self.assertTrue(controller.worker_supports_job(staged, {'work_type': work_type, 'state': 'queued'}))
        self.assertFalse(controller.worker_supports_job(agentic, {'work_type':'engine','state':'queued'}))
        self.assertTrue(controller.worker_supports_job(agentic, {'work_type':'engine','state':'awaiting_verification'}))
        self.assertEqual(controller.effective_target_ready(
            {"target_ready": 3, "ready_per_worker": 2}, routed), 3)
        profile = json.loads((OPS / "docs/factory-ng/model-profiles/v1/qwen-goose-staged.json").read_text())
        self.assertEqual(profile['adapter']['engine'], 'goose-qwen-staged')
        self.assertEqual(profile['adapter']['max_model_calls'], 3)
        self.assertEqual(profile['adapter']['max_completion_tokens'], 32000)
        self.assertEqual(profile['adapter']['allowed_tools'], [])


    def test_auto_routing_keeps_map_priority_when_engine_backlog_is_larger(self):
        controller = load_script("factory_ng_qwen_engine_dispatch_test", "factory-ng-controller.py")
        worker_config = [{
            "id": "qwen-local", "enabled": True,
            "profile": controller.QWEN_DIRECT_PROFILE,
            "alternate_profiles": [controller.QWEN_AGENTIC_PROFILE],
            "routing_mode": "auto",
        }]
        workers = controller.configured_workers_by_profile(worker_config)
        availability = availability_of(workers, {profile: {"allowed": True, "detail": "ready"} for profile in workers})
        jobs = {"jobs": {
            "ticket:map.first/v1": {
                "ticket_id": "ticket:map.first/v1", "ticket_path": "map.json",
                "state": "queued", "work_type": "map", "created_at": "2026-01-01T00:00:00Z",
                "compatible_profiles": [controller.QWEN_DIRECT_PROFILE],
            },
            "ticket:engine.second/v1": {
                "ticket_id": "ticket:engine.second/v1", "ticket_path": "engine.json",
                "state": "queued", "work_type": "engine", "created_at": "2026-01-02T00:00:00Z",
                "compatible_profiles": [controller.QWEN_AGENTIC_PROFILE],
            },
            "ticket:engine.third/v1": {
                "ticket_id": "ticket:engine.third/v1", "ticket_path": "engine-third.json",
                "state": "queued", "work_type": "engine", "created_at": "2026-01-03T00:00:00Z",
                "compatible_profiles": [controller.QWEN_AGENTIC_PROFILE],
            },
        }}
        selected = controller.next_dispatch(jobs, workers, availability)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][1]["ticket_id"], "ticket:map.first/v1")
        self.assertEqual(selected[0][1]["dispatch_profile"], controller.QWEN_DIRECT_PROFILE)

        jobs["jobs"]["ticket:map.first/v1"]["state"] = "working"
        jobs["jobs"]["ticket:map.first/v1"]["worker"] = "qwen-local"
        self.assertEqual(controller.next_dispatch(jobs, workers, availability), [])

        jobs["jobs"]["ticket:map.first/v1"]["state"] = "completed"
        jobs["jobs"]["ticket:map.first/v1"].pop("worker")
        selected = controller.next_dispatch(jobs, workers, availability)
        self.assertEqual(selected[0][1]["ticket_id"], "ticket:engine.second/v1")
        self.assertEqual(selected[0][1]["dispatch_profile"], controller.QWEN_AGENTIC_PROFILE)

    def test_worker_routing_mode_limits_dual_profile_worker(self):
        controller = load_script("factory_ng_worker_routing_mode_test", "factory-ng-controller.py")
        claude = {"id": "claude", "profile": "claude-staged@1.0.0"}
        for mode, supports_map, supports_engine in (
                ("auto", True, True), ("map", True, False), ("engine", False, True)):
            worker = dict(claude, routing_mode=mode)
            self.assertEqual(controller.worker_supports(worker, "map"), supports_map)
            self.assertEqual(controller.worker_supports(worker, "engine"), supports_engine)
        self.assertFalse(controller.worker_supports(
            dict(claude, routing_mode="invalid"), "engine"))

    def test_auto_routing_keeps_map_priority_when_engine_is_not_dominant(self):
        controller = load_script("factory_ng_balanced_auto_routing_test", "factory-ng-controller.py")
        workers = controller.configured_workers_by_profile([{
            "id": "qwen-local", "enabled": True, "routing_mode": "auto",
            "profile": controller.QWEN_DIRECT_PROFILE,
            "alternate_profiles": [controller.QWEN_AGENTIC_PROFILE],
        }])
        availability = availability_of(workers, {profile: {"allowed": True, "detail": "ready"} for profile in workers})
        jobs = {"jobs": {
            "ticket:map/v1": {
                "ticket_id": "ticket:map/v1", "ticket_path": "map.json",
                "state": "queued", "work_type": "map",
                "compatible_profiles": [controller.QWEN_DIRECT_PROFILE],
            },
            "ticket:engine/v1": {
                "ticket_id": "ticket:engine/v1", "ticket_path": "engine.json",
                "state": "queued", "work_type": "engine",
                "compatible_profiles": [controller.QWEN_AGENTIC_PROFILE],
            },
        }}
        selected = controller.next_dispatch(jobs, workers, availability)
        self.assertEqual([item[1]["ticket_id"] for item in selected], ["ticket:map/v1"])

    def test_minimax_engine_need_dash_form_resolves_only_allowed_context(self):
        runner = load_script("factory_ng_minimax_need_test", "factory-ng-run-engine-ticket.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-minimax-need-") as directory:
            clone = Path(directory)
            targeting = clone / "backend/game/targeting.go"
            effects = clone / "backend/game/ability_effects.go"
            targeting.parent.mkdir(parents=True)
            targeting.write_text("package game\n\ntype TargetFilter struct {\n\tFilter string\n}\n")
            effects.write_text("package game\n\nfunc executeTap() {}\n")
            ticket = {"scope": {"allowed_paths": [
                "backend/game/targeting.go", "backend/game/ability_effects.go"]}}
            reply = ("NEED: backend/game/targeting.go — TargetFilter struct definition\n"
                     "NEED: backend/game/ability_effects.go executeTap function body\n"
                     "NEED: /etc/passwd - unrelated path\n")
            context = runner.requested_context(reply, clone, ticket)
        self.assertIn("backend/game/targeting.go", context)
        self.assertIn("TargetFilter", context)
        self.assertIn("backend/game/ability_effects.go", context)
        self.assertIn("executeTap", context)
        self.assertNotIn("/etc/passwd", context)

    def test_second_worker_on_same_profile_dispatches_concurrently(self):
        """Two enabled worker entries sharing one profile (e.g. a secondary
        claude-staged lease) must both be usable in the same dispatch round —
        the second lease must not be shadowed by the first under one profile key."""
        controller = load_script("factory_ng_dual_lease_test", "factory-ng-controller.py")
        workers = controller.configured_workers_by_profile([
            {"id": "claude", "enabled": True, "routing_mode": "auto",
             "profile": "claude-staged@1.0.0"},
            {"id": "claude-2", "enabled": True, "routing_mode": "engine",
             "profile": "claude-staged@1.0.0"},
        ])
        self.assertEqual(len(workers["claude-staged@1.0.0"]), 2)
        availability = availability_of(workers, {
            "claude-staged@1.0.0": {"allowed": True, "detail": "ready"}})
        jobs = {"jobs": {
            "ticket:engine.first/v1": {
                "ticket_id": "ticket:engine.first/v1", "ticket_path": "e1.json",
                "state": "queued", "work_type": "engine", "created_at": "2026-01-01T00:00:00Z",
                "compatible_profiles": ["claude-staged@1.0.0"],
            },
            "ticket:engine.second/v1": {
                "ticket_id": "ticket:engine.second/v1", "ticket_path": "e2.json",
                "state": "queued", "work_type": "engine", "created_at": "2026-01-02T00:00:00Z",
                "compatible_profiles": ["claude-staged@1.0.0"],
            },
        }}
        selected = controller.next_dispatch(jobs, workers, availability)
        self.assertEqual(len(selected), 2)
        self.assertEqual({item[2]["id"] for item in selected}, {"claude", "claude-2"})
        self.assertEqual({item[1]["ticket_id"] for item in selected},
                         {"ticket:engine.first/v1", "ticket:engine.second/v1"})

    def test_model_protocol_retry_fails_over_to_another_profile(self):
        controller = load_script("factory_ng_profile_failover_test", "factory-ng-controller.py")
        job = {"ticket_id": "ticket:engine.example/v1", "ticket_path": "example.json",
               "work_type": "engine",
               "state": "queued", "dispatch_profile": "codex-constrained@1.0.0",
               "compatible_profiles": ["claude-staged@1.0.0", "codex-constrained@1.0.0"]}
        controller.record_profile_failure(job, "infrastructure_failed_model_protocol")
        workers = by_profile_of({
            "claude-staged@1.0.0": {"id": "claude", "profile": "claude-staged@1.0.0"},
            "codex-constrained@1.0.0": {"id": "codex", "profile": "codex-constrained@1.0.0"},
        })
        selected = controller.next_dispatch(
            {"jobs": {job["ticket_id"]: job}}, workers,
            availability_of(workers, {profile: {"allowed": True, "detail": "ready"} for profile in workers}))
        self.assertEqual(selected[0][2]["id"], "claude")

    def test_minimax_engine_protocol_migration_refunds_duplicate_attempts(self):
        controller = load_script("factory_ng_minimax_migration_test", "factory-ng-controller.py")
        job = {"ticket_id": "ticket:engine.example/v1", "work_type": "engine",
               "state": "failed", "outcome": "infrastructure_failed_model_protocol",
               "dispatch_profile": controller.MINIMAX_PROFILE, "attempts": 3}
        jobs = {"jobs": {job["ticket_id"]: job}}
        self.assertEqual(controller.migrate_minimax_engine_protocol_retries(jobs), 1)
        self.assertEqual(job["attempts"], 1)
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["failed_profiles"], [controller.MINIMAX_PROFILE])
        self.assertEqual(jobs["minimax_engine_protocol_migration_v1"]["refunded_attempts"], 2)
        self.assertEqual(controller.migrate_minimax_engine_protocol_retries(jobs), 0)

    def test_unstarted_minimax_engine_lease_is_refunded(self):
        controller = load_script("factory_ng_minimax_dispatch_migration_test", "factory-ng-controller.py")
        job = {"ticket_id": "ticket:engine.example/v1", "work_type": "engine",
               "state": "queued", "outcome": "infrastructure_failed",
               "worker": "minimax-m3-free", "attempts": 1}
        jobs = {"jobs": {job["ticket_id"]: job}}
        self.assertEqual(controller.migrate_unstarted_minimax_engine_dispatches(jobs), 1)
        self.assertEqual(job["attempts"], 0)
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["failed_profiles"], [controller.MINIMAX_PROFILE])

    def test_remote_runner_never_repairs_after_need_continuation(self):
        runner = load_script("factory_ng_remote_call_bound_test", "factory-ng-run-engine-ticket.py")
        model = {"exit_code": 0}
        rejected = {"exit_code": 5}
        self.assertTrue(runner.should_attempt_repair(model, rejected, {}))
        self.assertFalse(runner.should_attempt_repair(
            model, rejected, {"need_continuation_attempted": True}))
        self.assertFalse(runner.should_attempt_repair(
            {"exit_code": runner.OPENROUTER_RATE_LIMIT_EXIT}, rejected, {}))

    def test_enqueue_rejects_incomplete_ticket(self):
        result = subprocess.run(["python3", str(OPS / "scripts/factory-ng-enqueue.py")],
                                input='{"schema":"factory.ticket-spec/v1"}', text=True,
                                capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "rejected")

    def test_continuous_producer_advances_past_accounted_key(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-producer-test-") as directory:
            root = Path(directory)
            tickets = root / "tickets"
            tickets.mkdir()
            jobs = root / "jobs.json"
            jobs.write_text('{"schema":"factory.ng-jobs/v1","jobs":{}}\n')
            command = ["python3", str(OPS / "scripts/factory-ng-produce-build-plan.py"),
                       "--ticket-dir", str(tickets), "--jobs", str(jobs)]
            first = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            self.assertEqual(first["ticket"]["execution"]["selected_profile"],
                             "claude-staged@1.0.0")
            self.assertEqual(first["status"], "ready")
            first_path = tickets / "first.json"
            first_path.write_text(json.dumps(first["ticket"]))
            second = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            self.assertEqual(second["status"], "ready")
            self.assertNotEqual(first["ticket"]["production"]["key"],
                                second["ticket"]["production"]["key"])

    def test_continuous_producer_versions_one_exhausted_infrastructure_failure(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-producer-retry-test-") as directory:
            root = Path(directory)
            # This test runs across two scans. Pin a checkout and a private
            # cache so live integration/producer activity cannot alter either.
            source = root / 'source'
            canonical = SOURCE
            subprocess.run(['git', 'clone', '--quiet', '--shared', str(canonical), str(source)],
                           check=True, capture_output=True, timeout=180)
            shutil.copyfile(canonical/'corpus/AtomicCards.json.gz', source/'corpus/AtomicCards.json.gz')
            skill = root/'docs/factory-ng/skills/v1/implement-map-class/SKILL.md'
            skill.parent.mkdir(parents=True)
            shutil.copyfile(OPS/'docs/factory-ng/skills/v1/implement-map-class/SKILL.md', skill)
            wrapper = root/'producer.py'
            wrapper.write_text('import importlib.util,sys\nfrom pathlib import Path\n' +
                'sys.path.insert(0, ' + repr(str(OPS/'scripts')) + ')\n' +
                'spec=importlib.util.spec_from_file_location("producer", ' +
                repr(str(OPS/'scripts/factory-ng-produce-build-plan.py')) + ')\n' +
                'm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n' +
                'm.OPS=Path(' + repr(str(root)) + ');m.SKILL=Path(' + repr(str(skill)) + ')\nm.main()\n')
            tickets = root / "tickets"
            tickets.mkdir()
            jobs = root / "jobs.json"
            command = ["python3", str(wrapper), '--repo', str(source),
                       "--ticket-dir", str(tickets), "--jobs", str(jobs)]
            jobs.write_text('{"schema":"factory.ng-jobs/v1","jobs":{}}\n')
            first = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            (tickets / "first.json").write_text(json.dumps(first["ticket"]))
            jobs.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                first["ticket"]["id"]: {"state": "failed", "outcome": "infrastructure_failed_model_protocol"}
            }}))
            retried = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            self.assertEqual(retried["ticket"]["production"]["key"],
                             first["ticket"]["production"]["key"])
            self.assertEqual(retried["ticket"]["supersedes"], first["ticket"]["id"])
            self.assertEqual(retried["ticket"]["production"]["retry_generation"], 1)
            self.assertEqual(retried["ticket"]["execution"]["selected_profile"],
                             "claude-staged@1.0.0")
            self.assertNotEqual(retried["ticket"]["evidence"][0]["path"],
                                first["ticket"]["evidence"][0]["path"])

    def test_continuous_producer_routes_failed_qwen_candidate_to_paid_repair(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-producer-semantic-retry-") as directory:
            root = Path(directory)
            tickets = root / "tickets"; tickets.mkdir()
            jobs = root / "jobs.json"
            command = ["python3", str(OPS / "scripts/factory-ng-produce-build-plan.py"),
                       "--ticket-dir", str(tickets), "--jobs", str(jobs)]
            jobs.write_text('{"schema":"factory.ng-jobs/v1","jobs":{}}\n')
            first = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            (tickets / "first.json").write_text(json.dumps(first["ticket"]))
            jobs.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                first["ticket"]["id"]: {"state": "failed", "outcome": "gate_failed",
                                                "dispatch_profile": "qwen-prepared-direct@1.0.2",
                                                "receipt": "docs/factory-ng/runs/failed-qwen.json"}
            }}))
            retried = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            self.assertEqual(retried["status"], "ready")
            self.assertEqual(retried["ticket"]["supersedes"], first["ticket"]["id"])
            self.assertEqual(retried["ticket"]["production"]["retry_reason"], "semantic_gate_repair")
            self.assertNotIn("qwen-prepared-direct@1.0.2",
                             retried["ticket"]["execution"]["compatible_profiles"])
            self.assertTrue(any(item.get("path") == "docs/factory-ng/runs/failed-qwen.json"
                                for item in retried["ticket"]["evidence"]))

    def test_fresh_build_plan_lane_skips_paid_repair_frontier(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-producer-fresh-lane-") as directory:
            root = Path(directory)
            tickets = root / "tickets"; tickets.mkdir()
            jobs = root / "jobs.json"
            base = ["python3", str(OPS / "scripts/factory-ng-produce-build-plan.py"),
                    "--ticket-dir", str(tickets), "--jobs", str(jobs)]
            jobs.write_text('{"schema":"factory.ng-jobs/v1","jobs":{}}\n')
            first = json.loads(subprocess.run(base, check=True, capture_output=True, text=True).stdout)
            (tickets / "first.json").write_text(json.dumps(first["ticket"]))
            jobs.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                first["ticket"]["id"]: {"state": "failed", "outcome": "gate_failed",
                                                "dispatch_profile": "qwen-prepared-direct@1.0.2"}
            }}))
            fresh = json.loads(subprocess.run(base + ["--lane", "fresh"], check=True,
                                              capture_output=True, text=True).stdout)
            repair = json.loads(subprocess.run(base + ["--lane", "repair"], check=True,
                                               capture_output=True, text=True).stdout)
            self.assertEqual(fresh["status"], "ready")
            self.assertNotEqual(fresh["ticket"]["production"]["key"],
                                first["ticket"]["production"]["key"])
            self.assertIn("qwen-prepared-direct@1.0.2",
                          fresh["ticket"]["execution"]["compatible_profiles"])
            self.assertEqual(repair["ticket"]["production"]["key"],
                             first["ticket"]["production"]["key"])
            self.assertNotIn("qwen-prepared-direct@1.0.2",
                             repair["ticket"]["execution"]["compatible_profiles"])

    def test_fresh_discovery_extends_beyond_plan_sample_names(self):
        producer = load_script("factory_ng_fresh_discovery_test",
                               "factory-ng-produce-build-plan.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-fresh-discovery-") as directory:
            source = Path(directory)
            carddb = source / "backend/data/carddb"; carddb.mkdir(parents=True)
            carddb.joinpath("a.json").write_text(json.dumps({
                "A Fresh Card": {"name": "A Fresh Card", "status": "review", "text": "Untap it."}
            }))
            class FakeReparse:
                @staticmethod
                def reparse_card(card):
                    return {"misses": [("verb_unmapped:untap", "untap it")]}
            rows = [{"rank": 1, "item": "verb_unmapped:untap", "examples": ["Old Sample"]}]
            found = producer.discover_fresh_example(
                source, FakeReparse, rows, {"untap": {}}, history={})
            self.assertEqual(found[1], "A Fresh Card")

    def test_integration_conflict_gets_one_latest_source_successor(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-conflict-retry-") as directory:
            root = Path(directory)
            tickets = root / "tickets"; tickets.mkdir()
            jobs = root / "jobs.json"
            command = ["python3", str(OPS / "scripts/factory-ng-produce-build-plan.py"),
                       "--ticket-dir", str(tickets), "--jobs", str(jobs)]
            jobs.write_text('{"schema":"factory.ng-jobs/v1","jobs":{}}\n')
            first = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
            prior = first["ticket"]
            prior["id"] = prior["id"].replace("/v1", "/v2")
            prior["production"]["retry_generation"] = 1
            (tickets / "prior.json").write_text(json.dumps(prior))
            jobs.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                prior["id"]: {"state": "integration_failed", "outcome": "candidate_conflict",
                              "integration_receipt": "docs/factory-ng/runs/conflict.json"}
            }}))
            retry = json.loads(subprocess.run(command + ["--lane", "conflict"], check=True,
                                              capture_output=True, text=True).stdout)
            self.assertEqual(retry["ticket"]["production"]["retry_generation"], 2)
            self.assertEqual(retry["ticket"]["production"]["retry_reason"],
                             "integration_conflict_repair")
            self.assertEqual(retry["ticket"]["supersedes"], prior["id"])

    def test_registry_parser_preserves_go_escaped_quotes(self):
        producer = load_script("factory_ng_build_plan_test", "factory-ng-produce-build-plan.py")
        damage = producer.registry_effects(SOURCE)["damage"]
        self.assertIn('case "damage" -> SpellEffect', damage["executor"])

    def test_capability_oracle_lookup_ignores_handler_metadata_collision(self):
        contract = load_script("factory_ng_capability_oracle_test", "capability-contract.py")
        capability = {"specification": {"source_misses": [{
            "card": "Foray of Orcs",
            "paragraph": "Amass Orcs 2. When you do, Foray of Orcs deals X damage to target creature an opponent controls, where X is the amassed Army's power. (To amass Orcs 2, put two +1/+1 counters on an Army you control. It's also an Orc. If you don't control an Army, create a 0/0 black Orc Army creature token first.)",
        }]}}
        contract.validate_oracle(capability, str(SOURCE))
        self.assertIn("oracle_text_sha256", capability["specification"]["source_misses"][0])

    def test_capability_producer_recovers_now_valid_raw_verdict(self):
        producer = load_script("factory_ng_capability_recovery_test",
                               "factory-ng-produce-capability-dependency.py")
        value = {"key": "damage_by_amassed_army_power", "summary": "resolve amassed Army power",
                 "specification": {"required_behavior": "Resolve the amassed Army power.",
                                   "source_misses": [{
                                       "card": "Foray of Orcs",
                                       "paragraph": "Amass Orcs 2. When you do, Foray of Orcs deals X damage to target creature an opponent controls, where X is the amassed Army's power. (To amass Orcs 2, put two +1/+1 counters on an Army you control. It's also an Orc. If you don't control an Army, create a 0/0 black Orc Army creature token first.)",
                                   }]}}
        reply = "VERDICT: NEEDS_PRIMITIVE\nCAPABILITY_JSON: " + json.dumps(value, separators=(",", ":"))
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl") as raw:
            raw.write(json.dumps({"item": {"type": "agent_message", "text": reply}}) + "\n")
            raw.flush()
            receipt = {"outcome": "invalid_capability_demand",
                       "raw_artifacts": [{"path": raw.name}]}
            capability = producer.recover_valid_capability(receipt)
        self.assertEqual(capability["key"], "damage_by_amassed_army_power")

    def test_patch_applicator_rejects_trailing_duplicate_replace_marker(self):
        with tempfile.TemporaryDirectory(prefix="factory-ng-apply-marker-") as directory:
            root = Path(directory)
            target = root / "sample.py"
            target.write_text("before\n")
            reply = ("<<<FILE sample.py\n<<<SEARCH\nbefore\n===REPLACE\nafter\n"
                     "===REPLACE\n>>>END\n")
            result = subprocess.run(
                ["python3", str(OPS / "scripts/map-pipeline-apply.py")], cwd=root,
                input=reply, text=True, capture_output=True)
            self.assertEqual(result.returncode, 6)
            self.assertIn("second REPLACE marker", result.stdout)
            self.assertEqual(target.read_text(), "before\n")

    def test_duplicate_classification_is_lifecycle_aware(self):
        controller = load_script("factory_ng_controller_test", "factory-ng-controller.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-dedupe-test-") as directory:
            root = Path(directory)
            controller.OPS = root
            controller.TICKETS = root / "tickets"
            controller.JOBS = root / "jobs.json"
            ticket = {"id": "ticket:map.test/v1", "production": {"key": "ground-truth:test"}}
            status, _ = controller.persist_ready({"ticket": ticket})
            self.assertEqual(status, "queued")
            status, _ = controller.persist_ready({"ticket": ticket})
            self.assertEqual(status, "duplicate_terminal")
            controller.JOBS.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                ticket["id"]: {"state": "queued"}
            }}))
            status, _ = controller.persist_ready({"ticket": ticket})
            self.assertEqual(status, "duplicate_active")
            controller.JOBS.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                ticket["id"]: {"state": "failed", "outcome": "infrastructure_failed"}
            }}))
            successor = {"id": "ticket:map.test/v2", "supersedes": ticket["id"],
                         "production": {"key": "ground-truth:test"}}
            status, _ = controller.persist_ready({"ticket": successor})
            self.assertEqual(status, "queued")

    def test_paused_tickets_do_not_fill_runnable_reserve(self):
        controller = load_script("factory_ng_queue_test", "factory-ng-controller.py")
        jobs = {"jobs": {
            "ticket:map.paused/v1": {
                "ticket_id": "ticket:map.paused/v1", "state": "queued", "work_type": "map",
                "profile": "claude-staged@1.0.0",
                "compatible_profiles": ["claude-staged@1.0.0", "codex-constrained@1.0.0"],
            },
            "ticket:map.local/v1": {
                "ticket_id": "ticket:map.local/v1", "state": "queued", "work_type": "map",
                "profile": "claude-staged@1.0.0",
                "compatible_profiles": ["claude-staged@1.0.0", "qwen-prepared-direct@1.0.2"],
            },
        }}
        workers = by_profile_of({
            "claude-staged@1.0.0": {"id": "claude", "profile": "claude-staged@1.0.0"},
            "codex-constrained@1.0.0": {"id": "codex", "profile": "codex-constrained@1.0.0"},
            "qwen-prepared-direct@1.0.2": {"id": "qwen-local", "profile": "qwen-prepared-direct@1.0.2"},
        })
        availability = availability_of(workers, {
            "claude-staged@1.0.0": {"allowed": False},
            "codex-constrained@1.0.0": {"allowed": False},
            "qwen-prepared-direct@1.0.2": {"allowed": True},
        })
        inventory = controller.queue_inventory(jobs, workers, availability)
        self.assertEqual(inventory["runnable"], ["ticket:map.local/v1"])
        self.assertEqual(inventory["deferred"], ["ticket:map.paused/v1"])

    def test_dispatch_falls_back_to_available_compatible_profile(self):
        controller = load_script("factory_ng_fallback_test", "factory-ng-controller.py")
        jobs = {"jobs": {"ticket:map.test/v1": {
            "ticket_id": "ticket:map.test/v1", "ticket_path": "ticket.json",
            "state": "queued", "work_type": "map", "created_at": "2026-01-01T00:00:00Z",
            "profile": "claude-staged@1.0.0",
            "compatible_profiles": ["claude-staged@1.0.0", "qwen-prepared-direct@1.0.2"],
        }}}
        workers = by_profile_of({
            "claude-staged@1.0.0": {"id": "claude", "profile": "claude-staged@1.0.0"},
            "qwen-prepared-direct@1.0.2": {"id": "qwen-local", "profile": "qwen-prepared-direct@1.0.2"},
        })
        availability = availability_of(workers, {
            "claude-staged@1.0.0": {"allowed": False, "detail": "paused"},
            "qwen-prepared-direct@1.0.2": {"allowed": True, "detail": "unmetered"},
        })
        selected = controller.next_dispatch(jobs, workers, availability)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][2]["id"], "qwen-local")
        self.assertEqual(jobs["jobs"]["ticket:map.test/v1"]["dispatch_profile"],
                         "qwen-prepared-direct@1.0.2")

    def test_dispatch_prioritizes_gate_informed_semantic_repair(self):
        controller = load_script("factory_ng_repair_priority_test", "factory-ng-controller.py")
        jobs = {"jobs": {
            "ticket:engine.old/v1": {
                "ticket_id": "ticket:engine.old/v1", "ticket_path": "old.json",
                "state": "queued", "work_type": "engine", "created_at": "2026-01-01T00:00:00Z",
                "profile": "codex-constrained@1.0.0",
                "compatible_profiles": ["codex-constrained@1.0.0"],
            },
            "ticket:map.repair/v2": {
                "ticket_id": "ticket:map.repair/v2", "ticket_path": "repair.json",
                "state": "queued", "work_type": "map", "created_at": "2026-01-02T00:00:00Z",
                "profile": "codex-constrained@1.0.0",
                "compatible_profiles": ["codex-constrained@1.0.0"],
                "production": {"retry_reason": "semantic_gate_repair"},
            },
        }}
        workers = by_profile_of({"codex-constrained@1.0.0": {
            "id": "codex", "profile": "codex-constrained@1.0.0", "work_types": ["map", "engine"]}})
        availability = availability_of(workers, {"codex-constrained@1.0.0": {"allowed": True, "detail": "capacity"}})
        selected = controller.next_dispatch(jobs, workers, availability)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][1]["ticket_id"], "ticket:map.repair/v2")

    def test_new_dispatch_does_not_present_stale_terminal_metadata(self):
        controller = load_script("factory_ng_dispatch_metadata_test", "factory-ng-controller.py")
        job = {"outcome": "infrastructure_failed", "reason": "old attempt",
               "finished_at": "2026-01-01T00:00:00Z"}
        controller.clear_terminal_metadata(job)
        self.assertNotIn("outcome", job)
        self.assertNotIn("reason", job)
        self.assertNotIn("finished_at", job)

    def test_runners_accept_declared_fallback_profiles(self):
        map_runner = load_script("factory_ng_map_runner_profiles", "factory-ng-run-map-ticket.py")
        engine_runner = load_script("factory_ng_engine_runner_profiles", "factory-ng-run-engine-ticket.py")
        ticket = {"execution": {"selected_profile": "claude-staged@1.0.0",
                                "compatible_profiles": ["claude-staged@1.0.0",
                                                        "qwen-prepared-direct@1.0.2"]}}
        self.assertTrue(map_runner.supports_profile(ticket, "qwen-prepared-direct@1.0.2"))
        self.assertTrue(engine_runner.supports_profile(ticket, "claude-staged@1.0.0"))
        self.assertFalse(engine_runner.supports_profile(ticket, "codex-constrained@1.0.0"))
        legacy_retry = {"work_type": "map", "production": {"retry_generation": 1},
                        "execution": {"selected_profile": "codex-constrained@1.0.0"}}
        self.assertTrue(engine_runner.supports_profile(legacy_retry, "claude-staged@1.0.0"))
        legacy_engine = {"work_type": "engine", "execution": {
            "selected_profile": "claude-staged@1.0.0",
            "compatible_profiles": ["claude-staged@1.0.0", "codex-constrained@1.0.0"],
        }}
        self.assertTrue(engine_runner.supports_profile(
            legacy_engine, "qwen-prepared-local@1.0.1"))
        self.assertFalse(engine_runner.supports_profile(
            {**legacy_engine, "work_type": "map"}, "qwen-prepared-local@1.0.1"))

    def test_harness_failure_keeps_infrastructure_retry_budget(self):
        controller = load_script("factory_ng_harness_retry_test", "factory-ng-controller.py")
        job = {"profile": "claude-staged@1.0.0",
               "dispatch_profile": "qwen-prepared-direct@1.0.2"}
        settings = {"infrastructure_attempts": 3}
        self.assertEqual(controller.max_attempts_for(job, settings), 1)
        self.assertEqual(controller.max_attempts_for_outcome(
            job, settings, "infrastructure_failed"), 3)
        self.assertEqual(controller.max_attempts_for_outcome(
            job, settings, "infrastructure_failed_model_protocol"), 1)
        job["dispatch_profile"] = controller.QWEN_AGENTIC_PROFILE
        self.assertEqual(controller.max_attempts_for(job, settings), 1)

    def test_retry_map_does_not_fall_back_to_exhausted_local_profile(self):
        controller = load_script("factory_ng_retry_profiles_test", "factory-ng-controller.py")
        ticket = {"work_type": "map", "production": {"retry_generation": 1}}
        profiles = controller.default_compatible_profiles(ticket, "codex-constrained@1.0.0")
        self.assertNotIn("qwen-prepared-direct@1.0.2", profiles)
        self.assertIn("minimax-prepared-direct@1.0.0", profiles)

    def test_watchdog_productive_movement_ignores_failure_receipts(self):
        watchdog = load_script("factory_ng_watchdog_test", "factory-ng-watchdog.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-watchdog-test-") as directory:
            watchdog.OPS = Path(directory)
            runs = watchdog.OPS / "docs/factory-ng/runs"
            runs.mkdir(parents=True)
            (runs / "failed.json").write_text(json.dumps({
                "schema": "factory.observation-receipt/v1", "outcome": "gate_failed"}))
            empty = watchdog.productive_signature({})
            self.assertEqual(empty["accepted_receipts"], 0)
            self.assertEqual(empty["latest_productive_epoch"], 0)
            (runs / "accepted.json").write_text(json.dumps({
                "schema": "factory.observation-receipt/v1", "outcome": "accepted_candidate"}))
            productive = watchdog.productive_signature({"ticket": {"state": "completed"}})
            self.assertEqual(productive["accepted_receipts"], 1)
            self.assertEqual(productive["completed_jobs"], 1)
            self.assertGreater(productive["latest_productive_epoch"], 0)

    def test_watchdog_exposes_controller_sweep_exception(self):
        watchdog = load_script("factory_ng_watchdog_producer_error_test", "factory-ng-watchdog.py")
        errors = watchdog.runtime_producer_errors({"phase": "producer_error", "results": []})
        self.assertEqual(errors, [{"producer": "controller-sweep"}])

    def test_completed_dependency_reserve_is_bounded_and_prioritized(self):
        controller = load_script("factory_ng_completed_dependency_reserve", "factory-ng-controller.py")
        job = {"work_type":"map", "state":"queued", "production":{"producer":"capability-dependencies"}}
        self.assertTrue(controller.dependency_resume_slot_available({"jobs":{"a":job}}, 2))
        self.assertFalse(controller.dependency_resume_slot_available({"jobs":{"a":job,"b":job}}, 2))
        self.assertFalse(controller.dependency_resume_slot_available({"jobs":{}}, 0))
        self.assertLess(controller.dispatch_priority(("a",job)), controller.dispatch_priority(("b",{"work_type":"engine"})))

    def test_capability_compiler_emits_bounded_engine_ticket(self):
        producer = load_script("factory_ng_dependency_test", "factory-ng-produce-capability-dependency.py")
        # HTTP retrieval is covered with a real fixture service in test_factory_ng_knowledge.
        producer.discover_capability = mock.Mock(return_value={"status":"not_found","candidates":[],"lookups":[]})
        capability = {
            "key": "damage_amount_from_devotion",
            "summary": "resolve devotion as a damage amount",
            "specification": {
                "required_behavior": "Resolve a damage amount from the source controller's devotion.",
                "source_misses": [{"card": "Fanatic of Mogis",
                                   "paragraph": "When Fanatic of Mogis enters, it deals damage to each opponent equal to your devotion to red.",
                                   "required_behavior": "Resolve devotion as damage."}],
                "negative_examples": ["fixed damage remains fixed"],
                "expected_unlock": 1,
            },
        }
        receipt = OPS / "docs/factory-ng/runs/test-placeholder.json"
        ticket = producer.engine_ticket("ticket:map.test/v1", receipt, capability)
        self.assertEqual(ticket["work_type"], "engine")
        self.assertEqual(ticket["parents"], ["ticket:map.test/v1"])
        self.assertIn("backend/game/ability_effects.go", ticket["scope"]["allowed_paths"])
        self.assertTrue(any("TestFactoryNGDamageAmountFromDevotion" in item
                            for item in ticket["required_behavior"]))

    def test_capability_producer_discovers_validated_receipt_without_live_mutation(self):
        producer = load_script("factory_ng_dependency_main_test", "factory-ng-produce-capability-dependency.py")
        # HTTP retrieval is covered with a real fixture service in test_factory_ng_knowledge.
        producer.discover_capability = mock.Mock(return_value={"status":"not_found","candidates":[],"lookups":[]})
        capability = {
            "key": "damage_amount_from_devotion",
            "summary": "resolve devotion as a damage amount",
            "specification": {
                "required_behavior": "Resolve devotion as damage.",
                "source_misses": [{"card": "Fanatic of Mogis", "paragraph": "exact", "required_behavior": "same"}],
                "negative_examples": [], "expected_unlock": 1,
            },
        }
        with tempfile.TemporaryDirectory(prefix="factory-ng-dependency-main-", dir=OPS) as directory:
            root = Path(directory)
            cache_class = producer.ProducerCache
            producer.ProducerCache = lambda _path: cache_class(root / 'scan-cache.sqlite3')
            producer.RUNS = root / "runs"; producer.RUNS.mkdir()
            producer.TICKETS = root / "tickets"; producer.TICKETS.mkdir()
            producer.JOBS = root / "jobs.json"
            producer.JOBS.write_text('{"schema":"factory.ng-jobs/v1","jobs":{}}\n')
            parent_id = "ticket:map.fixture/v1"
            parent_path = producer.ticket_path_for_id(parent_id)
            parent_path.write_text(json.dumps({"schema": "factory.ticket-spec/v1", "id": parent_id}))
            (producer.RUNS / "receipt.json").write_text(json.dumps({
                "schema": "factory.observation-receipt/v1", "outcome": "blocked_by_capability",
                "ticket": {"id": parent_id}, "capability_demand": capability,
            }))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                producer.main()
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["ticket"]["work_type"], "engine")
            self.assertEqual(result["ticket"]["parents"], [parent_id])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                producer.main(completed_dependencies_only=True)
            self.assertNotEqual(json.loads(output.getvalue())["status"], "ready")

    def test_engine_lane_likely_full_counts_only_active_engine_jobs(self):
        producer = load_script("factory_ng_lane_full_unit_test", "factory-ng-produce-capability-dependency.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-lane-full-", dir=OPS) as directory:
            root = Path(directory)
            producer.POLICY = root / "policy.json"
            producer.POLICY.write_text(json.dumps({"queue": {"max_queued": 2, "map_reserve": 0}}))
            producer.JOBS = root / "jobs.json"
            producer.JOBS.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                "ticket:engine.one/v1": {"work_type": "engine", "state": "queued"},
                "ticket:map.one/v1": {"work_type": "map", "state": "queued"},
            }}))
            self.assertFalse(producer.engine_lane_likely_full())
            producer.JOBS.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                "ticket:engine.one/v1": {"work_type": "engine", "state": "queued"},
                "ticket:engine.two/v1": {"work_type": "engine", "state": "working"},
                "ticket:map.one/v1": {"work_type": "map", "state": "queued"},
            }}))
            self.assertTrue(producer.engine_lane_likely_full())

    def test_capability_producer_defers_new_engine_ticket_when_lane_is_full(self):
        producer = load_script("factory_ng_dependency_lane_full_test", "factory-ng-produce-capability-dependency.py")
        # HTTP retrieval is covered with a real fixture service in test_factory_ng_knowledge.
        producer.discover_capability = mock.Mock(return_value={"status":"not_found","candidates":[],"lookups":[]})
        capability = {
            "key": "damage_amount_from_devotion",
            "summary": "resolve devotion as a damage amount",
            "specification": {
                "required_behavior": "Resolve devotion as damage.",
                "source_misses": [{"card": "Fanatic of Mogis", "paragraph": "exact", "required_behavior": "same"}],
                "negative_examples": [], "expected_unlock": 1,
            },
        }
        with tempfile.TemporaryDirectory(prefix="factory-ng-dependency-lane-full-", dir=OPS) as directory:
            root = Path(directory)
            cache_class = producer.ProducerCache
            producer.ProducerCache = lambda _path: cache_class(root / 'scan-cache.sqlite3')
            producer.RUNS = root / "runs"; producer.RUNS.mkdir()
            producer.TICKETS = root / "tickets"; producer.TICKETS.mkdir()
            producer.POLICY = root / "policy.json"
            producer.POLICY.write_text(json.dumps({"queue": {"max_queued": 1, "map_reserve": 0}}))
            producer.JOBS = root / "jobs.json"
            producer.JOBS.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                "ticket:engine.unrelated/v1": {"work_type": "engine", "state": "working"},
            }}))
            parent_id = "ticket:map.fixture/v1"
            parent_path = producer.ticket_path_for_id(parent_id)
            parent_path.write_text(json.dumps({"schema": "factory.ticket-spec/v1", "id": parent_id}))
            (producer.RUNS / "receipt.json").write_text(json.dumps({
                "schema": "factory.observation-receipt/v1", "outcome": "blocked_by_capability",
                "ticket": {"id": parent_id}, "capability_demand": capability,
            }))
            # The Engine lane is already at its (artificially tiny) cap, and no
            # Map-type resume exists anywhere in this receipt set. The producer
            # must still fall back to proposing the Engine ticket rather than
            # silently reporting nothing actionable.
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                producer.main()
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["ticket"]["work_type"], "engine")

    def test_capability_producer_skips_already_ground_truth_satisfied_parent(self):
        producer = load_script("factory_ng_dependency_satisfied_skip_test",
                               "factory-ng-produce-capability-dependency.py")
        capability = {
            "key": "damage_amount_from_devotion",
            "summary": "resolve devotion as a damage amount",
            "specification": {
                "required_behavior": "Resolve devotion as damage.",
                "source_misses": [{"card": "Fanatic of Mogis", "paragraph": "exact", "required_behavior": "same"}],
                "negative_examples": [], "expected_unlock": 1,
            },
        }
        with tempfile.TemporaryDirectory(prefix="factory-ng-dependency-satisfied-skip-", dir=OPS) as directory:
            root = Path(directory)
            producer.RUNS = root / "runs"; producer.RUNS.mkdir()
            producer.TICKETS = root / "tickets"; producer.TICKETS.mkdir()
            producer.POLICY = root / "policy.json"
            producer.POLICY.write_text(json.dumps({"queue": {"max_queued": 12, "map_reserve": 2}}))
            parent_id = "ticket:map.fixture/v1"
            producer.JOBS = root / "jobs.json"
            producer.JOBS.write_text(json.dumps({"schema": "factory.ng-jobs/v1", "jobs": {
                parent_id: {"state": "completed", "outcome": "ground_truth_satisfied_after_dependency"},
            }}))
            parent_path = producer.ticket_path_for_id(parent_id)
            parent_path.write_text(json.dumps({"schema": "factory.ticket-spec/v1", "id": parent_id}))
            (producer.RUNS / "receipt.json").write_text(json.dumps({
                "schema": "factory.observation-receipt/v1", "outcome": "blocked_by_capability",
                "ticket": {"id": parent_id}, "capability_demand": capability,
            }))
            # A prior pass already resolved this parent as ground-truth-satisfied.
            # The scan must skip it outright rather than recomputing resumed_map()
            # and re-reporting parent_satisfied on every future call.
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                producer.main()
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "no_capability_demand")

    def test_reparse_card_probe_packs_without_text_field(self):
        ticket = OPS / "docs/factory-ng/tickets/map-plan-damage-fanatic-of-mogis-78b4874cfb-v1.json"
        result = subprocess.run(
            ["python3", str(OPS / "scripts/map-ticket-spec-pack.py"),
             "--ticket-spec", str(ticket), "--repo", str(SOURCE)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("equal to your devotion to red", result.stdout)
        self.assertIn("reparse_card(load_card('Fanatic of Mogis'))", result.stdout)

    def test_documented_scope_gate_is_machine_checked(self):
        runner = load_script("factory_ng_runner_test", "factory-ng-run-engine-ticket.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-gate-test-") as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "allowed.py").write_text("value = 1\n")
            ticket = {"scope": {"allowed_paths": ["allowed.py"]}}
            result = runner.ticket_gate(
                "git status --porcelain adds or changes only allowed.py", root, ticket)
            self.assertEqual(result["exit_code"], 0, result)
            (root / "outside.py").write_text("value = 2\n")
            result = runner.ticket_gate(
                "git status --porcelain adds or changes only allowed.py", root, ticket)
            self.assertEqual(result["exit_code"], 1, result)


    def test_model_call_classifies_expired_oauth(self):
        model_call = load_script("factory_ng_model_call_auth_test", "model_call.py")
        self.assertTrue(model_call.authentication_failed("Failed to authenticate: OAuth session expired and could not be refreshed"))
        self.assertFalse(model_call.authentication_failed("candidate gate failed"))

    def test_authentication_failure_refunds_once_and_pauses_worker(self):
        controller = load_script("factory_ng_controller_auth_test", "factory-ng-controller.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-auth-test-") as directory:
            controller.WORKER_PAUSES = Path(directory) / "worker-pauses.json"
            job = {"ticket_id": "ticket:test/v1", "worker": "claude",
                   "dispatch_profile": "claude-staged@1.0.0", "attempts": 2}
            self.assertTrue(controller.refund_authentication_attempt(job, "receipt.json"))
            self.assertFalse(controller.refund_authentication_attempt(job, "receipt.json"))
            self.assertEqual(job["attempts"], 1)
            controller.pause_worker_for_authentication(job, "receipt.json")
            pauses = controller.load_worker_pauses()["workers"]
            self.assertIn("claude", pauses)
            availability = controller.worker_availability({"claude-staged@1.0.0": [{
                "id": "claude", "profile": "claude-staged@1.0.0"}]})
            self.assertFalse(availability["claude-staged@1.0.0"]["claude"]["allowed"])

    def test_historical_oauth_attempt_is_refunded_and_requeued(self):
        controller = load_script("factory_ng_controller_auth_migration_test", "factory-ng-controller.py")
        with tempfile.TemporaryDirectory(prefix="factory-ng-auth-migration-") as directory:
            root = Path(directory)
            controller.OPS = root
            controller.RUNS = root / "docs/factory-ng/runs"
            controller.RUNS.mkdir(parents=True)
            raw = controller.RUNS / "raw.json"
            raw.write_text("Failed to authenticate: OAuth session expired and could not be refreshed")
            receipt = controller.RUNS / "receipt.json"
            receipt.write_text(json.dumps({"schema": "factory.observation-receipt/v1",
                "ticket": {"id": "ticket:test/v1"},
                "raw_artifacts": [{"path": str(raw.relative_to(root))}]}))
            jobs = {"schema": "factory.ng-jobs/v1", "jobs": {"ticket:test/v1": {
                "ticket_id": "ticket:test/v1", "state": "failed",
                "outcome": "infrastructure_failed", "attempts": 1}}}
            controller.migrate_authentication_failures(jobs)
            job = jobs["jobs"]["ticket:test/v1"]
            self.assertEqual((job["state"], job["attempts"], job["outcome"]),
                             ("queued", 0, controller.AUTHENTICATION_OUTCOME))
            self.assertEqual(jobs["oauth_retry_migration_v1"]["refunded_attempts"], 1)

if __name__ == "__main__":
    unittest.main()
