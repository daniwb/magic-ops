#!/usr/bin/env python3
"""Rebuildable SQLite read index; immutable Factory artifacts remain authoritative.

Only the background refresh reads source JSON. HTTP queries use a consistent
SQLite snapshot and bounded pages. Raw provider token fields are copied without
quota weighting; no effective-token or completed-card totals are inferred.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "state/factory-ng-dashboard.sqlite3"
SCHEMAS = {"factory.ticket-spec/v1": "ticket",
           "factory.observation-receipt/v1": "attempt",
           "factory.integration-receipt/v1": "integration"}
JOB_FIELDS = "ticket_id ticket_path work_type state outcome worker started_at created_at updated_at receipt integration_receipt superseded_by waiting_reason repair_blocker reason attempts integration_attempts dependency_blocker log_path finished_at verification_resume verification_batch verification_host integration_wave_size pid result_path".split()


# Bump when projection fields change so unchanged receipts are reprojected once.
PROJECTION_VERSION = "failure-diagnostics-v3"


def failure_summary(value):
    failed = [g for g in value.get("gates", []) if g.get("outcome") == "failed"
              and g.get("id") != "initial-patch-apply"]
    if not failed:
        return {"reason": str(value.get("reason", ""))[:900]}
    # A missing patch is a downstream symptom when the provider call failed.
    gate = next((g for g in failed if g.get('id', '').startswith('provider-')), failed[0])
    detail = str(gate.get("detail") or gate.get("evidence") or "")
    lines = detail.splitlines()
    relevant = [line.strip() for line in lines if any(word in line for word in
                ("UNREGISTERED", "Error:", "error:", "AssertionError", "CONFLICT", "--- FAIL:", "FAIL:"))]
    return {"gate": gate.get("id", ""), "reason": str(value.get("reason", ""))[:900],
            "detail": ("\n".join(relevant) if relevant else detail.strip())[:900]}


def job_projection(job, db):
    row = {k: job[k] for k in JOB_FIELDS if k in job}
    path = job.get("integration_receipt") if job.get("state") == "integration_failed" else job.get("receipt")
    if path:
        found = db.execute("SELECT payload FROM artifacts WHERE path=?", (path,)).fetchone()
        if found:
            receipt = json.loads(found[0])
            # A previous attempt's receipt may survive a later preflight exit.
            if job.get("state") == "integration_failed" or receipt.get("created_at", "") >= job.get("started_at", ""):
                row["failure_receipt"] = path
                row["failure"] = receipt.get("excluded_failures", {}).get(job["ticket_id"], receipt.get("failure", {}))
    return row


def timestamp(path, value):
    if value.get("created_at"):
        return value["created_at"]
    match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{6}Z)-", path.name)
    if match:
        return datetime.datetime.strptime(match[1], "%Y-%m-%dT%H%M%SZ").isoformat() + "Z"
    return datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS artifacts (
          path TEXT PRIMARY KEY, mtime INTEGER, size INTEGER, kind TEXT,
          ticket_id TEXT, created_at TEXT, outcome TEXT, payload TEXT);
        CREATE INDEX IF NOT EXISTS artifact_page ON artifacts(kind, created_at DESC, path DESC);
        CREATE INDEX IF NOT EXISTS artifact_ticket ON artifacts(kind, ticket_id);
        CREATE TABLE IF NOT EXISTS edges (parent TEXT, child TEXT, PRIMARY KEY(parent, child));
        CREATE INDEX IF NOT EXISTS edge_child ON edges(child);
        CREATE TABLE IF NOT EXISTS supersedes (receipt TEXT, previous TEXT, PRIMARY KEY(receipt, previous));
        CREATE INDEX IF NOT EXISTS superseded_path ON supersedes(previous);
        CREATE TABLE IF NOT EXISTS jobs (ticket_id TEXT PRIMARY KEY, state TEXT,
          updated_at TEXT, attention INTEGER, problem INTEGER, payload TEXT);
        CREATE INDEX IF NOT EXISTS job_page ON jobs(updated_at DESC, ticket_id);
        CREATE INDEX IF NOT EXISTS job_state ON jobs(state, updated_at DESC);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    return db


def project(path, value, root):
    kind = SCHEMAS.get(value.get("schema"), "ignored")
    rel = str(path.relative_to(root))
    if kind == "ticket":
        row = {k: value.get(k) for k in ("id", "work_type", "lifecycle")}
        row.update(path=rel, parents=value.get("parents", []),
                   sha256="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
    elif kind == "attempt":
        model = value.get("model", {})
        row = dict(receipt_path=rel, ticket_id=value.get("ticket", {}).get("id"),
                   ticket_sha256=value.get("ticket", {}).get("sha256"),
                   created_at=timestamp(path, value), outcome=value.get("outcome", "unknown"),
                   profile=model.get("profile", "unknown"),
                   resolved_model=model.get("resolved_model", "unknown"),
                   telemetry=model.get("telemetry") or model.get("aggregate_telemetry") or {},
                   integration=value.get("integration", "unknown"),
                   candidate_commit=value.get("execution", {}).get("candidate_commit", ""))
    elif kind == "integration":
        source = value.get("source", {})
        row = dict(receipt_path=rel, created_at=timestamp(path, value),
                   parents=value.get("parents", []), outcome=value.get("outcome", "unknown"),
                   result_commit=source.get("result_commit", "—"),
                   pushed=source.get("pushed", False), deployed=source.get("deployed", False))
    else:
        row = {}
    if kind in ("attempt", "integration"):
        row["failure"] = failure_summary(value)
        if kind == "integration":
            row["excluded_failures"] = {key: failure_summary(item)
                                       for key, item in value.get("excluded_candidates", {}).items()}
    return kind, row


def refresh(root=ROOT, path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"busy": True}
        db = connect(path)
        try:
            version = db.execute("SELECT value FROM meta WHERE key='projection_version'").fetchone()
            rebuild = not version or version[0] != PROJECTION_VERSION
            known = {p: (m, s) for p, m, s in db.execute("SELECT path,mtime,size FROM artifacts")}
            seen, changed, invalid = set(), 0, []
            # One atomic publish: readers keep the previous snapshot during refresh.
            with db:
                for folder in ("tickets", "runs"):
                    directory = root / "docs/factory-ng" / folder
                    if not directory.is_dir():
                        raise FileNotFoundError(directory)
                    for artifact in directory.glob("*.json"):
                        # Provider transport logs use this suffix but may be
                        # JSONL or plain text; they are never Factory receipts.
                        if artifact.name.endswith(".raw.json"):
                            continue
                        rel, stat = str(artifact.relative_to(root)), artifact.stat()
                        seen.add(rel)
                        if not rebuild and known.get(rel) == (stat.st_mtime_ns, stat.st_size):
                            continue
                        try:
                            value = json.loads(artifact.read_text())
                            if not isinstance(value, dict):
                                raise ValueError("artifact is not an object")
                        except (OSError, ValueError):
                            # Some historical *.json files are actually JSONL or
                            # empty output. Match the legacy renderer's exclusion,
                            # but make incomplete refreshes visible to operators.
                            invalid.append(rel)
                            continue
                        kind, row = project(artifact, value, root)
                        ticket = row.get("id", row.get("ticket_id"))
                        if kind == "ticket":
                            db.execute("DELETE FROM edges WHERE child=?", (ticket,))
                            db.executemany("INSERT OR IGNORE INTO edges VALUES (?,?)",
                                           [(p, ticket) for p in row["parents"]])
                        db.execute("DELETE FROM supersedes WHERE receipt=?", (rel,))
                        if kind == "integration":
                            old = value.get("supersedes", [])
                            old = [old] if isinstance(old, str) else old
                            db.executemany("INSERT OR IGNORE INTO supersedes VALUES (?,?)",
                                           [(rel, p) for p in old if isinstance(p, str)])
                        db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?,?)",
                                   (rel, stat.st_mtime_ns, stat.st_size, kind, ticket,
                                    row.get("created_at", ""), row.get("outcome", ""), json.dumps(row)))
                        changed += 1
                for rel in known.keys() - seen:
                    db.execute("DELETE FROM edges WHERE child IN (SELECT ticket_id FROM artifacts WHERE path=? AND kind='ticket')", (rel,))
                    db.execute("DELETE FROM supersedes WHERE receipt=?", (rel,))
                    db.execute("DELETE FROM artifacts WHERE path=?", (rel,))
                job_path = root / "state/factory-ng-jobs.json"
                stat = job_path.stat()
                stamp = f"test-queue-v3:{stat.st_mtime_ns}:{stat.st_size}"
                old = db.execute("SELECT value FROM meta WHERE key='jobs_stamp'").fetchone()
                if rebuild or changed or (known.keys() - seen) or not old or old[0] != stamp:
                    jobs = json.loads(job_path.read_text()).get("jobs", {})
                    db.execute("DELETE FROM jobs")
                    for job in jobs.values():
                        outcome, state = job.get("outcome", ""), job.get("state", "")
                        unresolved = state in ("failed", "integration_failed") and not job.get("superseded_by")
                        system = outcome != "infrastructure_failed_authentication" and (
                            outcome.startswith("infrastructure_failed") or outcome in
                            ("producer_error", "full_gate_failed", "push_failed_after_full_gate"))
                        problem = unresolved and (system or state == "integration_failed")
                        attention = unresolved and (system or state == "integration_failed" or outcome == "candidate_conflict")
                        db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?)", (
                            job["ticket_id"], state, job.get("updated_at", ""), attention, problem,
                            json.dumps(job_projection(job, db))))
                    db.execute("INSERT OR REPLACE INTO meta VALUES ('jobs_stamp',?)", (stamp,))
                db.execute("INSERT OR REPLACE INTO meta VALUES ('projection_version',?)", (PROJECTION_VERSION,))
                now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
                db.execute("INSERT OR REPLACE INTO meta VALUES ('indexed_at',?)", (now,))
                db.execute("INSERT OR REPLACE INTO meta VALUES ('invalid_files',?)", (json.dumps(invalid),))
            return {"changed": changed, "artifacts": len(seen), "indexed_at": now, "invalid_files": invalid}
        finally:
            db.close()


def query(path=DB, work_filter="active", jobs_offset=0, attempts_offset=0,
          integrations_offset=0, attempts=False, focus="", search="", limit=30):
    limit = max(1, min(int(limit), 100))
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    try:
        db.execute("BEGIN")
        def count(table, where, args=()):
            return db.execute(f"SELECT count(*) FROM {table} WHERE {where}", args).fetchone()[0]
        def rows(sql, args=()):
            return [json.loads(r[0]) for r in db.execute(sql, args)]
        def page(table, where, order, offset, args=()):
            total = count(table, where, args)
            offset = min(max(0, int(offset)), max(0, ((total - 1) // limit) * limit))
            return rows(f"SELECT payload FROM {table} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", (*args, limit, offset)), dict(total=total, offset=offset, limit=limit)
        where = {"active": "state IN ('working','queued','awaiting_verification','awaiting_integration','integrating')",
                 "attention": "attention=1", "recent": "1"}[work_filter]
        jobs, jobs_page = page("jobs", where, "updated_at DESC,ticket_id", jobs_offset)
        current_integrations = "kind='integration' AND NOT EXISTS (SELECT 1 FROM supersedes s WHERE s.previous=artifacts.path)"
        integrated, integration_page = page("artifacts", current_integrations, "created_at DESC,path DESC", integrations_offset)
        attempt_rows, attempt_page = (page("artifacts", "kind='attempt'", "created_at DESC,path DESC", attempts_offset)
                                      if attempts else ([], dict(total=count("artifacts", "kind='attempt'"), offset=0, limit=limit)))
        active = rows("SELECT payload FROM jobs WHERE state IN ('working','integrating','awaiting_verification','awaiting_integration') ORDER BY ticket_id")
        if not focus:
            focus = next((j["ticket_id"] for j in active + jobs), "")
        choices = rows("SELECT payload FROM artifacts WHERE kind='ticket' AND instr(lower(ticket_id),lower(?))>0 ORDER BY ticket_id LIMIT 50", (search,)) if search else []
        ids = {j["ticket_id"] for j in jobs + active} | {focus} | {t["id"] for t in choices}
        ids.update(r[0] for r in db.execute("SELECT parent FROM edges WHERE child=? UNION SELECT child FROM edges WHERE parent=? LIMIT 100", (focus, focus)))
        placeholders = ",".join("?" for _ in ids)
        tickets = rows(f"SELECT payload FROM artifacts WHERE kind='ticket' AND ticket_id IN ({placeholders}) ORDER BY ticket_id", tuple(ids))
        graph_jobs = rows(f"SELECT payload FROM jobs WHERE ticket_id IN ({placeholders})", tuple(ids))
        summary = dict(tickets=count("artifacts", "kind='ticket'"), attempts=attempt_page["total"],
                       accepted=count("artifacts", "kind='attempt' AND outcome LIKE 'accepted%'"),
                       integrations=integration_page["total"], problems=count("jobs", "problem=1"),
                       worker_failures=count("jobs", "problem=1 AND state='failed'"),
                       integration_failures=count("jobs", "problem=1 AND state='integration_failed'"))
        indexed_at = db.execute("SELECT value FROM meta WHERE key='indexed_at'").fetchone()[0]
        invalid = json.loads(db.execute("SELECT value FROM meta WHERE key='invalid_files'").fetchone()[0])
        return dict(tickets=tickets, jobs=jobs, active_jobs=active, graph_jobs=graph_jobs,
                    focus=focus, attempts=attempt_rows, integrations=integrated,
                    summary=summary, indexed_at=indexed_at, invalid_files=invalid,
                    pages=dict(jobs=jobs_page, attempts=attempt_page, integrations=integration_page))
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--filter", choices=("active", "attention", "recent"), default="active")
    for field in ("jobs", "attempts", "integrations"):
        parser.add_argument(f"--{field}-offset", type=int, default=0)
    parser.add_argument("--attempts", action="store_true")
    parser.add_argument("--focus", default="")
    parser.add_argument("--search", default="")
    args = parser.parse_args()
    result = refresh(args.root, args.db) if args.refresh else query(
        args.db, args.filter, args.jobs_offset, args.attempts_offset,
        args.integrations_offset, args.attempts, args.focus, args.search)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
