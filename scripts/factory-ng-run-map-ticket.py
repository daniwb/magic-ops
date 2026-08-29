#!/usr/bin/env python3
"""Run one evidence-complete Map TicketSpec in a disposable clone.

This is the small bridge between Factory NG's deterministic producers and the
already-proven prepared-Qwen path.  The model only proposes edit blocks; this
harness applies them in a clone, owns every gate, and records the outcome.
Nothing is merged, pushed, deployed, or written to the source checkout.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
SOURCE = Path("/opt/development/test/openmagic")
RUNS = OPS / "docs/factory-ng/runs"
CANDIDATES = OPS / "docs/factory-ng/candidates"


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
        return {"exit_code": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "",
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


def run_ticket_gate(command, clone):
    """Run a TicketSpec gate, including the compact remeasurement shorthand."""
    suffix = " reports zero remaining pinned members"
    executable = command[:-len(suffix)] if command.endswith(suffix) else command
    result = run(["bash", "-lc", executable], clone, timeout=720)
    if "factory-ng-targeted-demand.py" in executable and "--members-from" in executable and result["exit_code"] == 0:
        try:
            if json.loads(result["stdout"]).get("member_count") != 0:
                result["exit_code"] = 1
                result["stderr"] += "\npinned remeasurement is not zero"
        except json.JSONDecodeError:
            result["exit_code"] = 1
            result["stderr"] += "\npinned remeasurement did not return JSON"
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", required=True, type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--worker", default="qwen-local")
    args = ap.parse_args()
    ticket_path = args.ticket.resolve()
    ticket = json.loads(ticket_path.read_text())
    if ticket.get("schema") != "factory.ticket-spec/v1" or ticket.get("work_type") != "map":
        ap.error("only a Map factory.ticket-spec/v1 can use this runner")
    if ticket.get("execution", {}).get("selected_profile") != "qwen-prepared-direct@1.0.2":
        ap.error("ticket is not routed to the prepared-Qwen Map runner")
    if subprocess.check_output(["git", "-C", str(SOURCE), "status", "--porcelain"], text=True):
        ap.error("canonical source checkout must be clean")

    ticket_id = ticket["id"]
    slug = ticket_id.removeprefix("ticket:").replace("/", "-").replace(".", "-")
    stamp = time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
    clone = Path(tempfile.mkdtemp(prefix="factory-ng-" + slug + "-", dir="/tmp"))
    receipt_path = RUNS / (stamp + "-" + slug + "-qwen.json")
    raw_path = RUNS / (stamp + "-" + slug + "-qwen.raw.txt")
    RUNS.mkdir(parents=True, exist_ok=True)
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    candidate_patch = None
    outcome = "infrastructure_failed"
    try:
        clone_result = run(["git", "clone", "--quiet", "--no-hardlinks", str(SOURCE), str(clone)], OPS, timeout=180)
        if clone_result["exit_code"] != 0:
            raise RuntimeError("clone failed: " + output(clone_result))
        packet_result = run([sys.executable, str(OPS / "scripts/map-ticket-spec-pack.py"),
                             "--ticket-spec", str(ticket_path), "--repo", str(clone)], OPS, timeout=180)
        if packet_result["exit_code"] != 0:
            raise RuntimeError("packet failed: " + output(packet_result))
        proposal = run([sys.executable, str(OPS / "scripts/qwen-prepared-call.py"),
                        "--model", args.model, "--max-tokens", "800"], clone, stdin=packet_result["stdout"], timeout=960)
        raw_path.write_text(proposal["stdout"])
        telemetry = qwen_telemetry(proposal["stderr"], proposal["elapsed_ms"])
        apply_result = run([sys.executable, str(OPS / "scripts/map-pipeline-apply.py")], clone,
                           stdin=proposal["stdout"], timeout=60)
        gates = [gate("patch-apply", "scripts/map-pipeline-apply.py", apply_result)]
        outcome = "gate_failed"
        changed = []
        if proposal["exit_code"] != 0:
            outcome = "infrastructure_failed"
        elif apply_result["exit_code"] == 4:
            outcome = "parked"
        elif apply_result["exit_code"] == 0:
            # TicketSpec gates are the acceptance contract.  The first rollout
            # accidentally retained the previous ticket's test/measurement
            # names here, which made every later valid Map proposal fail a
            # foreign test.  Run each current ticket gate in the clone instead.
            for index, command in enumerate(ticket.get("gates", [])):
                commanded = run_ticket_gate(command, clone)
                gates.append(gate("ticket-gate-%d" % index, command, commanded))
            diffcheck = run(["git", "diff", "--check"], clone, timeout=60)
            gates.append(gate("diff-check", "git diff --check", diffcheck))
            names = run(["git", "status", "--porcelain"], clone, timeout=60)
            changed = [line[3:] for line in names["stdout"].splitlines() if len(line) > 3]
            allowed = set(ticket["scope"]["allowed_paths"])
            scope_result = {"exit_code": 0 if changed and set(changed).issubset(allowed) else 1,
                            "stdout": "changed=" + ",".join(changed), "stderr": ""}
            gates.append(gate("scope", "ticket allowed_paths only", scope_result))
            if all(item["outcome"] == "passed" for item in gates):
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
            "raw_artifacts": [{"path": str(raw_path.relative_to(OPS)), "sha256": sha_file(raw_path)}],
            "gates": gates, "outcome": outcome,
            "integration": "eligible_full_gate" if outcome == "accepted_for_dependent_observation" else "observation_only",
            "next_action": "Explicitly decide whether to integrate an accepted clone patch; Factory NG never integrates automatically."
        }
        if candidate_patch:
            receipt["execution"]["candidate_patch"] = str(candidate_patch.relative_to(OPS))
            receipt["execution"]["candidate_patch_sha256"] = sha_file(candidate_patch)
            receipt["next_action"] = "Factory NG may integrate this durable patch under its configured full-gate policy."
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": outcome, "ticket_id": ticket_id, "worker": args.worker,
                          "receipt": str(receipt_path.relative_to(OPS)), "telemetry": telemetry}, sort_keys=True))
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
