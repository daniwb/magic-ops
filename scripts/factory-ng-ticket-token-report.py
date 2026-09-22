#!/usr/bin/env python3
"""Per-ticket token usage from the dashboard's SQLite snapshot.

Groups attempt telemetry by base ticket (retries across /vN merged) over a
window, so you can see which tickets are burning the most tokens. Read-only.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3

OPS = Path(__file__).resolve().parents[1]
FIELDS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens')

# Per docs/factory-ng/CURRENT.md and the model-profile adapters (docs/factory-ng/model-profiles/v1/*.json):
# agentic profiles run a native/tool-use loop (allowed_tools + max_turns > 1); non-agentic profiles
# are no-tools completions from a prepared/staged packet (allowed_tools empty, max_turns <= 5).
AGENTIC_PROFILES = {'codex-constrained', 'qwen-prepared-local', 'claude-agentic', 'claude-agentic-test',
                    'openrouter-prepared-agentic'}
NON_AGENTIC_PROFILES = {'claude-staged', 'qwen-prepared-direct', 'minimax-prepared-direct',
                        'openrouter-prepared-direct', 'nemotron-structured-edit'}


def base_ticket(ticket_id):
    return re.sub(r'/v\d+$', '', ticket_id)


def classify_profile(profile):
    base = (profile or '').split('@')[0]
    if base in AGENTIC_PROFILES:
        return 'agentic'
    if base in NON_AGENTIC_PROFILES:
        return 'non_agentic'
    return 'unknown'


def aggregate(rows):
    rows = list({row['receipt_path']: row for row in rows}.values())
    totals = {}
    for field in FIELDS:
        known = [r.get('telemetry', {}).get(field) for r in rows
                 if type(r.get('telemetry', {}).get(field)) in (int, float)]
        totals[field] = sum(known)
    totals['total_tokens'] = totals['input_tokens'] + totals['output_tokens']
    totals['attempts'] = len(rows)
    totals['versions'] = sorted({r['ticket_id'] for r in rows})
    totals['outcomes'] = dict(Counter(r['outcome'] for r in rows))
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=OPS / 'state/factory-ng-dashboard.sqlite3')
    parser.add_argument('--days', type=float, default=7, help='Lookback window in days')
    parser.add_argument('--since', help='Inclusive UTC timestamp, overrides --days')
    parser.add_argument('--until', help='Exclusive UTC timestamp; default now')
    parser.add_argument('--limit', type=int, default=25, help='Rows to show in the table (0 = all)')
    parser.add_argument('--json', action='store_true', help='Emit full JSON instead of a table')
    args = parser.parse_args()

    until = args.until or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    since = args.since or (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime('%Y-%m-%dT%H:%M:%SZ')

    db = sqlite3.connect('file:' + str(args.db.resolve()) + '?mode=ro', uri=True)
    db.execute('BEGIN')
    rows = [json.loads(payload) for (payload,) in db.execute(
        "SELECT payload FROM artifacts WHERE kind='attempt' AND created_at>=? AND created_at<?", (since, until))]
    db.close()

    by_ticket = defaultdict(list)
    for row in rows:
        by_ticket[base_ticket(row['ticket_id'])].append(row)

    tickets = {ticket_id: aggregate(attempt_rows) for ticket_id, attempt_rows in by_ticket.items()}
    ranked = sorted(tickets.items(), key=lambda kv: kv[1]['total_tokens'], reverse=True)

    by_class = defaultdict(list)
    for row in rows:
        by_class[classify_profile(row.get('profile'))].append(row)
    execution_modes = {}
    for cls, cls_rows in by_class.items():
        cls_tickets = {base_ticket(r['ticket_id']) for r in cls_rows}
        execution_modes[cls] = {**aggregate(cls_rows), 'tickets': len(cls_tickets)}

    result = {
        'schema': 'factory.ticket-token-report/v1',
        'since': since, 'until': until,
        'ticket_count': len(tickets),
        'attempt_count': len(rows),
        'grand_total': aggregate(rows),
        'execution_modes': execution_modes,
        'tickets': {ticket_id: totals for ticket_id, totals in ranked},
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print(f"Ticket token usage {since} .. {until}")
    print(f"{len(tickets)} tickets, {len(rows)} attempts, "
          f"{result['grand_total']['total_tokens']:,} total tokens "
          f"(in={result['grand_total']['input_tokens']:,} out={result['grand_total']['output_tokens']:,} "
          f"cache_read={result['grand_total']['cache_read_tokens']:,})")
    if tickets:
        avg_total = result['grand_total']['total_tokens'] / len(tickets)
        avg_in = result['grand_total']['input_tokens'] / len(tickets)
        avg_out = result['grand_total']['output_tokens'] / len(tickets)
        avg_attempts = len(rows) / len(tickets)
        print(f"avg per ticket: {avg_total:,.0f} total tokens "
              f"(in={avg_in:,.0f} out={avg_out:,.0f}), {avg_attempts:.2f} attempts")
    print()

    print("By execution mode (agentic = native/tool-use loop; non_agentic = no-tools prepared/staged call):")
    mode_header = f"{'MODE':<12}  {'TICKETS':>8}  {'ATTEMPTS':>8}  {'TOTAL':>14}  {'AVG/TICKET':>12}"
    print(mode_header)
    print('-' * len(mode_header))
    for cls in ('agentic', 'non_agentic', 'unknown'):
        m = execution_modes.get(cls)
        if not m:
            continue
        avg = m['total_tokens'] / m['tickets'] if m['tickets'] else 0
        print(f"{cls:<12}  {m['tickets']:>8}  {m['attempts']:>8}  {m['total_tokens']:>14,}  {avg:>12,.0f}")
    print()
    header = f"{'TOTAL':>12}  {'INPUT':>12}  {'OUTPUT':>10}  {'CACHE_RD':>12}  {'ATTEMPTS':>8}  TICKET"
    print(header)
    print('-' * len(header))
    shown = ranked if args.limit == 0 else ranked[:args.limit]
    for ticket_id, t in shown:
        print(f"{t['total_tokens']:>12,}  {t['input_tokens']:>12,}  {t['output_tokens']:>10,}  "
              f"{t['cache_read_tokens']:>12,}  {t['attempts']:>8}  {ticket_id}")
    if args.limit and len(ranked) > args.limit:
        print(f"... {len(ranked) - args.limit} more tickets (use --limit 0 for all, or --json)")


if __name__ == '__main__':
    main()
