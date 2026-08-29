#!/usr/bin/env python3
"""Render the single, receipt-derived Factory NG operator view.

This intentionally has no database, service, scheduler, or inferred state.
It reads TicketSpec JSON and observation receipts only, so every displayed
number links back to a durable artifact under docs/factory-ng/.
"""
import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTORY = ROOT / "docs" / "factory-ng"
TICKETS = FACTORY / "tickets"
RUNS = FACTORY / "runs"
JOBS = ROOT / "state/factory-ng-jobs.json"


def load_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def ticket_specs():
    rows = {}
    for path in sorted(TICKETS.glob("*.json")):
        value = load_json(path)
        if value and value.get("schema") == "factory.ticket-spec/v1":
            rows[value["id"]] = {
                "id": value["id"], "path": str(path.relative_to(ROOT)),
                "parents": value.get("parents", []), "work_type": value.get("work_type"),
                "lifecycle": value.get("lifecycle"), "sha256": digest(path),
            }
    return rows


def jobs():
    value = load_json(JOBS) or {}
    rows = value.get("jobs", {}) if isinstance(value, dict) else {}
    if not isinstance(rows, dict):
        return []
    return sorted((item for item in rows.values() if isinstance(item, dict)),
                  key=lambda item: (item.get("created_at", ""), item.get("ticket_id", "")))


def receipts():
    rows = []
    for path in sorted(RUNS.glob("*.json")):
        value = load_json(path)
        if not value or value.get("schema") != "factory.observation-receipt/v1":
            continue
        ticket = value.get("ticket", {})
        model = value.get("model", {})
        telemetry = model.get("telemetry") or model.get("aggregate_telemetry") or {}
        ticket_path = ROOT / ticket.get("path", "")
        binding = "missing"
        if ticket_path.is_file():
            binding = "valid" if digest(ticket_path) == ticket.get("sha256") else "mismatch"
        rows.append({
            "receipt_path": str(path.relative_to(ROOT)), "ticket_id": ticket.get("id"),
            "ticket_binding": binding, "outcome": value.get("outcome", "unknown"),
            "profile": model.get("profile", "unknown"),
            "resolved_model": model.get("resolved_model", "unknown"),
            "telemetry": telemetry, "integration": value.get("integration", "unknown"),
            "gates": value.get("gates", []), "next_action": value.get("next_action", ""),
            "candidate_commit": value.get("execution", {}).get("candidate_commit", ""),
        })
    return rows


def integrations():
    rows = []
    superseded = set()
    for path in sorted(RUNS.glob("*.json")):
        value = load_json(path)
        if not value or value.get("schema") != "factory.integration-receipt/v1":
            continue
        old = value.get("supersedes")
        if isinstance(old, str):
            superseded.add(old)
        elif isinstance(old, list):
            superseded.update(item for item in old if isinstance(item, str))
        source = value.get("source", {})
        rows.append({
            "receipt_path": str(path.relative_to(ROOT)),
            "parents": value.get("parents", []),
            "outcome": value.get("outcome", "unknown"),
            "result_commit": source.get("result_commit", "—"),
            "pushed": source.get("pushed", False),
            "deployed": source.get("deployed", False),
        })
    # A follow-up integration receipt records a newly completed gate without
    # rewriting its immutable predecessor. Show only the current record in the
    # operator view; the older artifact remains on disk and linked by path.
    return [row for row in rows if row["receipt_path"] not in superseded]


def number(value):
    return str(value) if isinstance(value, (int, float)) else "—"


def markdown(specs, attempts, integrated, job_rows):
    accepted = sum(item["outcome"].startswith("accepted") for item in attempts)
    failed = sum(item["outcome"].startswith("gate_failed") for item in attempts)
    infra = sum(item["outcome"].startswith("infrastructure_failed") for item in attempts)
    warnings = sum(item["outcome"].startswith("warning_") for item in attempts)
    lines = [
        "# Factory NG dashboard", "",
        "Derived directly from immutable TicketSpecs and observation receipts.", "",
        f"Tickets: {len(specs)} · observation receipts: {len(attempts)} · integration receipts: {len(integrated)} · accepted: {accepted} · gate-failed: {failed} · infrastructure-failed: {infra} · warning-stopped: {warnings}",
        "", "## Ticket DAG", "",
        "| Ticket | Type | Ticket lifecycle | Factory state | Parents | Receipt binding |", "|---|---|---|---|---|---|",
    ]
    by_ticket = {item["ticket_id"]: item for item in attempts}
    jobs_by_ticket = {item.get("ticket_id"): item for item in job_rows}
    for ticket_id, spec in sorted(specs.items()):
        receipt = by_ticket.get(ticket_id)
        job = jobs_by_ticket.get(ticket_id, {})
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            ticket_id, spec["work_type"], spec["lifecycle"],
            job.get("state", "not queued"),
            ", ".join(spec["parents"]) or "—",
            receipt["ticket_binding"] if receipt else "no receipt"))
    lines += ["", "## Attempts and telemetry", "",
              "| Ticket | Outcome | Profile / model | Input | Output | Cache read | Cache write | Reasoning | Cost USD |", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for item in attempts:
        telem = item["telemetry"]
        lines.append("| %s | %s | %s / %s | %s | %s | %s | %s | %s | %s |" % (
            item["ticket_id"], item["outcome"], item["profile"], item["resolved_model"],
            number(telem.get("input_tokens")), number(telem.get("output_tokens")),
            number(telem.get("cache_read_tokens")), number(telem.get("cache_write_tokens")),
            number(telem.get("reasoning_tokens")), number(telem.get("provider_cost_usd"))))
    if integrated:
        lines += ["", "## Integrations", "",
                  "| Parents | Outcome | Commit | Pushed | Deployed |",
                  "|---|---|---|---|---|"]
        for item in integrated:
            lines.append("| %s | %s | %s | %s | %s |" % (
                ", ".join(item["parents"]) or "—", item["outcome"],
                item["result_commit"], item["pushed"], item["deployed"]))
    lines += ["", "Ticket gates accept a candidate. Only the integrations table proves the separate full production gate, push, and deployment states."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    specs, attempts, integrated, job_rows = ticket_specs(), receipts(), integrations(), jobs()
    if args.format == "json":
        print(json.dumps({"tickets": list(specs.values()), "attempts": attempts,
                          "integrations": integrated, "jobs": job_rows}, indent=2, sort_keys=True))
    else:
        print(markdown(specs, attempts, integrated, job_rows), end="")


if __name__ == "__main__":
    main()
