#!/usr/bin/env python3
"""Resolve NEED: lines from a pipeline model reply into code regions.

stdin: model output containing lines like 'NEED: scripts/paragraph/reparse.py'
or 'NEED: _GAIN_CONTROL_FILT' (symbol). stdout: line-numbered regions.
Run from the repo/clone root.
"""
import os, re, subprocess, sys

needs = re.findall(r'^NEED:\s*(.+)$', sys.stdin.read(), re.M)[:3]
if not needs:
    sys.exit(1)
budget = 400
for need in needs:
    need = need.strip().strip('`')
    if budget <= 0:
        break
    if os.path.exists(need):
        lines = open(need, encoding='utf-8', errors='replace').read().splitlines()
        take = min(len(lines), 150, budget)
        print('### %s:1-%d (full-file head; request a symbol for a deeper slice)\n%s\n'
              % (need, take, '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(take))))
        budget -= take
        continue
    # symbol: grep across parser + cards sources
    try:
        out = subprocess.run(['grep', '-rn', '--include=*.py', '--include=*.go', '-l', need,
                              'scripts/paragraph', 'backend/cards', 'backend/game'],
                             capture_output=True, text=True, timeout=30).stdout.split()
    except Exception:
        out = []
    for f in out[:2]:
        lines = open(f, encoding='utf-8', errors='replace').read().splitlines()
        hits = [i for i, l in enumerate(lines) if need in l]
        for h in hits[:2]:
            if budget <= 0:
                break
            lo, hi = max(0, h - 40), min(len(lines), h + 60)
            take = min(hi - lo, budget)
            print('### %s:%d-%d\n%s\n' % (f, lo + 1, lo + take,
                  '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(lo, lo + take))))
            budget -= take
    if not out:
        print('### %s: NOT FOUND in scripts/paragraph, backend/cards, backend/game\n' % need)
