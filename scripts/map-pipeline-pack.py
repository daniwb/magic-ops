#!/usr/bin/env python3
"""map-pipeline stage A: deterministic context pack for one REPARSE-MAP ticket.

Gathers everything the model needs for ONE focused patch call — ticket shape,
example cards with their oracle text and CURRENT reparse misses, the relevant
parser/converter code regions, and knowledge-service hits — so the model call
that follows needs zero exploration turns (the 22M-token anatomy was turns x
re-read context; this replaces ~100 agentic turns with one packed prompt).

Usage: map-pipeline-pack.py TICKET_ID [--repo PATH] [--db PATH]
Writes the pack to stdout; exits 3 if the ticket is not a parseable map ticket.
"""
import argparse, json, glob, os, re, sqlite3, subprocess, sys, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument('ticket', type=int)
ap.add_argument('--repo', default='/opt/development/test/openmagic')
ap.add_argument('--db', default='/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db')
ap.add_argument('--kb', default='http://127.0.0.1:4103')
a = ap.parse_args()

c = sqlite3.connect(a.db)
row = c.execute('select title, descr from tickets where id=?', (a.ticket,)).fetchone()
if not row:
    sys.exit('no such ticket %d' % a.ticket)
title, descr = row
m = re.search(r'Miss shape:\*\*\s*`([^`]+)`', descr)
if not m:
    sys.exit(3)
shape = m.group(1)
examples = re.findall(r'^- \[([^\]]+)\]', descr, re.M)[:5]

os.chdir(a.repo)
sys.path.insert(0, os.path.join(a.repo, 'scripts/paragraph'))
import reparse as R  # noqa: E402

recs = {}
for f in glob.glob('backend/data/carddb/*.json'):
    if f.endswith(('_handlers.json', '_unresolved.json')):
        continue
    try:
        d = json.load(open(f))
    except Exception:
        continue
    for n in set(d) & set(examples):
        recs[n] = d[n]

card_sections = []
for n in examples:
    r = recs.get(n)
    if not r:
        continue
    try:
        out = R.reparse_card(r)
        misses = out.get('misses') if isinstance(out, dict) else '?'
    except Exception as e:
        misses = 'reparse_card raised: %r' % e
    card_sections.append('### %s\nOracle text:\n%s\nCurrent misses: %s' %
                         (n, r.get('text', '?'), misses))

# Code regions: grep the shape's distinguishing token through the parser
# sources, include +-25 lines per hit region, cap total.
token = shape.split(':', 1)[1] if ':' in shape else shape
token = re.sub(r'[^a-z_].*$', '', token) or token
code_sections, budget = [], 260
files = ['scripts/paragraph/slotparse_triggered.py', 'scripts/paragraph/reparse.py',
         'scripts/paragraph/slotparse.py', 'backend/cards/v2.go', 'backend/cards/converter.go']
for f in files:
    if budget <= 0 or not os.path.exists(f):
        continue
    lines = open(f, encoding='utf-8', errors='replace').read().splitlines()
    hits = [i for i, l in enumerate(lines) if token and token in l]
    if not hits and 'slotparse_triggered' in f and shape.startswith('event_unsupported'):
        hits = [30]  # the EVENTS table
    merged = []
    for h in hits[:4]:
        lo, hi = max(0, h - 25), min(len(lines), h + 25)
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    for lo, hi in merged:
        take = min(hi - lo, budget)
        seg = '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(lo, lo + take))
        code_sections.append('### %s:%d-%d\n%s' % (f, lo + 1, lo + take, seg))
        budget -= take

kb_hits = ''
try:
    q = urllib.parse.quote(token.replace('_', ' '))
    kb_hits = urllib.request.urlopen('%s/find?q=%s&n=3' % (a.kb, q), timeout=5).read().decode()
except Exception:
    pass

print('''# MAP-PIPELINE TASK — single-shot patch, no exploration

Ticket #%d: %s
Miss shape: `%s`

You are patching the deterministic MTG reparse pipeline (repo openmagic).
The shape above blocks the example cards below. Your job: ONE minimal patch to
the parser/converter tables so these paragraphs map to REGISTERED vocabulary.
Rules (map contract):
- Registered vocabulary ONLY. If a genuinely new engine primitive is required,
  do NOT patch — output the park verdict instead.
- NEVER touch backend/game/ (auto-park). Parser tables + backend/cards/ only.
- Prefer extending existing tables/regex/case-lists over new mechanisms.

## Example cards (current state)
%s

## Relevant code regions (line-numbered, read-only reference)
%s

## Knowledge-service hits
%s

## OUTPUT FORMAT (strict)
EITHER a park verdict:
VERDICT: NEEDS_PRIMITIVE|SEMANTIC_GAP|AMBIGUOUS|NOT_A_SHAPE
REASON: <one line>

OR one or more edit blocks (exact-match search text, unique in the file):
<<<FILE path/relative/to/repo
<<<SEARCH
exact existing lines (copy verbatim, WITHOUT the line-number prefixes)
===REPLACE
replacement lines
>>>END

End with one line:
EXPECT: <which example paragraph(s) should now parse and to what>
No other prose.''' % (a.ticket, title, shape,
                      '\n\n'.join(card_sections) or '(no records found)',
                      '\n\n'.join(code_sections) or '(no code hits)',
                      kb_hits.strip() or '(kb unavailable)'))
