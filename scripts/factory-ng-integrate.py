#!/usr/bin/env python3
"""Integrate one accepted NG patch (or current local main) through full gates.

Models never call this program.  The controller invokes it only after an
accepted observation receipt.  All validation happens in a disposable clone;
the canonical checkout is fast-forwarded only after every production gate is
green.  A green gate automatically pushes when policy enables it.  Deployment
is deliberately a separate policy because it mutates the live service.
"""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
SOURCE = Path("/opt/development/test/openmagic")
RUNS = OPS / "docs/factory-ng/runs"
POLICY = OPS / "config/factory-ng-policy.json"
GO = "/usr/local/go/bin/go"


def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stamp():
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def call(command, cwd, timeout=3600):
    started = time.monotonic()
    try:
        env = os.environ.copy()
        env["PATH"] = "/usr/local/go/bin:" + env.get("PATH", "")
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                                timeout=timeout, env=env)
        return {"exit_code": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr,
                "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "",
                "elapsed_ms": round((time.monotonic() - started) * 1000)}


def gate(identifier, command, result):
    detail = (result["stdout"] + "\n" + result["stderr"]).strip()[-1600:]
    return {"id": identifier, "command": " ".join(command),
            "outcome": "passed" if result["exit_code"] == 0 else "failed",
            "exit_code": result["exit_code"], "elapsed_ms": result["elapsed_ms"],
            "detail": detail}


def lock(name):
    Path("/tmp/orch").mkdir(parents=True, exist_ok=True)
    handle = open("/tmp/orch/%s.lock" % name, "a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def git(cwd, *args, timeout=180):
    return call(["git", *args], cwd, timeout=timeout)


def clean(path):
    return git(path, "status", "--porcelain")["stdout"].strip() == ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, help="accepted observation receipt")
    parser.add_argument("--current-main", action="store_true",
                        help="gate and publish already-integrated local main")
    parser.add_argument("--parent", action="append", default=[],
                        help="receipt path represented by --current-main")
    parser.add_argument("--supersedes", action="append", default=[],
                        help="older integration receipt replaced by this full-gate result")
    args = parser.parse_args()
    if bool(args.receipt) == bool(args.current_main):
        parser.error("choose exactly one of --receipt or --current-main")

    policy = json.loads(POLICY.read_text()).get("integration", {})
    if not policy.get("automatic", False) and not args.current_main:
        print(json.dumps({"status": "integration_disabled"}))
        return 0

    observation = None
    parents = list(args.parent)
    slug = "current-main"
    if args.receipt:
        receipt_path = args.receipt.resolve()
        observation = json.loads(receipt_path.read_text())
        if observation.get("schema") != "factory.observation-receipt/v1" or not str(observation.get("outcome", "")).startswith("accepted"):
            parser.error("receipt is not an accepted factory observation")
        parents = list(args.parent) + [observation["ticket"]["id"], str(receipt_path.relative_to(OPS))]
        slug = observation["ticket"]["id"].removeprefix("ticket:").replace("/", "-").replace(".", "-")

    integration_lock = lock("openmagic-integration")
    if integration_lock is None:
        print(json.dumps({"status": "integration_busy", "reason": "openmagic integration lock held"}))
        return 75

    clone = Path(tempfile.mkdtemp(prefix="factory-ng-integrate-", dir="/tmp"))
    receipt_out = RUNS / (stamp() + "-" + slug + "-integration.json")
    RUNS.mkdir(parents=True, exist_ok=True)
    gates = []
    base = "unavailable"
    result_commit = "unavailable"
    pushed = False
    outcome = "infrastructure_failed"
    reason = ""
    try:
        if not clean(SOURCE):
            raise RuntimeError("canonical integration checkout is dirty")
        fetch = git(SOURCE, "fetch", "-q", "origin", "refs/heads/main:refs/remotes/origin/main")
        if fetch["exit_code"] != 0:
            raise RuntimeError("origin/main fetch failed: " + fetch["stderr"][-500:])
        base = git(SOURCE, "rev-parse", "HEAD")["stdout"].strip()
        ancestry = git(SOURCE, "merge-base", "--is-ancestor", "origin/main", "HEAD")
        if ancestry["exit_code"] != 0:
            raise RuntimeError("local main is not a fast-forward descendant of origin/main")
        cloned = git(OPS, "clone", "--quiet", "--no-hardlinks", str(SOURCE), str(clone), timeout=300)
        if cloned["exit_code"] != 0:
            raise RuntimeError("integration clone failed: " + cloned["stderr"][-500:])
        # The canonical corpus snapshot is intentionally gitignored (about
        # 50 MB) but import-corpus requires it. Expose it read-only to the
        # disposable clone; all generated output remains inside the clone.
        corpus_input = SOURCE / "corpus/AtomicCards.json.gz"
        clone_input = clone / "corpus/AtomicCards.json.gz"
        if not corpus_input.is_file():
            raise RuntimeError("canonical AtomicCards corpus input is missing")
        if not clone_input.exists():
            clone_input.symlink_to(corpus_input)

        if observation:
            source_revision = observation.get("execution", {}).get("source_revision", "")
            if source_revision and git(clone, "merge-base", "--is-ancestor", source_revision, "HEAD")["exit_code"] != 0:
                raise RuntimeError("candidate source revision is not an ancestor of current main")
            candidate = observation.get("execution", {}).get("candidate_commit", "")
            already_present = candidate and git(clone, "merge-base", "--is-ancestor", candidate, "HEAD")["exit_code"] == 0
            if not already_present:
                patch_name = observation.get("execution", {}).get("candidate_patch", "")
                patch_path = OPS / patch_name if patch_name else None
                temporary_patch = None
                if not patch_path or not patch_path.is_file():
                    candidate_clone = Path(observation.get("execution", {}).get("candidate_clone", ""))
                    if not candidate or not candidate_clone.is_dir():
                        raise RuntimeError("accepted candidate has no durable patch or recoverable clone")
                    exported = git(candidate_clone, "format-patch", "-1", "--stdout", candidate)
                    if exported["exit_code"] != 0:
                        raise RuntimeError("candidate export failed: " + exported["stderr"][-500:])
                    temporary_patch = clone / ".factory-ng-candidate.patch"
                    temporary_patch.write_text(exported["stdout"])
                    patch_path = temporary_patch
                expected = observation.get("execution", {}).get("candidate_patch_sha256")
                if expected and digest(patch_path) != expected:
                    raise RuntimeError("candidate patch digest mismatch")
                applied = git(clone, "am", "--3way", str(patch_path), timeout=300)
                gates.append(gate("candidate-apply", ["git", "am", "--3way", str(patch_path)], applied))
                if applied["exit_code"] != 0:
                    outcome = "candidate_conflict"
                    reason = applied["stderr"][-800:]
                    raise ValueError(reason)

        tag = "factory-ng-" + time.strftime("%m%d-%H%M", time.gmtime())
        commands = [
            ("reparse-flip", [sys.executable, "scripts/paragraph/reparse.py", "--flip-batch", "300", "--tag", tag], 1800),
            ("reparse-import", [sys.executable, "scripts/paragraph/reparse.py", "--import-corpus", "--tag", tag], 1800),
            ("go-build", [GO, "build", "./..."], 1800),
            ("focused-go", [GO, "test", "./cards/", "-run", "TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes", "-count=1"], 1800),
        ]
        for identifier, command, timeout in commands:
            cwd = clone / "backend" if identifier in ("go-build", "focused-go") else clone
            result = call(command, cwd, timeout=timeout)
            gates.append(gate(identifier, command, result))
            if result["exit_code"] != 0:
                outcome = "full_gate_failed"
                reason = "%s failed" % identifier
                break
        if outcome != "full_gate_failed":
            shard = call(["bash", "scripts/test-cards-sharded.sh", "6"], clone, timeout=7200)
            gates.append(gate("full-sharded-suite", ["bash", "scripts/test-cards-sharded.sh", "6"], shard))
            if shard["exit_code"] != 0:
                outcome = "full_gate_failed"
                reason = "full sharded suite failed"

        if outcome != "full_gate_failed":
            git(clone, "add", "-A", "backend/data/carddb")
            if git(clone, "diff", "--cached", "--quiet")["exit_code"] != 0:
                committed = git(clone, "-c", "user.name=Factory NG", "-c", "user.email=factory-ng@local",
                                "commit", "-m", "factory-ng: import fully gated corpus wave")
                if committed["exit_code"] != 0:
                    raise RuntimeError("carddb wave commit failed: " + committed["stderr"][-500:])
            result_commit = git(clone, "rev-parse", "HEAD")["stdout"].strip()
            if git(SOURCE, "rev-parse", "HEAD")["stdout"].strip() != base or not clean(SOURCE):
                raise RuntimeError("canonical checkout changed during full gate")
            fetched = git(SOURCE, "fetch", "-q", str(clone), result_commit)
            merged = git(SOURCE, "merge", "--ff-only", "--no-edit", "FETCH_HEAD") if fetched["exit_code"] == 0 else fetched
            if merged["exit_code"] != 0:
                raise RuntimeError("canonical fast-forward failed: " + merged["stderr"][-500:])
            outcome = "committed_locally_full_production_gate_green"

            if policy.get("push_when_full_gate_green", False):
                deploy_lock = lock("factory-deploy")
                if deploy_lock is None:
                    outcome = "push_deferred_deploy_lock_busy"
                    reason = "deployment/push lock held"
                else:
                    try:
                        push = git(SOURCE, "push", "origin", "main", timeout=600)
                        gates.append(gate("push", ["git", "push", "origin", "main"], push))
                        pushed = push["exit_code"] == 0
                        if pushed:
                            outcome = "pushed_full_production_gate_green"
                        else:
                            outcome = "push_failed_after_full_gate"
                            reason = push["stderr"][-800:]
                    finally:
                        deploy_lock.close()
    except ValueError:
        pass
    except Exception as exc:
        reason = str(exc)
        if outcome not in ("candidate_conflict", "full_gate_failed"):
            outcome = "infrastructure_failed"
    finally:
        value = {
            "schema": "factory.integration-receipt/v1", "created_at": utc(),
            "parents": parents, "outcome": outcome,
            "policy": {"automatic": bool(policy.get("automatic")),
                       "push_when_full_gate_green": bool(policy.get("push_when_full_gate_green")),
                       "deploy_after_push": bool(policy.get("deploy_after_push"))},
            "source": {"base_commit": base, "result_commit": result_commit,
                       "pushed": pushed, "deployed": False},
            "gates": gates,
            "progress": {"verified_revision": result_commit if outcome != "full_gate_failed" else "unavailable",
                         "verification": "reparse wave plus complete six-shard production suite"},
        }
        if args.supersedes and outcome in ("pushed_full_production_gate_green", "committed_locally_full_production_gate_green"):
            value["supersedes"] = args.supersedes
        if reason:
            value["reason"] = reason
        receipt_out.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        shutil.rmtree(clone, ignore_errors=True)
        integration_lock.close()
    print(json.dumps({"status": outcome, "receipt": str(receipt_out.relative_to(OPS)),
                      "result_commit": result_commit, "pushed": pushed}, sort_keys=True))
    return 0 if outcome in ("pushed_full_production_gate_green", "committed_locally_full_production_gate_green") else 1


if __name__ == "__main__":
    raise SystemExit(main())
