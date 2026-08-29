#!/usr/bin/env python3
"""Execute and record the isolated Factory NG golden Map patch gates."""
import datetime
import hashlib
import json
import lzma
import pathlib
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path("/tmp/factory-ng-golden-map-target-player-draw")
BASE = pathlib.Path("/opt/development/test/openmagic")
OPS = pathlib.Path("/opt/development/magic-ops")
MAGIC = pathlib.Path("/opt/development/magic-new")
CONTRACT = OPS / "docs/sessions/ticketspec-v1-contract-correction"
SNAP = pathlib.Path("/opt/development/magic-ops-artifacts/oracle-face-snapshot/run1/8cdd0282d959a4039ceaa5e462c9214b3e95f15de9b9880373bda04f5fbef629.jsonl.xz")
IDS = {
    "59b869b9-cb48-4152-ad91-52f582e2df5b": "Comparative Analysis",
    "8f32ceb2-92c2-4dde-bf73-40bb79c3fcef": "Inspiration",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    data = value if isinstance(value, bytes) else canonical(value)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def run_gate(gate_id, argv, cwd):
    started = datetime.datetime.now(datetime.timezone.utc)
    mono = time.monotonic()
    proc = subprocess.run(argv, cwd=cwd, capture_output=True)
    ended = datetime.datetime.now(datetime.timezone.utc)
    stdout_path = ROOT / "gate-receipts" / f"{gate_id}.stdout"
    stderr_path = ROOT / "gate-receipts" / f"{gate_id}.stderr"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_bytes(proc.stdout[-65536:])
    stderr_path.write_bytes(proc.stderr[-65536:])
    receipt = {
        "schema": "factory.patch-gate-receipt/v1",
        "gate_id": gate_id,
        "argv": argv,
        "cwd": str(cwd),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "wall_time_ms": int((time.monotonic() - mono) * 1000),
        "exit_code": proc.returncode,
        "stdout": {"path": str(stdout_path.relative_to(ROOT)), "sha256": digest(stdout_path.read_bytes()), "bytes": stdout_path.stat().st_size},
        "stderr": {"path": str(stderr_path.relative_to(ROOT)), "sha256": digest(stderr_path.read_bytes()), "bytes": stderr_path.stat().st_size},
        "result": "passed" if proc.returncode == 0 else "failed",
    }
    write_json(ROOT / "gate-receipts" / f"{gate_id}.json", receipt)
    return receipt


def load_faces():
    found = {}
    with lzma.open(SNAP, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            oid = row["oracleFaceKey"]["scryfallOracleId"]
            if oid in IDS:
                found[oid] = row
    if set(found) != set(IDS):
        raise RuntimeError("E_SOURCE_MEMBER_MISSING")
    return found


def remeasure():
    sys.path.insert(0, str(WORK / "scripts/paragraph"))
    import reparse

    before_scope = json.loads((CONTRACT / "outputs/scope.json").read_text())
    before = {x["oracle_face_key"]["scryfallOracleId"]: x for x in before_scope["root_cause_scope"]}
    results = []
    partitions = {
        "confirmed_fixed_by_change": [],
        "already_fixed_independently": [],
        "still_failing_same_root_cause": [],
        "reclassified_different_root_cause": [],
        "invalid_or_unsupported": [],
    }
    for oid, row in sorted(load_faces().items()):
        revision = row["canonicalSemanticRevision"]
        card = {
            "name": IDS[oid],
            "text": revision["text"],
            "types": revision["types"],
            "type": revision["types"][0],
            "keywords": revision.get("keywords") or [],
        }
        outcome = reparse.reparse_card(card)
        after_gaps = sorted({x[0] for x in outcome.get("misses", [])})
        selected_fixed = "verb_unmapped:p_draw" not in after_gaps
        record = {
            "oracle_face_id": before[oid]["oracle_face_id"],
            "oracle_face_key": before[oid]["oracle_face_key"],
            "semantic_source_hash": before[oid]["semantic_source_hash"],
            "assertion_locator": before[oid]["assertion_locator"],
            "before_gap_set": before[oid]["complete_gap_set"],
            "after_gap_set": after_gaps,
            "eligible_after": outcome["eligible"],
            "selected_root_cause_fixed": selected_fixed,
            "ability_count_after": len(outcome["abilities"]),
        }
        results.append(record)
        member = before[oid]
        if not selected_fixed:
            partitions["still_failing_same_root_cause"].append(member)
        elif after_gaps:
            partitions["reclassified_different_root_cause"].append(member)
        else:
            partitions["confirmed_fixed_by_change"].append(member)
    measured_ids = [x["oracle_face_id"] for values in partitions.values() for x in values]
    expected_ids = [x["oracle_face_id"] for x in before_scope["root_cause_scope"]]
    if sorted(measured_ids) != sorted(expected_ids) or len(measured_ids) != len(set(measured_ids)):
        raise RuntimeError("E_RESULT_PARTITION_CONSERVATION")
    artifact = {
        "schema": "factory.golden-map-remeasurement/v1",
        "ticket_id": json.loads((CONTRACT / "outputs/ticket.json").read_text())["ticket_id"],
        "immutable_scope_hash": digest(before_scope),
        "results": results,
        "partitions": partitions,
        "summary": {
            "root_cause_members": 2,
            "selected_root_cause_fixed": sum(x["selected_root_cause_fixed"] for x in results),
            "whole_face_unlocks": sum(x["eligible_after"] for x in results),
            "residual_different_root_cause": sum(bool(x["after_gap_set"]) and x["selected_root_cause_fixed"] for x in results),
        },
    }
    write_json(ROOT / "remeasurement.json", artifact)
    return artifact


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    ticket = json.loads((CONTRACT / "outputs/ticket.json").read_text())
    skill = ticket["skill_receipt"]
    baseline_probe = (
        "import pathlib,sys;"
        f"sys.path.insert(0,{str(BASE / 'scripts/paragraph')!r});"
        "import reparse;v,a=reparse.O.parse_atom('Target player draws two cards.');"
        "assert v=='p_draw' and reparse.map_atom(v,a,kind='oneshot') is None"
    )
    gates = [
        run_gate("discriminating-baseline", ["python3", "-c", baseline_probe], BASE),
        run_gate("positive-adjacent-negative", ["python3", "-m", "unittest", "scripts.paragraph.test_ticketspec_target_player_draw"], WORK),
        run_gate("engine-target-player-draw", ["go", "test", "-overlay=" + str(CONTRACT / "tests/engine-overlay.json"), "./game", "-run", "^TestTicketSpecTargetPlayerDrawTwo$", "-count=1"], MAGIC / "backend"),
        run_gate("honesty-engine-unchanged", ["git", "diff", "--exit-code", "--", "backend/game", "backend/cardfns", "backend/cards"], MAGIC),
        run_gate("parser-regression", ["python3", "-m", "unittest", "discover", "-s", "scripts/paragraph", "-p", "test_*.py"], WORK),
        run_gate("diff-check", ["git", "diff", "--check"], WORK),
    ]
    measurement = remeasure()
    write_json(ROOT / "gate-receipts/index.json", {"schema": "factory.patch-gate-receipt-set/v1", "receipts": gates, "all_passed": all(x["result"] == "passed" for x in gates)})
    decision = {
        "schema": "factory.semantic-decision/v1",
        "stage": 4,
        "verdict": "IMPLEMENT",
        "reason": "The parser already recognizes p_draw and the Engine/converter path proves a chosen player target. The smallest honest Map change is to emit the existing generic player TargetSpec only for target player.",
        "refusals_checked": ["existing_map_rule", "missing_engine_capability", "mixed_root_cause", "prohibited_engine_change", "literal_card_special_case"],
    }
    write_json(ROOT / "stage-4-decision.json", decision)
    telemetry = {
        "schema": "factory.attempt-telemetry/v1",
        "attempt_id": "golden-map-target-player-draw-1",
        "route": "capable_online_codex_interactive",
        "model_identifier": {"status": "unavailable", "reason": "The interactive environment does not expose an authoritative API model identifier."},
        "token_usage": {
            "input_tokens": {"status": "unavailable"},
            "output_tokens": {"status": "unavailable"},
            "cache_read_tokens": {"status": "unavailable"},
            "cache_write_tokens": {"status": "unavailable"},
            "effective_total": {"status": "unavailable"},
            "durable_goal_checkpoint_before_attempt": {"tokens_used": 133751, "status": "blocked_snapshot", "authoritative_for_attempt_delta": False},
        },
        "budget": ticket["work_profile"]["budget"],
        "warning_triggered": False,
        "warning_basis": "No authoritative attempt token total is exposed; no threshold claim is inferred.",
    }
    write_json(ROOT / "telemetry.json", telemetry)
    summary = {
        "schema": "factory.golden-map-attempt/v1",
        "attempt_id": "golden-map-target-player-draw-1",
        "ticket_id": ticket["ticket_id"],
        "ticket_identity_digest": ticket["identity_digest"],
        "skill_receipt": skill,
        "repository": str(WORK),
        "base_commit": git(WORK, "rev-parse", "HEAD"),
        "branch": git(WORK, "branch", "--show-current"),
        "changed_paths": ["scripts/paragraph/reparse.py", "scripts/paragraph/test_ticketspec_target_player_draw.py"],
        "prohibited_paths_changed": False,
        "stage_4_verdict": decision["verdict"],
        "stage_5_patch_status": "proposed",
        "stage_6_gates_passed": all(x["result"] == "passed" for x in gates),
        "scope_remeasurement": measurement["summary"],
        "deployment_performed": False,
        "live_ticket_mutated": False,
    }
    write_json(ROOT / "attempt.json", summary)
    if not summary["stage_6_gates_passed"]:
        raise SystemExit("E_PATCH_GATE_FAILED")
    print("OK golden Map attempt gates and immutable-scope remeasurement")


if __name__ == "__main__":
    main()
