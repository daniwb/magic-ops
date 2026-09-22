#!/usr/bin/env python3
"""Deterministic concurrency tests for the centralized Go cache barrier."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
RUNNER = OPS / "scripts/go-cache-run.sh"


class GoCacheBarrierTest(unittest.TestCase):
    def test_cleaner_drains_existing_run_and_blocks_new_run(self):
        with tempfile.TemporaryDirectory(prefix="go-cache-barrier-test-") as directory:
            root = Path(directory)
            trace = root / "trace"
            fake_go = root / "go"
            fake_go.write_text("#!/bin/sh\n"
                               "echo clean-start >> \"$TRACE\"\n"
                               "sleep 0.15\n"
                               "echo clean-end >> \"$TRACE\"\n")
            fake_go.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "GO_CACHE_ROOT": str(root / "cache"),
                "GO_CACHE_LOCK_DIR": str(root / "locks"),
                "GO_CACHE_STATUS_FILE": str(root / "status.json"),
                "GO_CACHE_GO_BINARY": str(fake_go),
                "TRACE": str(trace),
            })
            first = subprocess.Popen(
                [str(RUNNER), "exec", "bash", "-c",
                 'echo first-start >> "$TRACE"; sleep 0.35; echo first-end >> "$TRACE"'],
                env=env,
            )
            self._wait_for(trace, "first-start")
            cleaner = subprocess.Popen([str(RUNNER), "clean"], env=env)
            self._wait_for_state(root / "status.json", "waiting_for_tests")
            second = subprocess.Popen(
                [str(RUNNER), "exec", "bash", "-c", 'echo second-start >> "$TRACE"'],
                env=env,
            )
            self.assertEqual(first.wait(timeout=3), 0)
            self.assertEqual(cleaner.wait(timeout=3), 0)
            self.assertEqual(second.wait(timeout=3), 0)
            self.assertEqual(trace.read_text().splitlines(), [
                "first-start", "first-end", "clean-start", "clean-end", "second-start",
            ])
            status = json.loads((root / "status.json").read_text())
            self.assertEqual(status["state"], "completed")

    def test_managed_run_forces_the_central_cache(self):
        with tempfile.TemporaryDirectory(prefix="go-cache-env-test-") as directory:
            root = Path(directory)
            output = root / "cache-path"
            env = os.environ.copy()
            env.update({
                "GO_CACHE_ROOT": str(root / "central"),
                "GO_CACHE_LOCK_DIR": str(root / "locks"),
                "GO_CACHE_STATUS_FILE": str(root / "status.json"),
            })
            subprocess.run(
                [str(RUNNER), "exec", "bash", "-c", 'printf %s "$GOCACHE" > "$1"',
                 "test", str(output)], env=env, check=True,
            )
            self.assertEqual(output.read_text(), str(root / "central"))

    def test_clone_paths_share_build_artifacts_and_tests_still_execute(self):
        with tempfile.TemporaryDirectory(prefix='go-cache-clone-test-') as directory:
            root = Path(directory)
            env = os.environ.copy()
            env.update(GO_CACHE_LOCK_DIR=str(root / 'locks'),
                       GO_CACHE_STATUS_FILE=str(root / 'status.json'))
            env.pop('GOFLAGS', None)
            env.pop('GOMAXPROCS', None)
            logs = []
            for name in ('first', 'second'):
                clone = root / name
                clone.mkdir()
                (clone / 'go.mod').write_text('module example.com/' + root.name + '\n\ngo 1.25.0\n')
                (clone / 'probe.go').write_text('package probe\nfunc Value() int { return 42 }\n')
                (clone / 'probe_test.go').write_text(
                    'package probe\nimport "testing"\n'
                    'func TestValue(t *testing.T) { if Value() != 42 { t.Fatal(Value()) }; t.Log("executed") }\n')
                result = subprocess.run([str(RUNNER), 'test', '-x', '-v', '-count=1', './...'],
                                        cwd=clone, env=env, text=True, capture_output=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('executed', result.stdout)
                logs.append(result.stderr)
            self.assertIn('/compile ', logs[0])
            self.assertNotIn('/compile ', logs[1])

    def test_resource_defaults_preserve_caller_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = os.environ.copy()
            env.update(GO_CACHE_ROOT=str(root / 'cache'), GO_CACHE_LOCK_DIR=str(root / 'locks'),
                       GO_CACHE_STATUS_FILE=str(root / 'status.json'),
                       GOMAXPROCS='1', GOFLAGS='-p=1 -trimpath=false')
            result = subprocess.run([str(RUNNER), 'env', 'GOMAXPROCS', 'GOFLAGS'],
                                    env=env, text=True, capture_output=True, check=True)
            self.assertIn('-trimpath -p=2 -p=1 -trimpath=false', result.stdout)
            result = subprocess.run([str(RUNNER), 'exec', 'sh', '-c', 'echo "$GOMAXPROCS"'],
                                    env=env, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), '1')

    def _wait_for(self, path, value):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if path.exists() and value in path.read_text():
                return
            time.sleep(0.02)
        self.fail("timed out waiting for %s in %s" % (value, path))

    def _wait_for_state(self, path, state):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if path.exists():
                try:
                    if json.loads(path.read_text()).get("state") == state:
                        return
                except json.JSONDecodeError:
                    pass
            time.sleep(0.02)
        self.fail("timed out waiting for cache state %s" % state)


if __name__ == "__main__":
    unittest.main()
