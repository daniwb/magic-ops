#!/usr/bin/env python3
"""Token-usage report over ALL worker session transcripts.

Computes TRUE per-day and per-model token usage from the claude CLI session
logs under ~/.claude/projects/-tmp-work-* (each factory worker clone gets a
project dir there). This is ground truth — the dispatcher's per-ticket
`tokens` field was last-turn-only until 2026-07-25 and under-reported ~23x.

Usage:
    scripts/token-usage-report.py [--days N]   # default 14

Effective weighting mirrors API pricing: cache_write x1.25 + cache_read x0.1
+ input + output. The Claude plan's window metering is not published but is
assumed to weight similarly; use the effective column for trend comparisons.

Baseline (pre cost-optimization): reports/token-baseline-2026-07-25.txt —
compare a fresh run after the factory's next night to see the effect of the
2026-07-25 changes (cache-stable system-prompt prefix, signature index,
turn diet, mirror+GOCACHE). Expected effects: cache_write/day sinkt deutlich
(Prefix wird gelesen statt geschrieben), Sessions werden kürzer (weniger
Turns -> weniger cache_read pro Job), tokens im Dispatcher steigen OPTISCH
(ehrliches Accounting seit 2026-07-25 ~22:00).
"""
import json, os, glob, datetime, collections, argparse

ap = argparse.ArgumentParser()
ap.add_argument('--days', type=int, default=14)
args = ap.parse_args()
cutoff = datetime.date.today() - datetime.timedelta(days=args.days)

by_day = collections.defaultdict(lambda: {'cw': 0, 'cr': 0, 'in': 0, 'out': 0, 'sessions': 0})
by_model = collections.defaultdict(lambda: {'cw': 0, 'cr': 0, 'in': 0, 'out': 0, 'turns': 0})
nfiles = 0

for d in glob.glob(os.path.expanduser('~/.claude/projects/-tmp-work-*')):
    for f in glob.glob(d + '/*.jsonl'):
        day = datetime.date.fromtimestamp(os.path.getmtime(f))
        if day < cutoff:
            continue
        nfiles += 1
        seen = {}
        try:
            for line in open(f, errors='ignore'):
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                m = rec.get('message') or {}
                u, mid = m.get('usage'), m.get('id')
                if u and mid:
                    seen[mid] = (u, m.get('model') or '?')
        except Exception:
            continue
        if not seen:
            continue
        dk = day.isoformat()
        by_day[dk]['sessions'] += 1
        for u, model in seen.values():
            for src, dst in (('cache_creation_input_tokens', 'cw'), ('cache_read_input_tokens', 'cr'),
                             ('input_tokens', 'in'), ('output_tokens', 'out')):
                by_day[dk][dst] += u.get(src, 0)
                by_model[model][dst] += u.get(src, 0)
            by_model[model]['turns'] += 1

def eff(v):
    return int(v['cw'] * 1.25 + v['cr'] * 0.1 + v['in'] + v['out'])

print(f"generated: {datetime.datetime.now().isoformat(timespec='seconds')}  ({nfiles} session files, last {args.days} days)\n")
print(f"{'day':<12}{'sessions':>9}{'cache_write':>14}{'cache_read':>16}{'input':>12}{'output':>12}{'RAW':>16}{'effective':>13}")
tot = {'cw': 0, 'cr': 0, 'in': 0, 'out': 0}
for day in sorted(by_day):
    v = by_day[day]
    for k in tot:
        tot[k] += v[k]
    print(f"{day:<12}{v['sessions']:>9}{v['cw']:>14,}{v['cr']:>16,}{v['in']:>12,}{v['out']:>12,}"
          f"{v['cw']+v['cr']+v['in']+v['out']:>16,}{eff(v):>13,}")
print(f"{'TOTAL':<12}{'':>9}{tot['cw']:>14,}{tot['cr']:>16,}{tot['in']:>12,}{tot['out']:>12,}"
      f"{sum(tot.values()):>16,}{eff(tot):>13,}")

print(f"\n{'model':<34}{'turns':>7}{'cache_write':>14}{'cache_read':>16}{'input':>12}{'output':>12}{'effective':>13}")
for model in sorted(by_model, key=lambda m: -eff(by_model[m])):
    v = by_model[model]
    print(f"{model:<34}{v['turns']:>7}{v['cw']:>14,}{v['cr']:>16,}{v['in']:>12,}{v['out']:>12,}{eff(v):>13,}")
print("\nnote: non-claude models (glm/kimi/deepseek shadow workers) do NOT draw the Claude plan.")
