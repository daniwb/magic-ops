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
        'switch', 'case', 'and', 'its', 'the', 'registration', 'primitive',
        'exact', 'implementation', 'definitions', 'definition', 'used',
        'identify', 'representation', 'accessors', 'points'}

def regions_for(path, idents, budget):
    out = []
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    ordered_hits = []
    symbol_first = sorted(idents, key=lambda ident: (
        0 if ('_' in ident or any(ch.isupper() for ch in ident[1:])) else 1,
        idents.index(ident)))
    for ident in symbol_first:
        word = re.compile(r'\b%s\b' % re.escape(ident))
        decl = re.compile(r'^\s*(?:func|type|var|const|def|class)\b.*\b%s\b' % re.escape(ident))
        matches = [i for i, line in enumerate(lines) if word.search(line)]
        matches.sort(key=lambda i: (0 if decl.search(lines[i]) else 1, i))
        ordered_hits.extend(matches[:1])
    hits = list(dict.fromkeys(ordered_hits))
    if not hits:
        take = min(len(lines), 120, budget)
        out.append('### %s:1-%d (head; no requested symbol found in file)\n%s'
                   % (path, take, '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(take))))
        return out, budget - take
    # Preserve requested-symbol order instead of globally sorting by line.
    # Generic words such as "damage" must not crowd out an explicitly named
    # executeDamageEffect declaration thousands of lines later.
    merged = []
    for h in hits[:5]:
        lo, hi = max(0, h - 10), min(len(lines), h + 180)
        if not any(lo < old_hi and hi > old_lo for old_lo, old_hi in merged):
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
    # explicit line ranges (path:NNN-MMM) — models ask for these constantly;
    # without support they got the file head and re-asked until abort
    handled_range = False
    for m in re.finditer(r'([\w./-]+\.(?:go|py)):(\d+)-(\d+)', need):
        p, lo, hi = m.group(1), int(m.group(2)) - 1, int(m.group(3))
        if not os.path.exists(p):
            continue
        lines = open(p, encoding='utf-8', errors='replace').read().splitlines()
        lo = max(0, min(lo, len(lines))); hi = min(hi, len(lines), lo + budget)
        if hi > lo:
            print('### %s:%d-%d\n%s\n' % (p, lo + 1, hi,
                  '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(lo, hi))))
            budget -= (hi - lo)
            handled_range = True
    if handled_range:
        continue
    paths = [t for t in re.findall(r'[\w./-]+\.(?:go|py)', need) if '/' in t or '.' in t]
    # path_words: exclude words that just echo a requested path's own
    # components (e.g. "reparse.py" in the NEED line makes "scripts",
    # "paragraph", "reparse" look like content-search identifiers, but
    # matching a file's own name/dir against ITS OWN docstring/imports is
    # noise, not signal — confirmed live 2026-08-12 (ticket #3168,
    # put_counters): those generic words hit early lines (docstring at
    # line 1, "paragraph" in a comment at line 13) and crowded out the
    # real "put_counter" hits starting at line 760 out of hits[:4]'s
    # sorted-position cap, so the actually-relevant region never got
    # served across 2 full NEED rounds. See memory
    # circle_duplicate_primitive_waste.md for the related registry.go fix.
    path_words = {w.lower() for p in paths for w in re.split(r'[/._-]', p) if w}
    idents = [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]{4,}', need)
              if t.lower() not in STOP and t.lower() not in path_words
              and not t.endswith(('.go', '.py'))]
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
