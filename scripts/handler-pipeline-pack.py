#!/usr/bin/env python3
"""handler-pipeline stage A: context pack for ONE card-handler ticket.

The handler tier is the most stereotyped work in the factory: one card, one
new cardfns file + behavior test, conventions fixed. The pack delivers the
card, the two nearest existing handlers as templates (knowledge service
/similar), and helper hits — the model call builds the pair in one go.

Usage: handler-pipeline-pack.py TICKET_ID [--repo PATH] [--db PATH]
"""
import argparse, json, glob, os, re, sqlite3, sys, urllib.request, urllib.parse

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
m = re.match(r'REPARSE-HANDLER: \[[^\]]*\] (.+?)(?:\s+—.*)?$', title)
if not m:
    sys.exit(3)
card_name = m.group(1).strip()

os.chdir(a.repo)
rec = None
for f in glob.glob('backend/data/carddb/*.json'):
    if f.endswith(('_handlers.json', '_unresolved.json')):
        continue
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if card_name in d:
        rec = d[card_name]
        break
if rec is None:
    sys.exit('card %r not in carddb' % card_name)
oracle = rec.get('text', '')

def kb(path, **params):
    try:
        q = urllib.parse.urlencode(params)
        return urllib.request.urlopen('%s%s?%s' % (a.kb, path, q), timeout=8).read().decode()
    except Exception:
        return ''

similar = kb('/similar', text=oracle, n=2)
# Full body of the single nearest handler as the primary template.
tmpl = ''
mm = re.search(r'=== .*?\((backend/cardfns/[^)]+\.go)\)', similar)
if mm and os.path.exists(mm.group(1)):
    body = open(mm.group(1), encoding='utf-8', errors='replace').read()
    tmpl = '### PRIMARY TEMPLATE %s (full file)\n%s' % (mm.group(1), body[:9000])
    tfile = mm.group(1)[:-3] + '_test.go'
    if os.path.exists(tfile):
        tmpl += '\n### ITS TEST %s (full file)\n%s' % (tfile, open(tfile).read()[:7000])

finds = kb('/find', q=oracle, n=5)

fn_name = re.sub(r'[^A-Za-z0-9]', '', card_name)
print('''# HANDLER-PIPELINE TASK — build ONE per-card handler + behavior test

Ticket #%d: %s
Card: %s
Oracle text:
%s

You are writing a per-card handler for the Go MTG engine (repo openmagic,
module magic-backend). Conventions:
- New file backend/cardfns/%s.go, package cardfns, one exported func
  %s(gs *game.GameState, self *game.Card) following the template below.
- New behavior test backend/cardfns/%s_test.go (a NEW +func Test... is
  REQUIRED — the gate greps the diff). Test real behavior via game.NewGame /
  NewTestScenario patterns from the template's test.
- backend/game/ is OFF-LIMITS (auto-park). Use existing primitives/helpers
  (lib_*.go) — the knowledge hits below list candidates.
- Register/wire NOTHING else: name-keyed handlers are picked up by
  RegisterCardAbilities via the cardfns registry convention shown in the
  template (mirror exactly what the template does).
- If a needed capability has no primitive/helper (check the hits below),
  park with a precise kebab-case primitive name.

## TOOL BUDGET
You may Read/Grep/Glob to verify symbols (~10 calls). Then STOP and emit —
your FINAL message MUST be the output format. Imperfect blocks beat silence:
the gate catches errors and you get one retry with the failure detail.

%s

## Knowledge-service hits (primitives/helpers)
%s

## OUTPUT FORMAT (strict)
EITHER:
VERDICT: NEEDS_PRIMITIVE|AMBIGUOUS
REASON: <one line; NEEDS_PRIMITIVE = kebab-case name + one-paragraph proposal>

OR file blocks:
<<<NEWFILE backend/cardfns/%s.go
full file content
>>>END
<<<NEWFILE backend/cardfns/%s_test.go
full file content
>>>END
(Existing-file edits, if truly needed, via <<<FILE/<<<SEARCH/===REPLACE/>>>END —
but a clean handler normally needs NO existing-file edits.)

End with one line:
EXPECT: <one sentence: the behavior now implemented>
No other prose.''' % (a.ticket, title, card_name, oracle,
                      fn_name, fn_name, fn_name,
                      tmpl or '(no similar handler found — follow standard cardfns conventions)',
                      finds.strip() or '(kb unavailable)',
                      fn_name, fn_name))
