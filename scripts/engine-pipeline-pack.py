#!/usr/bin/env python3
"""engine-pipeline stage A: context pack for ONE primitive demand.

Input: a blocked ticket carrying missing_prim (park from a map worker or the
map-pipeline). Gathers the demand reason, the blocked example cards, the
executor code regions the primitive name/reason point at, a worked example
(similar existing primitive), and the wiring conventions — one focused
engine-patch call instead of an agentic session.

Usage: engine-pipeline-pack.py TICKET_ID [--repo PATH] [--db PATH]
   or: engine-pipeline-pack.py --ticket-spec PATH [--repo PATH]
"""
import argparse, json, glob, os, re, sqlite3, sys, urllib.request, urllib.parse
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('ticket', type=int, nargs='?', help='legacy dispatcher ticket id')
ap.add_argument('--ticket-spec', type=Path, help='Factory NG TicketSpec JSON')
ap.add_argument('--capability', type=int, default=0)
ap.add_argument('--repo', default='/opt/development/test/openmagic')
ap.add_argument('--db', default='/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db')
ap.add_argument('--kb', default='http://127.0.0.1:4103')
ap.add_argument('--no-tools', action='store_true',
                help='emit a self-contained packet for a no-tools completion adapter')
a = ap.parse_args()

if bool(a.ticket) == bool(a.ticket_spec):
    ap.error('provide exactly one dispatcher ticket id or --ticket-spec')

capability_spec = None
spec = None
if a.ticket_spec:
    spec = json.loads(a.ticket_spec.read_text())
    if spec.get('schema') != 'factory.ticket-spec/v1' or spec.get('work_type') != 'engine':
        sys.exit('--ticket-spec must be an Engine factory.ticket-spec/v1')
    ticket_label = spec['id']
    title = spec['title']
    descr = ''
    prim = spec['id'].split('/')[-2].split('.')[-1].replace('-', '_')
    capability_spec = dict(spec.get('capability') or {})
    if not capability_spec:
        capability_spec = {
            'required_behavior': '\n'.join(spec.get('required_behavior', [])),
            'source_misses': [],
            'negative_examples': [],
        }
    capability_spec['allowed_paths'] = spec.get('scope', {}).get('allowed_paths', [])
    capability_spec['evidence'] = spec.get('evidence', [])
else:
    c = sqlite3.connect(a.db)
    row = c.execute('select title, descr, missing_prim from tickets where id=?', (a.ticket,)).fetchone()
    if not row:
        sys.exit('no such ticket %d' % a.ticket)
    ticket_label = '#%d' % a.ticket
    title, descr, prim = row
    prim = (prim or '').strip()
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

# Code regions: resolve any executor/handler function NAMED in the capability
# text against the LIVE source first. TicketSpec evidence anchors and the
# token-scored fallback below are frequently wrong (a keyword match landing in
# a file header/import comment, or a hardcoded default region) -- a function
# actually named in required_behavior/reason is unambiguous and a single grep
# away, so verify it against the current clone before trusting anything else.
def _resolve_named_function(repo_root, identifier):
    pattern = re.compile(r'(?m)^func\s*(?:\([^)]*\)\s*)?' + re.escape(identifier) + r'\s*\(')
    for rel_dir in ('backend/game', 'backend/cards'):
        for f in sorted(glob.glob(os.path.join(repo_root, rel_dir, '*.go'))):
            if f.endswith('_test.go'):
                continue
            try:
                text = Path(f).read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            m = pattern.search(text)
            if not m:
                continue
            file_lines = text.splitlines()
            func_line = text.count('\n', 0, m.start())
            start = func_line
            while start > 0 and file_lines[start - 1].lstrip().startswith('//'):
                start -= 1
            end = func_line + 1
            while end < len(file_lines) and not file_lines[end].startswith('func '):
                end += 1
            end = min(end, func_line + 150)
            return os.path.relpath(f, repo_root), start, end
    return None

text_pool = reason
if capability_spec:
    text_pool += ' ' + str(capability_spec.get('required_behavior', ''))
named_idents = re.findall(r'\b(execute[A-Z]\w+|handle[A-Z]\w+|apply[A-Z]\w+|resolve[A-Z]\w+)\b', text_pool)
named_idents += re.findall(r'`([A-Za-z_][A-Za-z0-9_.]{4,})`', text_pool)
named_idents = list(dict.fromkeys(named_idents))[:6]

code_sections, budget = [], 420
for ident in named_idents:
    if budget <= 0:
        break
    hit = _resolve_named_function(a.repo, ident)
    if not hit:
        continue
    rel_path, start, end = hit
    file_lines = Path(os.path.join(a.repo, rel_path)).read_text(encoding='utf-8', errors='replace').splitlines()
    take = min(end - start, budget)
    if take <= 0:
        continue
    code_sections.append('### %s:%d-%d (verified: named function %s)\n%s' % (
        rel_path, start + 1, start + take, ident,
        '\n'.join('%5d %s' % (i + 1, file_lines[i]) for i in range(start, start + take))))
    budget -= take

# Code regions: an NG TicketSpec supplies verified anchors. Legacy tickets use
# the established demand-token search below.
if spec:
    for evidence in spec.get('evidence', []):
        path = evidence.get('path', '')
        if not path or not os.path.exists(path):
            continue
        lines = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
        for lo, hi in re.findall(r'(\d+)-(\d+)', evidence.get('anchor', '')):
            if budget <= 0:
                break
            start, end = max(0, int(lo) - 1), min(len(lines), int(hi))
            take = min(end - start, budget)
            if take <= 0:
                continue
            code_sections.append('### %s:%d-%d (TicketSpec evidence)\n%s' % (
                path, start + 1, start + take,
                '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(start, start + take))))
            budget -= take

# Code regions: tokens from the primitive name + identifiers from the reason.
tokens = [t for t in re.split(r'[_\-]', prim) if len(t) > 3]
tokens += re.findall(r'`([A-Za-z_][A-Za-z0-9_.]{4,})`', reason)[:6]
tokens = list(dict.fromkeys(tokens))[:8]
FILES = ['backend/game/ability_effects.go', 'backend/game/gamestate.go',
         'backend/game/events.go', 'backend/game/gamestate_tutor.go',
         'backend/game/targeting.go', 'backend/cards/converter.go',
         'backend/cards/registry.go', 'backend/cards/v2.go']
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
kb_queries = [(' '.join(tokens[:4]), None)]
if spec:
    # The TicketSpec facts are where the producer records the exact seam it
    # already proved. Query those symbols individually: a slug such as
    # "pt-switch-layer" is useful for primitive discovery but is too vague to
    # retrieve GetPowerWithEffects from the function index.
    symbols = []
    for evidence in spec.get('evidence', []):
        symbols.extend(re.findall(r'\b[A-Z][A-Za-z0-9_]{3,}\b', evidence.get('fact', '')))
    for symbol in dict.fromkeys(symbols):
        kb_queries.append((symbol, 'engine'))

hits = []
for query_text, kind in kb_queries[:7]:
    try:
        query = urllib.parse.quote(query_text)
        suffix = '&kind=%s' % urllib.parse.quote(kind) if kind else ''
        hit = urllib.request.urlopen('%s/find?q=%s&n=2%s' % (a.kb, query, suffix), timeout=5).read().decode().strip()
        if hit and not hit.startswith('NO MATCH') and hit not in hits:
            hits.append(hit)
    except Exception:
        pass
kb_hits = '\n\n'.join(hits)

# Shape-test convention: show the head of a recent shape test as template.
test_tmpl = ''
for cand in ['backend/cards/shape_dealt_damage_test.go', 'backend/cards/shape_becomes_targeted_test.go']:
    if os.path.exists(cand):
        test_tmpl = '### %s (convention template, first 60 lines)\n%s' % (
            cand, '\n'.join(open(cand).read().splitlines()[:60]))
        break

tool_budget = '''## TOOL BUDGET
You may Read/Grep/Glob to verify exact lines (~10 tool calls budget). Plan
your reads, then STOP exploring and emit your answer — your FINAL message
MUST be the output format below. An imperfect block set beats running out of
turns in silence: the gate catches errors and you get one retry with the
failure detail.'''
if a.no_tools:
    tool_budget = '''## NO-TOOLS ADAPTER
No repository tools are available in this call. Use only the line-numbered
evidence in this packet. Do not issue a tool call. If essential exact source
is absent, use the bounded `NEED:` continuation defined below; otherwise
return an edit block or a verdict in this response.'''

print('''# ENGINE-PIPELINE TASK — build ONE small primitive, single-shot

Ticket %s: %s
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

%s

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
No other prose.''' % (ticket_label, title, prim, a.capability or ('TicketSpec' if spec else '(legacy)'),
                      json.dumps(capability_spec, indent=2, sort_keys=True) if capability_spec else '(legacy free-text demand)',
                      reason or '(no reason recorded — use the atomic specification and examples)',
                      '\n\n'.join(card_sections) or '(none found)',
                      '\n\n'.join(code_sections) or '(no hits)',
                      kb_hits.strip() or '(kb unavailable)', test_tmpl, tool_budget))
