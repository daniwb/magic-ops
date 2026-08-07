#!/usr/bin/env python3
"""Resolve NEED: lines from a pipeline model reply into code regions.

stdin: model output containing lines like
  NEED: backend/game/ability_effects.go executeDiscardEffect
  NEED: _GAIN_CONTROL_FILT
stdout: line-numbered regions. Run from the repo/clone root.

Each NEED line may mix a path and free text; we extract path-looking tokens
and identifier-looking tokens separately (models add prose like "(full
body)" — treating the raw line as one grep string finds nothing).
"""
import os, re, subprocess, sys

STOP = {'function', 'full', 'body', 'file', 'equivalent', 'pattern', 'mirror',
        'switch', 'case', 'and', 'its', 'the', 'registration', 'primitive'}

def regions_for(path, idents, budget):
    out = []
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    hits = []
    for ident in idents:
        hits += [i for i, l in enumerate(lines) if ident in l]
    if not hits:
        take = min(len(lines), 120, budget)
        out.append('### %s:1-%d (head; no requested symbol found in file)\n%s'
                   % (path, take, '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(take))))
        return out, budget - take
    # widen around the first hit per distinct area; function bodies need room
    merged = []
    for h in sorted(set(hits))[:4]:
        lo, hi = max(0, h - 10), min(len(lines), h + 90)
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    for lo, hi in merged[:3]:
        if budget <= 0:
            break
        take = min(hi - lo, budget)
        out.append('### %s:%d-%d\n%s' % (path, lo + 1, lo + take,
                   '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(lo, lo + take))))
        budget -= take
    return out, budget

needs = re.findall(r'^NEED:\s*(.+)$', sys.stdin.read(), re.M)[:3]
if not needs:
    sys.exit(1)
budget = 500
for need in needs:
    if budget <= 0:
        break
    paths = [t for t in re.findall(r'[\w./-]+\.(?:go|py)', need) if '/' in t or '.' in t]
    idents = [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]{4,}', need)
              if t.lower() not in STOP and not t.endswith(('.go', '.py'))]
    handled = False
    for p in paths:
        if os.path.exists(p):
            secs, budget = regions_for(p, idents, budget)
            print('\n\n'.join(secs) + '\n')
            handled = True
        else:
            # basename search: model may guess a filename that doesn't exist
            base = os.path.basename(p)
            try:
                found = subprocess.run(['find', 'backend', 'scripts', '-name', base],
                                       capture_output=True, text=True, timeout=20).stdout.split()
            except Exception:
                found = []
            if found:
                secs, budget = regions_for(found[0], idents, budget)
                print('\n\n'.join(secs) + '\n')
                handled = True
            else:
                print('### %s: file NOT FOUND — nearest matches below\n' % p)
    if not handled and idents:
        try:
            out = subprocess.run(['grep', '-rln', '--include=*.py', '--include=*.go'] +
                                 [idents[0]] + ['scripts/paragraph', 'backend/cards', 'backend/game'],
                                 capture_output=True, text=True, timeout=30).stdout.split()
        except Exception:
            out = []
        for f in out[:2]:
            secs, budget = regions_for(f, idents, budget)
            print('\n\n'.join(secs) + '\n')
            handled = True
        if not handled:
            print('### %r: nothing found in scripts/paragraph, backend/cards, backend/game\n' % need)
