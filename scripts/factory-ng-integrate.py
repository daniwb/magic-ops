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
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from factory_ng_receipts import write_receipt
from factory_ng_vocabulary import engine_registration_gate
from factory_ng_quiet import compilation_status
from factory_ng_safety import source_problem, decoded_output


OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE
RUNS = OPS / "docs/factory-ng/runs"
POLICY = OPS / "config/factory-ng-policy.json"
GO = str(OPS / "scripts/go-cache-run.sh")


def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stamp():
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def call(command, cwd, timeout=3600, extra_env=None):
    started = time.monotonic()
    try:
        env = os.environ.copy()
        env["PATH"] = "/usr/local/go/bin:" + env.get("PATH", "")
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                                timeout=timeout, env=env)
        return {"exit_code": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr,
                "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": 124, "stdout": decoded_output(exc.stdout), "stderr": decoded_output(exc.stderr),
                "elapsed_ms": round((time.monotonic() - started) * 1000)}


def gate(identifier, command, result):
    detail = (result["stdout"] + "\n" + result["stderr"]).strip()[-1600:]
    return {"id": identifier, "command": " ".join(command),
            "outcome": "passed" if result["exit_code"] == 0 else "failed",
            "exit_code": result["exit_code"], "elapsed_ms": result["elapsed_ms"],
            "detail": detail}


def cache_artifact_failure(result):
    """True only for errors consistent with a cache file vanishing mid-gate."""
    detail = (result.get("stdout", "") + "\n" + result.get("stderr", "")).lower()
    return ("failed to initialize build cache" in detail
            or ("no such file or directory" in detail
                and ("/go-build" in detail or "/.gocache" in detail)))


def cached_gate(identifier, command, cwd, gates, timeout):
    """Run a managed Go gate and retry cache-artifact loss once in isolation."""
    result = call(command, cwd, timeout=timeout)
    if result["exit_code"] == 0 or not cache_artifact_failure(result):
        gates.append(gate(identifier, command, result))
        return result
    first = gate(identifier, command, result)
    first["outcome"] = "infrastructure_retry"
    first["classification"] = "cache_artifact_disappeared"
    gates.append(first)
    with tempfile.TemporaryDirectory(prefix="factory-ng-gocache-retry-", dir="/tmp") as retry_cache:
        retry = call(command, cwd, timeout=timeout,
                     extra_env={"GO_CACHE_ROOT": retry_cache})
    retried = gate(identifier + "-cache-retry", command, retry)
    retried["classification"] = "isolated_cache_retry"
    gates.append(retried)
    return retry


def full_gate_commands(tag):
    return [
        ("reparse-flip", [sys.executable, "scripts/paragraph/reparse.py", "--flip-batch", "300", "--tag", tag], 1800),
        ("reparse-import", [sys.executable, "scripts/paragraph/reparse.py", "--import-corpus", "--tag", tag], 1800),
        ("go-build", [GO, "build", "./..."], 1800),
        ("game-tests", [GO, "test", "./game/", "-count=1"], 1800),
        ("focused-go", [GO, "test", "./cards/", "-run", "TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes", "-count=1"], 1800),
        ("full-sharded-suite", [GO, "exec", "bash", "scripts/test-cards-sharded.sh", "6"], 7200),
    ]


def run_full_gates(clone, gates, tag):
    for identifier, command, timeout in full_gate_commands(tag):
        cwd = clone / "backend" if identifier in ("go-build", "focused-go", "game-tests") else clone
        if identifier.startswith("reparse-"):
            result = call(command, cwd, timeout=timeout)
            gates.append(gate(identifier, command, result))
        else:
            result = cached_gate(identifier, command, cwd, gates, timeout)
        if result["exit_code"]:
            return False
    return True


def lock(name, wait=False):
    Path("/tmp/orch").mkdir(parents=True, exist_ok=True)
    handle = open("/tmp/orch/%s.lock" % name, "a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    except BlockingIOError:
        handle.close()
        return None
    return handle


def git(cwd, *args, timeout=180):
    return call(["git", *args], cwd, timeout=timeout)


def clean(path):
    return not source_problem(path)


def semantic_contract(observation):
    """Enumerate the original semantic checks without executing them."""
    ticket_path = OPS / observation['ticket']['path']
    if digest(ticket_path) != observation['ticket']['sha256']:
        raise RuntimeError('accepted TicketSpec digest mismatch')
    ticket = json.loads(ticket_path.read_text())
    composed = observation.get('execution', {}).get('mode') == 'isolated_composed_verification'
    checks = []
    if composed and ticket.get('work_type') == 'engine' and 'backend/game/ability_effects.go' in ticket.get('scope', {}).get('allowed_paths', []):
        checks.append({'id': 'engine-vocabulary-handoff', 'ticket_id': ticket['id']})
    for index, command in enumerate(ticket.get('gates', [])):
        scope_only = ((' only ' in command and command.startswith(('git status --porcelain ', 'git diff --name-only ')))
                      or command == 'git diff --check')
        if scope_only or (not composed and not ('go test' in command or 'python' in command)):
            continue
        if command in ('cd backend && go test ./game ./cards',
                       'cd backend && go test ./game ./cards -count=1'):
            continue
        checks.append({'id': 'composed-ticket-%d' % index, 'command': command, 'ticket_id': ticket['id']})
    return ticket, checks


def semantic_gates(observation, clone, gates):
    """Revalidate the accepted TicketSpec on the composed production revision."""
    ticket, checks = semantic_contract(observation)
    spec = importlib.util.spec_from_file_location('ng_integration_gate_runner',
                                                  OPS / 'scripts/factory-ng-run-map-ticket.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    for check in checks:
        if check['id'] == 'engine-vocabulary-handoff':
            checked = engine_registration_gate(ticket, clone)
        else:
            result = runner.run_ticket_gate(check['command'], clone, ticket)
            checked = gate(check['id'], [check['command']], result)
        checked['ticket_id'] = ticket['id']
        gates.append(checked)
        if checked['outcome'] != 'passed':
            return False
    return True


def apply_candidate(observation, clone, gates, resolution=None):
    execution = observation.get('execution', {})
    revision = execution.get('source_revision')
    if revision and git(clone, 'merge-base', '--is-ancestor', revision, 'HEAD')['exit_code']:
        raise RuntimeError('candidate source revision is not an ancestor of current main')
    candidate = execution.get('candidate_commit')
    if candidate and git(clone, 'merge-base', '--is-ancestor', candidate, 'HEAD')['exit_code'] == 0:
        return
    patch = OPS / execution.get('candidate_patch', '')
    if not patch.is_file():
        raise RuntimeError('accepted candidate has no durable patch')
    if digest(patch) != execution.get('candidate_patch_sha256'):
        raise RuntimeError('candidate patch digest mismatch')
    if resolution is not None:
        if (resolution.get('original_patch_sha256') != digest(patch)
                or resolution.get('ticket_sha256') != observation['ticket']['sha256']
                or not resolution.get('reason')):
            raise RuntimeError('reviewed resolution does not bind the original candidate and ticket')
        resolved_patch = OPS / resolution['patch']
        if digest(resolved_patch) != resolution.get('patch_sha256'):
            raise RuntimeError('reviewed resolution patch digest mismatch')
        if git(clone, 'merge-base', '--is-ancestor', resolution['source_revision'], 'HEAD')['exit_code']:
            raise RuntimeError('reviewed resolution source is not an ancestor of current main')
        gates.append({'id': 'operator-reviewed-resolution', 'outcome': 'passed',
                      'detail': resolution['reason'], 'resolution': resolution})
        patch = resolved_patch
    if git(clone, 'apply', '--reverse', '--check', str(patch))['exit_code'] == 0:
        gates.append({'id': 'candidate-already-present', 'outcome': 'passed',
                      'command': 'git apply --reverse --check',
                      'detail': 'The complete accepted patch is already present; revalidate its semantics before push retry.'})
        return
    result = git(clone, 'am', '--3way', str(patch), timeout=300)
    gates.append(gate('candidate-apply', ['git', 'am', '--3way', str(patch)], result))
    if result['exit_code']:
        raise ValueError(result['stderr'][-800:] or result['stdout'][-800:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, action='append', help="accepted observation receipt; repeat for a wave")
    parser.add_argument("--current-main", action="store_true",
                        help="gate and publish already-integrated local main")
    parser.add_argument("--parent", action="append", default=[],
                        help="receipt path represented by --current-main")
    parser.add_argument("--supersedes", action="append", default=[],
                        help="older integration receipt replaced by this full-gate result")
    parser.add_argument('--reviewed-resolutions', type=Path,
                        help='explicit operator-reviewed patch manifest; original semantic and full gates still apply')
    args = parser.parse_args()
    resolutions = {}
    if args.reviewed_resolutions:
        manifest = json.loads(args.reviewed_resolutions.read_text())
        if manifest.get('schema') != 'factory.reviewed-merge-resolutions/v1':
            parser.error('invalid reviewed merge resolution manifest')
        resolutions = manifest['resolutions']
    if bool(args.receipt) == bool(args.current_main):
        parser.error("choose exactly one of --receipt or --current-main")

    settings = json.loads(POLICY.read_text())
    if not compilation_status(settings)['allowed']:
        print(json.dumps({'status': 'integration_busy', 'reason': 'Compilation/testing switch is off.'}))
        return 0
    policy = settings.get("integration", {})
    if not policy.get("automatic", False) and not args.current_main:
        print(json.dumps({"status": "integration_disabled"}))
        return 0

    observations = []
    included = []
    excluded = {}
    parents = list(args.parent)
    slug = "current-main"
    for input_path in args.receipt or []:
        receipt_path = input_path.resolve()
        observation = json.loads(receipt_path.read_text())
        if observation.get("schema") != "factory.observation-receipt/v1" or not str(observation.get("outcome", "")).startswith("accepted"):
            parser.error("receipt is not an accepted factory observation")
        observations.append((receipt_path, observation))
        slug = observation["ticket"]["id"].removeprefix("ticket:").replace("/", "-").replace(".", "-")
    if len(observations) > 1:
        slug = 'wave-' + hashlib.sha256('\n'.join(str(p) for p, _ in observations).encode()).hexdigest()[:12]

    integration_lock = lock("openmagic-integration", wait=bool(resolutions))
    if integration_lock is None:
        print(json.dumps({"status": "integration_busy", "reason": "openmagic integration lock held"}))
        return 75

    clone = Path(tempfile.mkdtemp(prefix="factory-ng-integrate-", dir="/tmp"))
    receipt_out = RUNS / (stamp() + "-" + slug + "-" + str(time.time_ns()) + "-integration.json")
    RUNS.mkdir(parents=True, exist_ok=True)
    gates = []
    base = "unavailable"
    result_commit = "unavailable"
    pushed = False
    full_gate_execution = {"full_gate_host": "local"}
    outcome = "infrastructure_failed"
    reason = ""
    try:
        problem = source_problem(SOURCE)
        if problem:
            outcome = 'integration_source_blocked'
            raise RuntimeError(problem)
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

        # A single candidate keeps its individual failure attribution. For a
        # wave, compose first: compiling every intermediate Engine revision
        # needlessly invalidates the shared package cache.
        remote_semantics = (settings.get('integration', {}).get('remote', {}).get('enabled') is True
                            and settings['integration']['remote'].get('include_semantics') is True)
        single_candidate_checks = len(observations) == 1 and not resolutions
        for observation_path, observation in observations:
            candidate_base = git(clone, 'rev-parse', 'HEAD')['stdout'].strip()
            candidate_gates = []
            try:
                apply_candidate(observation, clone, candidate_gates, resolutions.get(observation['ticket']['id']))
                if single_candidate_checks and not remote_semantics and not semantic_gates(observation, clone, candidate_gates):
                    raise ValueError('composed TicketSpec semantic gate failed')
            except (ValueError, RuntimeError) as exc:
                failed_outcome = ('full_gate_failed' if any(
                    g['id'].startswith('composed-ticket-') and g['outcome'] == 'failed'
                    for g in candidate_gates) else
                    'candidate_conflict' if isinstance(exc, ValueError) else 'infrastructure_failed')
                excluded[observation['ticket']['id']] = {
                    'status': failed_outcome, 'reason': str(exc), 'gates': candidate_gates}
                # This checkout is our disposable integration clone. Restore only
                # that clone, retaining the accepted prefix for the rest of the wave.
                git(clone, 'am', '--abort')
                restored = git(clone, 'reset', '--hard', candidate_base)
                if restored['exit_code']:
                    raise RuntimeError('could not restore disposable candidate prefix')
                continue
            included.append((observation_path, observation))
            gates.extend(candidate_gates)
            parents.extend([observation['ticket']['id'], str(observation_path.relative_to(OPS))])
        if observations and not included:
            outcome = 'no_integratable_candidates'
            raise ValueError('every candidate was isolated with its own failure evidence')

        # Every original semantic contract runs on the final composition.
        # A red wave cannot publish; the controller's existing isolated retries
        # attribute failures and recover good candidates through all gates.
        if not single_candidate_checks and not remote_semantics:
            for _, observation in included:
                if not semantic_gates(observation, clone, gates):
                    outcome = 'full_gate_failed'
                    raise ValueError('combined wave invalidated a TicketSpec semantic gate')
        tag = "factory-ng-" + time.strftime("%m%d-%H%M", time.gmtime())
        from factory_ng_full_gate_remote import run_with_fallback
        semantic_observations = [observation for _, observation in included] if remote_semantics else []
        semantic_specs = [check for observation in semantic_observations
                          for check in semantic_contract(observation)[1]]
        def local_with_semantics(clone, gates, tag):
            for observation in semantic_observations:
                if not semantic_gates(observation, clone, gates):
                    return False
            return run_full_gates(clone, gates, tag)
        passed, full_gate_execution = run_with_fallback(
            clone, gates, tag, settings,
            local_runner=local_with_semantics, commands=full_gate_commands(tag),
            semantic_observations=semantic_observations, semantic_specs=semantic_specs)
        if not passed:
            outcome = "full_gate_failed"
            reason = "full production gate failed"

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
    except ValueError as exc:
        reason = str(exc)
    except Exception as exc:
        reason = str(exc)
        if outcome not in ("candidate_conflict", "full_gate_failed", "integration_source_blocked"):
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
            "execution": full_gate_execution,
            "excluded_candidates": excluded,
            "progress": {"verified_revision": result_commit if outcome != "full_gate_failed" else "unavailable",
                         "verification": "reparse wave plus complete six-shard production suite"},
        }
        if args.supersedes and outcome in ("pushed_full_production_gate_green", "committed_locally_full_production_gate_green"):
            value["supersedes"] = args.supersedes
        if reason:
            value["reason"] = reason
        write_receipt(receipt_out, value)
        shutil.rmtree(clone, ignore_errors=True)
        integration_lock.close()
    receipt_name = str(receipt_out.relative_to(OPS))
    ticket_results = {}
    for _, observation in observations:
        ticket_id = observation['ticket']['id']
        item = excluded.get(ticket_id, {'status': outcome, 'reason': reason})
        ticket_results[ticket_id] = {**item, 'receipt': receipt_name}
    print(json.dumps({"status": outcome, "receipt": receipt_name,
                      "ticket_results": ticket_results,
                      "result_commit": result_commit, "pushed": pushed}, sort_keys=True))
    return 0 if outcome in ("pushed_full_production_gate_green", "committed_locally_full_production_gate_green") else 1


if __name__ == "__main__":
    raise SystemExit(main())
