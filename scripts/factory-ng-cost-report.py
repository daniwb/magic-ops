#!/usr/bin/env python3
"""Read-only attempt/mission accounting from the dashboard's SQLite snapshot.

No quota weighting or missing-counter imputation. Shared dependencies are
counted once within a report; separate mission reports must not be added.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3

OPS = Path(__file__).resolve().parents[1]
FIELDS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens',
          'provider_cost_usd', 'elapsed_ms')


def mission_members(root, edges):
    children, parents = {}, {}
    for parent, child in edges:
        if not parent.startswith('ticket:'):
            continue
        children.setdefault(parent, set()).add(child)
        parents.setdefault(child, set()).add(parent)
    def closure(seed, links):
        found, pending = set(seed), list(seed)
        while pending:
            for key in links.get(pending.pop(), ()):
                if key not in found:
                    found.add(key)
                    pending.append(key)
        return found
    return closure(closure({root}, children), parents)


def aggregate(rows):
    # Deduplicate by immutable receipt identity, including shared dependencies.
    rows = list({row['receipt_path']: row for row in rows}.values())
    values = {}
    for field in FIELDS:
        known = [r.get('telemetry', {}).get(field) for r in rows
                 if type(r.get('telemetry', {}).get(field)) in (int, float)]
        values[field] = {'known_sum': sum(known), 'known_attempts': len(known),
                         'unknown_attempts': len(rows) - len(known)}
    stages = {}
    for key in ('attempt_wall_ms', 'model_ms', 'candidate_gate_ms', 'compilation_ms'):
        known = [r.get('telemetry', {}).get('stage_times', {}).get(key) for r in rows
                 if type(r.get('telemetry', {}).get('stage_times', {}).get(key)) in (int, float)]
        stages[key] = {'known_sum': sum(known), 'unknown_attempts': len(rows) - len(known)}
    return {'attempts': len(rows), 'ticket_versions': len({r['ticket_id'] for r in rows}),
            'outcomes': dict(Counter(r['outcome'] for r in rows)), 'counters': values,
            'stage_times': stages}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=OPS / 'state/factory-ng-dashboard.sqlite3')
    parser.add_argument('--ticket', help='Root mission ticket; includes descendants and their dependencies')
    parser.add_argument('--since', help='Inclusive UTC timestamp, e.g. 2026-09-08T20:00:00Z; mission default is all history')
    parser.add_argument('--until', help='Exclusive UTC timestamp; default now')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    until = args.until or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    since = args.since or ('' if args.ticket else (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    db = sqlite3.connect('file:' + str(args.db.resolve()) + '?mode=ro', uri=True)
    db.execute('BEGIN')
    members = mission_members(args.ticket, db.execute('SELECT parent,child FROM edges')) if args.ticket else None
    rows = [json.loads(payload) for (payload,) in db.execute(
        "SELECT payload FROM artifacts WHERE kind='attempt' AND created_at>=? AND created_at<?", (since, until))]
    rows = [r for r in rows if members is None or r['ticket_id'] in members]
    jobs = [json.loads(payload) for (payload,) in db.execute('SELECT payload FROM jobs')]
    integration_times = Counter()
    integration_outcomes = Counter()
    integrations_without_timing = 0
    for (payload,) in db.execute("SELECT payload FROM artifacts WHERE kind='integration' AND created_at>=? AND created_at<?", (since, until)):
        row = json.loads(payload)
        if members is not None and not members.intersection(row.get('parents', [])):
            continue
        integration_outcomes[row['outcome']] += 1
        # Integration receipts already retain explicit build and test stages.
        # Read just the selected receipts, never provider logs or the full tree.
        receipt = json.loads((OPS / row['receipt_path']).read_text())
        timed = [g for g in receipt.get('gates', []) if type(g.get('elapsed_ms')) is int]
        integrations_without_timing += not bool(timed)
        for gate in timed:
            command = gate.get('command', '')
            if isinstance(command, list): command = ' '.join(command)
            category = ('explicit_build_ms' if re.search(r'\b(?:go|go-cache-run\.sh)\s+build\b', command) else
                        'test_commands_including_compile_ms' if re.search(r'\b(?:go|go-cache-run\.sh)\s+test\b', command) or gate.get('id') == 'full-sharded-suite' else
                        'other_integration_gates_ms')
            integration_times[category] += gate['elapsed_ms']
    result = {'schema': 'factory.cost-report/v1', 'since': since or 'all history', 'until': until,
              'mission': args.ticket, 'total': aggregate(rows),
              'integration': {'outcomes': dict(integration_outcomes), 'stage_times': dict(integration_times),
                              'receipts_without_timing': integrations_without_timing},
              'profiles': {profile: aggregate([r for r in rows if r['profile'] == profile])
                           for profile in sorted({r['profile'] for r in rows})},
              'current_unresolved': [j for j in jobs if members is not None and j['ticket_id'] in members
                                     and not j.get('superseded_by') and j['state'] in ('failed', 'parked', 'integration_failed')],
              'definitions': [
                  'Raw counters are retained by profile. Do not add input and cached-input across providers: inclusion semantics differ.',
                  'elapsed_ms is accumulated provider-call wall time, not total attempt duration.',
                  'Candidate gate time includes compilation, test execution and gate overhead; separate compilation remains unknown.',
                  'Unknown cost is not free. Effective quota tokens and dollars cannot be inferred from raw counters.',
                  'Each receipt is counted once per report. Shared dependencies can belong to multiple mission reports; do not add their totals.',
                  'Accepted candidates and completed tickets are not whole-card verification.',
              ]}
    db.close()
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
