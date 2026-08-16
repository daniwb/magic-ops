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
implemented_capabilities = []
try:
    implemented_capabilities = c.execute(
        '''select c.id,c.capability_key,c.specification_json,c.implementation_commit
           from ticket_capabilities tc join capabilities c on c.id=tc.capability_id
           where tc.ticket_id=? and c.state='implemented' order by c.id''',
        (a.ticket,)).fetchall()
except sqlite3.OperationalError:
    pass  # legacy dispatcher DB during migration
m = re.search(r'Miss shape:\*\*\s*`([^`]+)`', descr)
if not m:
    sys.exit(3)
shape = m.group(1)
examples = re.findall(r'^- \[([^\]]+)\]', descr, re.M)[:5]
# CLUSTERED slice tickets (gen_fleet_tasks mega-shape split, 2026-08-08):
# the shape is shared by MANY template families, so the live-pile rescan
# below must stay within THIS ticket's family cards — otherwise every slice
# pack shows the same 5 alphabetically-first cards of the whole shape and
# the model judges the wrong family (seen on the first three ?-slices).
cluster_allow = None
if 'CLUSTERED slice' in descr:
    cluster_allow = set(re.findall(r'^- \[([^\]]+)\]', descr, re.M))

os.chdir(a.repo)
sys.path.insert(0, os.path.join(a.repo, 'scripts/paragraph'))
import reparse as R  # noqa: E402

# The ticket's example list is a snapshot from generation time — cards may
# have been fixed since (2482: 2 of 3 already parsed, so the model judged the
# whole 34-card family from n=1 and parked). Scan the live review pile for up
# to 5 cards that CURRENTLY miss with this exact shape instead.
card_sections, found = [], 0
for f in sorted(glob.glob('backend/data/carddb/*.json')):
    if found >= 5 or f.endswith(('_handlers.json', '_unresolved.json')):
        continue
    try:
        d = json.load(open(f))
    except Exception:
        continue
    for n, r in d.items():
        if found >= 5:
            break
        if r.get('status') != 'review':
            continue
        if cluster_allow is not None and n not in cluster_allow:
            continue
        try:
            out = R.reparse_card(r)
            misses = out.get('misses') if isinstance(out, dict) else []
        except Exception:
            continue
        if any(m[0] == shape for m in (misses or [])):
            card_sections.append('### %s\nOracle text:\n%s\nCurrent misses: %s' %
                                 (n, r.get('text', '?'), misses))
            found += 1

# Code regions: grep the shape's distinguishing token through the parser
# sources, include +-25 lines per hit region, cap total.
token = shape.split(':', 1)[1] if ':' in shape else shape
token = re.sub(r'[^a-z_].*$', '', token) or token
code_sections, budget = [], 260

# registry.go exact-key check, added 2026-08-12 (see [[circle_duplicate_
# primitive_waste]]): two confirmed false "no registered X primitive
# exists" parks (tap, exile — both long-registered, core verbs), traced to
# the model never being shown registry.go and not asking for it via NEED
# for a verb that "obviously" seemed unregistered. A loose substring search
# for "exile" in registry.go hits 20+ lines (other entries' comments
# mentioning exile, e.g. the "destroy" entry's cross-reference) LONG before
# the real `"exile": {...}` key at its own line — first-4-hits-with-±25-
# window never reaches it. So this checks for the EXACT registered key
# `"token": {` first (small, cheap, unambiguous — the one fact that matters
# most for avoiding a duplicate-primitive park) before falling back to the
# general substring search below for everything else.
try:
    reg_lines = open('backend/cards/registry.go', encoding='utf-8', errors='replace').read().splitlines()
    key_re = re.compile(r'^\s*"%s":\s*\{' % re.escape(token))
    key_hit = next((i for i, l in enumerate(reg_lines) if key_re.match(l)), None)
    if key_hit is not None:
        lo, hi = key_hit, min(len(reg_lines), key_hit + 6)
        seg = '\n'.join('%5d %s' % (i + 1, reg_lines[i]) for i in range(lo, hi))
        code_sections.append('### backend/cards/registry.go:%d-%d (exact key match for "%s")\n%s' % (lo + 1, hi, token, seg))
        budget -= (hi - lo)
except OSError:
    pass

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
    # Always blend the shape token with real words from the blocked example
    # cards' oracle text (card_sections, already collected above) — the
    # token alone is often too generic to surface what a ticket is
    # actually about. Two found failure modes, both 2026-08-11:
    #  1. Catch-all shapes ("verb_unmapped:?") reduce token to punctuation
    #     — literally querying kb for "?". Every registered primitive was
    #     invisible to every such ticket all night.
    #  2. Category-shaped tokens that ARE real words ("kw_action",
    #     "static_subject") still aren't card-specific: og1's kw_action
    #     ticket queried "kw action" and never found amass/monstrosity/
    #     proliferate even though the kb index has all three (verified
    #     live) — the query was too generic, not the index stale.
    # kb's own /find already AND-matches first and falls back to OR across
    # all words if that's empty (card-knowledge-service.py:171-172), so
    # blending in extra words is safe — worst case it degrades to OR
    # ranking instead of returning nothing.
    token_words = token.replace('_', ' ') if re.search(r'[a-z]{3,}', token) else ''
    example_words = ' '.join(re.findall(r'\b[a-z]{4,}\b', ' '.join(card_sections).lower()))
    kb_query = (token_words + ' ' + example_words).strip()[:300]
    q = urllib.parse.quote(kb_query)
    kb_hits = urllib.request.urlopen('%s/find?q=%s&n=5' % (a.kb, q), timeout=5).read().decode()
except Exception:
    pass

implemented_section = ''
if implemented_capabilities:
    parts = []
    diff_budget = 260
    for cid, key, spec_json, commit in implemented_capabilities:
        try:
            spec_text = json.dumps(json.loads(spec_json), indent=2, sort_keys=True)
        except Exception:
            spec_text = spec_json
        diff = ''
        if commit and diff_budget > 0:
            proc = subprocess.run(
                ['git', 'show', '--format=', '--no-ext-diff', commit, '--', 'backend/game', 'backend/cards'],
                cwd=a.repo, capture_output=True, text=True)
            lines = proc.stdout.splitlines()[:diff_budget]
            diff = '\n'.join(lines)
            diff_budget -= len(lines)
        parts.append('### Capability #%s `%s` (already implemented)\n%s\n\nImplementation diff:\n%s' %
                     (cid, key, spec_text, diff or '(commit diff unavailable)'))
    implemented_section = '''
## IMPLEMENTED CAPABILITIES FOR THIS TICKET

The engine work below is already on main. Wire the parser/converter to these
exact capabilities. Do not request another primitive for the same behavior.
If the current examples genuinely need a different behavior, return AMBIGUOUS
for discovery rather than broadening or duplicating the implemented primitive.

%s
''' % '\n\n'.join(parts)

print('''# MAP-PIPELINE TASK — single-shot patch, no exploration

Ticket #%d: %s
Miss shape: `%s`

You are patching the deterministic MTG reparse pipeline (repo openmagic).
The shape above blocks the example cards below. Your job: ONE minimal patch to
the parser/converter tables so these paragraphs map to REGISTERED vocabulary.
Rules (map contract):
- Registered vocabulary ONLY. If a genuinely new engine primitive is required
  for ALL examples, do NOT patch — output the park verdict instead. If only
  SOME examples need engine work, patch the mappable ones and name the
  engine-blocked remainder in the EXPECT line.
- NEVER touch backend/game/ (auto-park). Parser tables + backend/cards/ only.
- Prefer extending existing tables/regex/case-lists over new mechanisms.

## Example cards (current state)
%s

## Relevant code regions (line-numbered, read-only reference)
%s

## Knowledge-service hits
%s

%s

## TOOL BUDGET
You may Read/Grep/Glob to verify exact lines (~10 tool calls budget). Plan
your reads, then STOP exploring and emit your answer — your FINAL message
MUST be the output format below. An imperfect block set beats running out of
turns in silence: the gate catches errors and you get one retry with the
failure detail.

## OUTPUT FORMAT (strict)
If ESSENTIAL source is missing from the code regions above (you would have to
guess exact lines), reply ONLY with up to 3 request lines and nothing else:
NEED: <repo-relative-path or exact symbol/identifier>
The harness will send the regions and re-ask ONCE.

OTHERWISE — EITHER a park verdict. NEEDS_PRIMITIVE is legal ONLY when every
source_miss in the capability object needs the SAME atomic behavior. If the
examples require different behaviors, return AMBIGUOUS so discovery can split
the ticket; never invent one umbrella primitive name.
VERDICT: NEEDS_PRIMITIVE|SEMANTIC_GAP|AMBIGUOUS|NOT_A_SHAPE
For NEEDS_PRIMITIVE, add exactly one single-line JSON object (no markdown):
PRIMITIVE: <same lowercase_snake_case key, retained for legacy dashboards>
CAPABILITY_JSON: {"key":"lowercase_snake_case","summary":"short description","specification":{"required_behavior":"one precise atomic behavior","source_misses":[{"card":"ONE representative exact card name","paragraph":"exact relevant oracle paragraph","required_behavior":"the identical required_behavior text"}],"negative_examples":["adjacent behavior that must not change"],"expected_unlock":0}}
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
                      kb_hits.strip() or '(kb unavailable)', implemented_section))
