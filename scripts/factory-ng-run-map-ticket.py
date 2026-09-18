#!/usr/bin/env python3
"""Run one evidence-complete Map TicketSpec in a disposable clone.

This is the small bridge between Factory NG's deterministic producers and the
already-proven prepared-Qwen path.  The model only proposes edit blocks; this
harness applies them in a clone, owns every gate, and records the outcome.
Nothing is merged, pushed, deployed, or written to the source checkout.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from factory_ng_receipts import write_receipt
from factory_ng_verification import (VerificationPaused, require_compilation, save_proposal, load_proposal, restore_proposal)
from factory_ng_safety import (source_problem, final_gates_pass, test_json_command,
                               require_executed_test, decoded_output, source_wait_receipt)


OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE, local_gate_command
RUNS = OPS / "docs/factory-ng/runs"
CANDIDATES = OPS / "docs/factory-ng/candidates"
GO_CACHE_RUN = str(OPS / "scripts/go-cache-run.sh")


def sha_bytes(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha_file(path):
    return sha_bytes(Path(path).read_bytes())


def run(command, cwd, stdin=None, timeout=1200):
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, input=stdin, text=True,
                                capture_output=True, timeout=timeout)
        return {"exit_code": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr,
                "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": 124, "stdout": decoded_output(exc.stdout), "stderr": decoded_output(exc.stderr) + "\nCommand timed out after %d seconds." % timeout,
                "elapsed_ms": round((time.monotonic() - started) * 1000)}


def output(result):
    return (result["stdout"] + "\n" + result["stderr"]).strip()


def qwen_telemetry(stderr, elapsed_ms):
    match = re.findall(r"tokens: in=(\d+) out=(\d+) cache_r=(\d+) cache_w=(\d+)", stderr)
    if not match:
        unavailable = {"availability": "unavailable", "reason": "adapter emitted no SSE usage record"}
        return {"input_tokens": unavailable, "output_tokens": unavailable,
                "cache_read_tokens": unavailable, "cache_write_tokens": unavailable,
                "reasoning_tokens": {"availability": "unavailable", "reason": "local adapter disables thinking"},
                "provider_cost_usd": {"availability": "unavailable", "reason": "local provider does not report cost"},
                "elapsed_ms": elapsed_ms}
    uncached, out_tokens, cached, cache_write = map(int, match[-1])
    return {"input_tokens": uncached + cached, "output_tokens": out_tokens,
            "cache_read_tokens": cached, "cache_write_tokens": cache_write,
            "reasoning_tokens": {"availability": "unavailable", "reason": "local adapter disables thinking"},
            "provider_cost_usd": {"availability": "unavailable", "reason": "local provider does not report cost"},
            "elapsed_ms": elapsed_ms}


def gate(identifier, command, result):
    return {"id": identifier, "command": command, "outcome": "passed" if result["exit_code"] == 0 else "failed",
            "detail": output(result)[-1200:]}


def validated_capability(reply):
    module_path = OPS / "scripts/capability-contract.py"
    spec = importlib.util.spec_from_file_location("factory_ng_capability_contract", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.extract(reply)
    module.validate_oracle(value, str(SOURCE))
    return value


def supports_profile(ticket, profile):
    execution = ticket.get("execution", {})
    compatible = execution.get("compatible_profiles")
    if not compatible:
        preferred = execution.get("selected_profile")
        retry = int(ticket.get("production", {}).get("retry_generation", 0)) > 0
        compatible = ([preferred, "claude-staged@1.0.0", "codex-constrained@1.0.0"] if retry else
                      [preferred, "qwen-prepared-direct@1.0.2", "claude-staged@1.0.0",
                       "codex-constrained@1.0.0"])
    return profile in compatible


def run_ticket_gate(command, clone, ticket):
    """Run a TicketSpec gate, including the compact remeasurement shorthand."""
    if ((command.startswith("git status --porcelain ") and " only " in command) or
            (command.startswith("git diff --name-only ") and " only " in command)):
        names = run(["git", "status", "--porcelain"], clone, timeout=30)
        changed = [line[3:] for line in names["stdout"].splitlines() if len(line) > 3]
        allowed = set(ticket.get("scope", {}).get("allowed_paths", []))
        names["exit_code"] = 0 if changed and set(changed).issubset(allowed) else 1
        names["stdout"] = "changed=" + ",".join(changed)
        return names
    suffix = " reports zero remaining pinned members"
    executable = command[:-len(suffix)] if command.endswith(suffix) else command
    no_output = " produces no output"
    if executable.endswith(no_output):
        executable = executable[:-len(no_output)]
    shell_command = ["bash", "-lc", test_json_command(local_gate_command(executable))]
    if re.search(r"\bgo\s+(build|test|vet)\b", executable):
        shell_command = [GO_CACHE_RUN, "exec", *shell_command]
    # Compilation at reduced CPU capacity needs the full build allowance.
    gate_timeout = 1800 if re.search(r'\bgo\s+(build|test|vet)\b', executable) else 720
    result = run(shell_command, clone, timeout=gate_timeout)
    require_executed_test(executable, result)
    if "factory-ng-targeted-demand.py" in executable and "--members-from" in executable and result["exit_code"] == 0:
        try:
            measured = json.loads(result['stdout'])
            if measured.get("member_count") != 0:
                result["exit_code"] = 1
                result["stderr"] += "\npinned remeasurement is not zero"
            if ticket.get('work_type') == 'map' and measured.get('pinned_unresolved_count', 0):
                result['exit_code'] = 1
                result['stderr'] += '\npinned Map card still fails complete parsing; removing one miss category is insufficient'
        except json.JSONDecodeError:
            result["exit_code"] = 1
            result["stderr"] += "\npinned remeasurement did not return JSON"
    if no_output in command and result["exit_code"] == 0 and result["stdout"].strip():
        result["exit_code"] = 1
        result["stderr"] += "\ncommand produced output"
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", required=True, type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--worker", default="qwen-local")
    ap.add_argument("--resume-proposal", type=Path)
    ap.add_argument("--defer-verification", action="store_true")
    args = ap.parse_args()
    ticket_path = args.ticket.resolve()
    ticket = json.loads(ticket_path.read_text())
    if ticket.get("schema") != "factory.ticket-spec/v1" or ticket.get("work_type") != "map":
        ap.error("only a Map factory.ticket-spec/v1 can use this runner")
    if not supports_profile(ticket, "qwen-prepared-direct@1.0.2"):
        ap.error("ticket is not routed to the prepared-Qwen Map runner")
    problem = source_problem(SOURCE)
    if problem:
        print(json.dumps(source_wait_receipt(ticket_path, ticket, args.worker,
                         'qwen-prepared-direct@1.0.2', args.model, RUNS, OPS, problem)))
        return

    identity = {"worker": args.worker, "model": args.model, "profile": "qwen-prepared-direct@1.0.2"}
    saved = load_proposal(args.resume_proposal, ticket_path, identity) if args.resume_proposal else None
    ticket_id = ticket["id"]
    slug = ticket_id.removeprefix("ticket:").replace("/", "-").replace(".", "-")
    stamp = time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
    clone = Path(tempfile.mkdtemp(prefix="factory-ng-" + slug + "-", dir="/tmp"))
    receipt_path = RUNS / (stamp + "-" + slug + "-qwen.json")
    raw_path = RUNS / (stamp + "-" + slug + "-qwen.raw.txt")
    repair_raw_path = RUNS / (stamp + "-" + slug + "-qwen.repair.raw.txt")
    if saved:
        raw_path = OPS / saved["context"]["raw_path"]
        repair_raw_path = OPS / saved["context"]["repair_raw_path"]
    RUNS.mkdir(parents=True, exist_ok=True)
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    candidate_patch = None
    capability = None
    outcome = "infrastructure_failed"
    try:
        clone_result = run(["git", "clone", "--quiet", "--no-hardlinks", str(SOURCE), str(clone)], OPS, timeout=180)
        if clone_result["exit_code"] != 0:
            raise RuntimeError("clone failed: " + output(clone_result))
        pinned = run(["git", "checkout", "--detach", ticket["source"]["revision"]], clone, timeout=60)
        if pinned["exit_code"] != 0:
            raise RuntimeError("pinned revision checkout failed: " + output(pinned))
        if saved:
            context = restore_proposal(saved, clone)
            proposal, apply_result = context['proposal'], context['apply_result']
            packet_result, telemetry, gates = context['packet_result'], context['telemetry'], context['gates']
        else:
            packet_result = run([sys.executable, str(OPS / "scripts/map-ticket-spec-pack.py"),
                                 "--ticket-spec", str(ticket_path), "--repo", str(clone)], OPS, timeout=180)
            if packet_result["exit_code"] != 0:
                raise RuntimeError("packet failed: " + output(packet_result))
            proposal = run([sys.executable, str(OPS / "scripts/qwen-prepared-call.py"),
                            "--model", args.model, "--max-tokens", "2000"], clone, stdin=packet_result["stdout"], timeout=960)
            raw_path.write_text(proposal["stdout"])
            telemetry = qwen_telemetry(proposal["stderr"], proposal["elapsed_ms"])
            apply_result = run([sys.executable, str(OPS / "scripts/map-pipeline-apply.py")], clone,
                               stdin=proposal["stdout"], timeout=60)
            gates = []
            if proposal["exit_code"] == 0 and apply_result["exit_code"] in (5, 6):
                gates.append(gate("initial-patch-apply", "scripts/map-pipeline-apply.py", apply_result))
                repair_prompt = (packet_result["stdout"] + "\n\n## ONE BOUNDED REPAIR\nYour previous answer was:\n" +
                                 proposal["stdout"] + "\n\nThe strict patch harness rejected it with:\n" +
                                 output(apply_result)[-1600:] +
                                 "\nReturn one complete corrected answer in the original OUTPUT FORMAT. "
                                 "Use NEWFILE for paths that do not exist. No prose.\n")
                repaired = run([sys.executable, str(OPS / "scripts/qwen-prepared-call.py"),
                                "--model", args.model, "--max-tokens", "2000"], clone,
                               stdin=repair_prompt, timeout=960)
                repair_raw_path.write_text(repaired["stdout"])
                repair_telemetry = qwen_telemetry(repaired["stderr"], repaired["elapsed_ms"])
                for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "elapsed_ms"):
                    if isinstance(telemetry.get(key), int) and isinstance(repair_telemetry.get(key), int):
                        telemetry[key] += repair_telemetry[key]
                telemetry["bounded_repair_attempted"] = True
                proposal = repaired
                apply_result = run([sys.executable, str(OPS / "scripts/map-pipeline-apply.py")], clone,
                                   stdin=proposal["stdout"], timeout=60)
        gates.append(gate("patch-apply", "scripts/map-pipeline-apply.py", apply_result))
        outcome = "gate_failed"
        changed = []
        if proposal["exit_code"] != 0:
            outcome = "infrastructure_failed"
        elif apply_result["exit_code"] == 4:
            verdict = re.search(r"\bVERDICT:\s*([A-Z_]+)", proposal["stdout"])
            if verdict and verdict.group(1) == "NEEDS_PRIMITIVE":
                try:
                    capability = validated_capability(proposal["stdout"])
                    outcome = "blocked_by_capability"
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    outcome = "invalid_capability_demand"
                    gates.append({"id": "capability-contract", "command": "validate Oracle capability demand",
                                  "outcome": "failed", "detail": str(exc)[-1200:]})
            else:
                outcome = "parked"
        elif apply_result["exit_code"] != 0:
            # A provider response with no machine edit blocks is a bounded
            # adapter/protocol failure, not a semantic TicketSpec rejection.
            # Let the controller retry it under the infrastructure cap.
            apply_text = output(apply_result).lower()
            outcome = ("infrastructure_failed_model_protocol"
                       if "no edit blocks" in apply_text or "no verdict" in apply_text
                       else "gate_failed")
        elif apply_result["exit_code"] == 0:
            # TicketSpec gates are the acceptance contract.  The first rollout
            # accidentally retained the previous ticket's test/measurement
            # names here, which made every later valid Map proposal fail a
            # foreign test.  Run each current ticket gate in the clone instead.
            if args.defer_verification:
                raise VerificationPaused("Queued for combined focused verification.")
            require_compilation()
            for index, command in enumerate(ticket.get("gates", [])):
                require_compilation()
                commanded = run_ticket_gate(command, clone, ticket)
                gates.append(gate("ticket-gate-%d" % index, command, commanded))
            diffcheck = run(["git", "diff", "--check"], clone, timeout=60)
            gates.append(gate("diff-check", "git diff --check", diffcheck))
            names = run(["git", "status", "--porcelain"], clone, timeout=60)
            changed = [line[3:] for line in names["stdout"].splitlines() if len(line) > 3]
            allowed = set(ticket["scope"]["allowed_paths"])
            scope_result = {"exit_code": 0 if changed and set(changed).issubset(allowed) else 1,
                            "stdout": "changed=" + ",".join(changed), "stderr": ""}
            gates.append(gate("scope", "ticket allowed_paths only", scope_result))
            if final_gates_pass(gates):
                staged = run(["git", "add", "-A"], clone, timeout=60)
                if staged["exit_code"] != 0:
                    gates.append(gate("candidate-stage", "git add -A", staged))
                    commit = staged
                else:
                    commit = run(["git", "-c", "user.name=Factory NG", "-c", "user.email=factory-ng@local", "commit", "-m", "factory-ng: supervised map observation"], clone, timeout=60)
                if commit["exit_code"] == 0:
                    outcome = "accepted_for_dependent_observation"
                    patch_result = run(["git", "format-patch", "-1", "--stdout", "HEAD"], clone, timeout=60)
                    if patch_result["exit_code"] == 0:
                        candidate_patch = CANDIDATES / (stamp + "-" + slug + ".patch")
                        candidate_patch.write_text(patch_result["stdout"])
                    else:
                        outcome = "infrastructure_failed_candidate_export"
                        gates.append(gate("candidate-export", "git format-patch -1 --stdout HEAD", patch_result))
                else:
                    gates.append(gate("candidate-commit", "git commit clone candidate", commit))
        result_commit = run(["git", "rev-parse", "HEAD"], clone, timeout=30)["stdout"].strip()
        source_clean = not subprocess.check_output(["git", "-C", str(SOURCE), "status", "--porcelain"], text=True).strip()
        receipt = {
            "schema": "factory.observation-receipt/v1",
            "ticket": {"id": ticket_id, "path": str(ticket_path.relative_to(OPS)), "sha256": sha_file(ticket_path)},
            "skill": ticket["skill"],
            "model": {"profile": "qwen-prepared-direct@1.0.2", "resolved_model": args.model,
                      "worker": args.worker, "telemetry": telemetry},
            "execution": {"mode": "isolated_clone_observation_only", "source_revision": ticket["source"]["revision"],
                          "source_tree_changed": not source_clean, "candidate_commit": result_commit,
                          "candidate_clone": str(clone), "packet_sha256": sha_bytes(packet_result["stdout"].encode()),
                          "model_exit_code": proposal["exit_code"]},
            "raw_artifacts": ([{"path": str(raw_path.relative_to(OPS)), "sha256": sha_file(raw_path)}] +
                              ([{"path": str(repair_raw_path.relative_to(OPS)),
                                 "sha256": sha_file(repair_raw_path), "kind": "bounded_repair"}]
                               if repair_raw_path.exists() else [])),
            "gates": gates, "outcome": outcome,
            "integration": "eligible_full_gate" if outcome == "accepted_for_dependent_observation" else "observation_only",
            "next_action": "The controller will integrate an accepted candidate under the configured full-gate policy."
        }
        if candidate_patch:
            receipt["execution"]["candidate_patch"] = str(candidate_patch.relative_to(OPS))
            receipt["execution"]["candidate_patch_sha256"] = sha_file(candidate_patch)
            receipt["next_action"] = "Factory NG may integrate this durable patch under its configured full-gate policy."
        if capability:
            receipt["capability_demand"] = capability
            receipt["next_action"] = "The dependency producer will compile this validated atomic demand into an Engine TicketSpec."
        write_receipt(receipt_path, receipt)
        print(json.dumps({"status": outcome, "ticket_id": ticket_id, "worker": args.worker,
                          "receipt": str(receipt_path.relative_to(OPS)), "telemetry": telemetry}, sort_keys=True))
    except VerificationPaused:
        context = {'proposal': proposal, 'apply_result': apply_result, 'packet_result': packet_result,
                   'telemetry': telemetry, 'gates': gates, 'raw_path': str(raw_path.relative_to(OPS)),
                   'repair_raw_path': str(repair_raw_path.relative_to(OPS))}
        pending = save_proposal(CANDIDATES, clone, ticket_path, identity, context)
        print(json.dumps({'status': 'verification_pending', 'ticket_id': ticket_id, 'worker': args.worker,
                          'proposal': str(pending.relative_to(OPS)),
                          'reason': 'Patch saved without acceptance; awaiting focused verification.'}))
    except Exception as exc:
        raw_path.write_text("runner infrastructure failure: %s\n" % exc)
        print(json.dumps({"status": "infrastructure_failed", "ticket_id": ticket_id,
                          "reason": str(exc), "raw": str(raw_path.relative_to(OPS))}, sort_keys=True))
    finally:
        # The patch is the durable candidate. Clones are always disposable and
        # otherwise accumulate multiple gigabytes under /tmp over time.
        if candidate_patch is not None or outcome != "accepted_for_dependent_observation":
            shutil.rmtree(clone, ignore_errors=True)


if __name__ == "__main__":
    main()
