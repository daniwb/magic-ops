#!/usr/bin/env python3
"""engine-pipeline stage A: context pack for ONE primitive demand.

Input: a blocked ticket carrying missing_prim (park from a map worker or the
map-pipeline). Gathers the demand reason, the blocked example cards, the
executor code regions the primitive name/reason point at, a worked example
(similar existing primitive), and the wiring conventions — one focused
engine-patch call instead of an agentic session.

Usage: engine-pipeline-pack.py TICKET_ID [--repo PATH] [--db PATH]
"""
import argparse, json, glob, os, re, sqlite3, sys, urllib.request, urllib.parse

ap = argparse.ArgumentParser()
ap.add_argument('ticket', type=int)
ap.add_argument('--capability', type=int, default=0)
ap.add_argument('--repo', default='/opt/development/test/openmagic')
ap.add_argument('--db', default='/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db')
ap.add_argument('--kb', default='http://127.0.0.1:4103')
a = ap.parse_args()

c = sqlite3.connect(a.db)
row = c.execute('select title, descr, missing_prim from tickets where id=?', (a.ticket,)).fetchone()
if not row:
    sys.exit('no such ticket %d' % a.ticket)
title, descr, prim = row
prim = (prim or '').strip()
capability_spec = None
if a.capability:
    cap = c.execute('select capability_key, summary, specification_json from capabilities where id=?',
                    (a.capability,)).fetchone()
    if not cap:
        sys.exit('no such capability %d' % a.capability)
    prim, cap_summary, cap_json = cap
    capability_spec = json.loads(cap_json)
if not prim:
    sys.exit(3)

# Park reason: pipeline replies live in /tmp/orch; fall back to ticket descr.
reason = ''
if capability_spec:
    reason = 'Atomic contract authority: ' + capability_spec['required_behavior']
else:
    for f in sorted(glob.glob('/tmp/orch/pipeline-%d-reply-*.md' % a.ticket), reverse=True):
        t = open(f).read()
        m = re.search(r'^REASON:(.*?)(?=^EXPECT:|\Z)', t, re.M | re.S)
        if m:
            reason = m.group(1).strip()
            break

os.chdir(a.repo)
sys.path.insert(0, os.path.join(a.repo, 'scripts/paragraph'))

# Example cards from the ticket bullet list, with oracle text + misses.
examples = re.findall(r'^- \[([^\]]+)\]', descr, re.M)[:4]
if capability_spec:
    examples = list(dict.fromkeys(m.get('card', '') for m in capability_spec.get('source_misses', [])
                                  if m.get('card')))[:8]
try:
    import reparse as R
except Exception:
    R = None
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
    misses = ''
    if R:
        try:
            out = R.reparse_card(r)
            misses = str(out.get('misses') if isinstance(out, dict) else '')
        except Exception:
            pass
    card_sections.append('### %s\nOracle text:\n%s\nCurrent misses: %s' %
                         (n, r.get('text', '?'), misses))

# Code regions: tokens from the primitive name + identifiers from the reason.
tokens = [t for t in re.split(r'[_\-]', prim) if len(t) > 3]
tokens += re.findall(r'`([A-Za-z_][A-Za-z0-9_.]{4,})`', reason)[:6]
tokens = list(dict.fromkeys(tokens))[:8]
FILES = ['backend/game/ability_effects.go', 'backend/game/gamestate.go',
         'backend/game/events.go', 'backend/game/gamestate_tutor.go',
         'backend/game/targeting.go', 'backend/cards/converter.go',
         'backend/cards/registry.go', 'backend/cards/v2.go']
code_sections, budget = [], 420
scored = []
for f in FILES:
    if not os.path.exists(f):
        continue
    lines = open(f, encoding='utf-8', errors='replace').read().splitlines()
    hits = [i for i, l in enumerate(lines) for t in tokens if t in l]
    if hits:
        scored.append((len(hits), f, lines, sorted(set(hits))))
scored.sort(reverse=True)
for _, f, lines, hits in scored[:4]:
    if budget <= 0:
        break
    merged = []
    for h in hits[:5]:
        lo, hi = max(0, h - 30), min(len(lines), h + 30)
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    for lo, hi in merged[:3]:
        take = min(hi - lo, budget)
        seg = '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(lo, lo + take))
        code_sections.append('### %s:%d-%d\n%s' % (f, lo + 1, lo + take, seg))
        budget -= take

kb_hits = ''
try:
    q = urllib.parse.quote(' '.join(tokens[:4]))
    kb_hits = urllib.request.urlopen('%s/find?q=%s&n=4' % (a.kb, q), timeout=5).read().decode()
except Exception:
    pass

# Shape-test convention: show the head of a recent shape test as template.
test_tmpl = ''
for cand in ['backend/cards/shape_dealt_damage_test.go', 'backend/cards/shape_becomes_targeted_test.go']:
    if os.path.exists(cand):
        test_tmpl = '### %s (convention template, first 60 lines)\n%s' % (
            cand, '\n'.join(open(cand).read().splitlines()[:60]))
        break

print('''# ENGINE-PIPELINE TASK — build ONE small primitive, single-shot

Ticket #%d: %s
Primitive demand: `%s`
Capability ID: `%s`
Atomic capability specification:
%s
Park reason:
%s

You are extending the Go MTG engine (repo openmagic, module magic-backend,
run from backend/). Build the SMALLEST change that delivers this primitive.
Rules:
- backend/game/ edits ARE allowed here (this is the engine tier).
- Follow existing conventions: extend an existing executor/switch where
  possible; wire new vocabulary through the SAME registration points the
  code regions below show (registry entry / converter case / v2 enum) if a
  new effect name is needed.
- A NEW test function in a NEW _test.go file is REQUIRED (gate greps the
  diff for +func Test). Behavior test, not just compilation.
- If this demand is actually FRAMEWORK-SIZED (new event system, new
  dispatch machinery, cross-cutting state), do NOT attempt it.

## Blocked example cards
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

OTHERWISE — EITHER a park verdict:
VERDICT: FRAMEWORK|AMBIGUOUS
REASON: <one line>

OR edit blocks. Existing files via exact-match search/replace:
<<<FILE path/relative/to/repo
<<<SEARCH
exact existing lines (verbatim, no line-number prefixes)
===REPLACE
replacement lines
>>>END
New files (the required test file, new registry file if conventions demand):
<<<NEWFILE path/relative/to/repo
full file content
>>>END

End with one line:
EXPECT: <what now works, one sentence>
No other prose.''' % (a.ticket, title, prim, a.capability or '(legacy)',
                      json.dumps(capability_spec, indent=2, sort_keys=True) if capability_spec else '(legacy free-text demand)',
                      reason or '(no reason recorded — use the atomic specification and examples)',
                      '\n\n'.join(card_sections) or '(none found)',
                      '\n\n'.join(code_sections) or '(no hits)',
                      kb_hits.strip() or '(kb unavailable)', test_tmpl))
