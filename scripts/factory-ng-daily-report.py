#!/usr/bin/env python3
"""Email a daily Factory NG report derived from the live dashboard APIs."""
import argparse
import collections
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage


DEFAULT_BASE = "http://127.0.0.1:9999"
SYSTEM_FAILURES = {
    "producer_error", "full_gate_failed", "push_failed_after_full_gate",
}


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_system_problem(outcome):
    outcome = outcome or ""
    return outcome.startswith("infrastructure_failed") or outcome in SYSTEM_FAILURES


def fetch_snapshot(base_url, timeout=20):
    snapshot, errors = {}, []
    for name, path in (("cards", "/factory-ng/cards"),
                       ("status", "/factory-ng/status"),
                       ("data", "/factory-ng/data"),
                       ("limits", "/factory-ng/limits")):
        try:
            request = urllib.request.Request(base_url.rstrip("/") + path,
                                             headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                snapshot[name] = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            snapshot[name] = {}
            errors.append("%s: %s" % (name, exc))
    snapshot["errors"] = errors
    return snapshot


def recent(rows, cutoff):
    return [row for row in rows if (parse_time(row.get("created_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)) >= cutoff]


def value_or_dash(value):
    return "—" if value is None else str(value)


def signed(value):
    if value is None:
        return "unmeasured"
    return "%+d" % int(value)


def limit_line(name, value):
    if not value:
        return "  %-7s no readable usage sample" % name
    status = value.get("status", "unknown")
    if name == "Claude":
        return ("  Claude  %-9s 5h %s%% used · 7d %s%% used · %s%% currently unlocked · %s%% usable now"
                % (status, value_or_dash(value.get("short_used_pct")),
                   value_or_dash(value.get("weekly_used_pct")),
                   value_or_dash(value.get("weekly_unlocked_pct")),
                   value_or_dash(value.get("weekly_headroom_pct"))))
    return ("  Codex   %-9s 7d %s%% used · %s%% remaining · %s%% currently unlocked · %s%% guard headroom"
            % (status, value_or_dash(value.get("used_pct")),
               value_or_dash(value.get("remaining_pct")),
               value_or_dash(value.get("weekly_unlocked_pct")),
               value_or_dash(value.get("headroom_pct"))))


def summarize(snapshot, now=None):
    now = now or utc_now()
    cutoff = now - dt.timedelta(hours=24)
    hour_cutoff = now - dt.timedelta(hours=1)
    cards = snapshot.get("cards") or {}
    current = cards.get("current") or {}
    change = cards.get("change_24h") or {}
    status = snapshot.get("status") or {}
    data = snapshot.get("data") or {}
    limits = snapshot.get("limits") or {}
    jobs = data.get("jobs") or []
    attempts = data.get("attempts") or []
    integrations = data.get("integrations") or []
    active = status.get("active") or []
    states = collections.Counter(job.get("state", "unknown") for job in jobs)
    attempts_24h = recent(attempts, cutoff)
    integrations_24h = recent(integrations, cutoff)
    accepted = sum(str(row.get("outcome", "")).startswith("accepted") for row in attempts_24h)
    not_accepted = sum(str(row.get("outcome", "")).startswith("gate_failed") for row in attempts_24h)
    infra_attempts = sum(is_system_problem(row.get("outcome")) for row in attempts_24h)
    integrated = sum(row.get("outcome") in (
        "pushed_full_production_gate_green",
        "committed_locally_full_production_gate_green",
        "committed_full_production_gate_green",
    ) for row in integrations_24h)
    unresolved = [job for job in jobs if is_system_problem(job.get("outcome"))
                  and job.get("state") in ("failed", "integration_failed")
                  and not job.get('superseded_by')]
    moving = [job for job in jobs if job.get("state") in ("working", "integrating", "awaiting_integration")]
    producers = [item for item in active if item.get("kind") == "producer"]
    running_count = len(moving) + len(producers)
    queue = status.get("queue") or {}
    runnable = queue.get("runnable", states.get("queued", 0))
    deferred = queue.get("deferred", len(status.get("deferred") or []))
    cache = status.get("cache_maintenance") or {}

    warnings = []
    if snapshot.get("errors"):
        warnings.append("dashboard data unavailable: " + "; ".join(snapshot["errors"]))
    if status and status.get("state") != "running":
        warnings.append("Factory NG controller is not running")
    if unresolved:
        warnings.append("%d unresolved system failure(s)" % len(unresolved))
    if cache.get("state") == "failed":
        warnings.append("Go cache maintenance failed")
    if change.get('auto') is not None and change['auto'] <= 0:
        warnings.append('no enabled-card increase over the last 24 hours')
    health = "REVIEW" if warnings else "OK"
    enabled = current.get("auto")
    enabled_delta = change.get("auto")
    subject = ("[magefield-fleet] Factory NG %s — enabled %s (%s/24h), running %d"
               % (health, value_or_dash(enabled), signed(enabled_delta), running_count))

    active_lines = []
    listed_tickets = set()
    for item in active:
        label = item.get("id", "unknown")
        detail = item.get("ticket_id") or item.get("kind", "work")
        active_lines.append("  %-18s %s" % (label, detail))
        if item.get("ticket_id"):
            listed_tickets.add(item["ticket_id"])
    for job in moving:
        if job.get("ticket_id") in listed_tickets:
            continue
        label = job.get("worker") or job.get("state", "factory")
        active_lines.append("  %-18s %s" % (label, job.get("ticket_id", "unknown ticket")))
    if not active_lines:
        active_lines = ["  none at snapshot time"]
    warning_text = "\n".join("  ! " + warning for warning in warnings) if warnings else "  OK — no current system break"
    body = f"""Magefield Factory NG — daily report
Snapshot: {now.astimezone().strftime('%Y-%m-%d %H:%M %Z')} · window: previous 24 hours

HEALTH
{warning_text}

CARDS — same source and definitions as the dashboard
  Corpus total:        {value_or_dash(current.get('corpus_total'))}
  Corpus classified:   {value_or_dash(current.get('corpus_classified'))}
  Imported:            {value_or_dash(current.get('imported'))} ({signed(change.get('imported'))}/24h)
  Enabled / auto:      {value_or_dash(enabled)} ({signed(enabled_delta)}/24h)
  Needs review:        {value_or_dash(current.get('review'))} ({signed(change.get('review'))}/24h)
  Manual:              {value_or_dash(current.get('manual'))} ({signed(change.get('manual'))}/24h)

FACTORY NOW
  Controller:          {status.get('state', 'unknown')}
  Processes shown:     {running_count}
  Queue:               {runnable} runnable · {deferred} deferred
  Jobs:                {states.get('working', 0)} working · {states.get('integrating', 0) + states.get('awaiting_integration', 0)} integrating · {states.get('queued', 0)} queued
  Go cache:            {cache.get('state', 'idle')} · {cache.get('cache_path', '/opt/development/.gocache-magic')}
{os.linesep.join(active_lines)}

LAST 24 HOURS
  Observation attempts: {len(attempts_24h)}
  Candidates accepted:  {accepted}
  Not accepted by gate:  {not_accepted}  (expected decisions, not system failures)
  Infrastructure errors: {infra_attempts}
  Successful integrations: {integrated}
  Cards newly enabled:   {value_or_dash(enabled_delta)}

MODEL CAPACITY
{limit_line('Claude', limits.get('claude'))}
{limit_line('Codex', limits.get('codex'))}

TOTAL DURABLE FACTORY RECORDS
  TicketSpecs: {len(data.get('tickets') or [])} · attempts: {len(attempts)} · integration waves: {len(integrations)}

Dashboard: http://localhost:9999/dashboard
Source: /factory-ng/cards, /factory-ng/status, /factory-ng/data, /factory-ng/limits
Legacy dispatcher SQLite, old tmux lane names, and git-message estimates are intentionally not used.
"""
    return {"subject": subject, "body": body, "health": health,
            "metrics": {"enabled": enabled, "enabled_delta_24h": enabled_delta,
                        "running": running_count, "accepted_24h": accepted,
                        "integrations_24h": integrated, "system_problems": len(unresolved)}}


def send(report, recipient, sender):
    binary = shutil.which("sendmail") or "/usr/sbin/sendmail"
    message = EmailMessage()
    message["Subject"] = report["subject"]
    message["From"] = "magefield-fleet <%s>" % sender
    message["To"] = recipient
    message.set_content(report["body"])
    subprocess.run([binary, "-f", sender, "-t"], input=message.as_bytes(), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--to", default=os.getenv("REPORT_TO", "dani@sunier.li"))
    parser.add_argument("--from", dest="sender", default=os.getenv("REPORT_FROM", "dani@sunier.li"))
    args = parser.parse_args()
    report = summarize(fetch_snapshot(args.base_url))
    if args.send:
        send(report, args.to, args.sender)
        print("[%s] Factory NG daily report sent to %s (%s)" %
              (utc_now().isoformat(), args.to, report["health"]))
    elif args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(report["subject"])
        print()
        print(report["body"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
