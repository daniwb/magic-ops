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
from factory_ng_context import render_regions, source_path, resolved_regions, requested_context
from factory_ng_knowledge import search as knowledge_search, discover_capability, describe, resolve_candidate
from factory_ng_symbols import render as render_symbol
from factory_ng_verification_context import verification_context

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
    production_key = spec.get('production',{}).get('key','')
    prim = production_key.split(':')[1] if production_key.startswith('capability:') else spec['id'].split('/')[-2].split('.')[-1].replace('-', '_')
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
    identifier = identifier.rsplit('.', 1)[-1]
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
if spec:
    text_pool += ' ' + ' '.join(item.get('fact', '') for item in spec.get('evidence', []))
named_idents = re.findall(r'\b(execute[A-Z]\w+|handle[A-Z]\w+|apply[A-Z]\w+|resolve[A-Z]\w+|Get[A-Z]\w+|Can[A-Z]\w+)\b', text_pool)
named_idents += re.findall(r'`([A-Za-z_][A-Za-z0-9_.]{4,})`', text_pool)
named_idents = list(dict.fromkeys(named_idents))[:6]

code_sections, budget = [], 420
# A named effect's actual dispatch outranks nearby comments and stale anchors.
# Use the same resolver as the runner's NEED continuation.
if spec:
    capability_key = spec.get('production', {}).get('key', '').split(':')
    exact_names = named_idents + (capability_key[1:2] if capability_key[:1] == ['capability'] else [])
    exact_names += re.findall(r'`([a-z][a-z0-9_]{3,})`', text_pool)
    detail = ' '.join(dict.fromkeys(exact_names))
    for relative in dict.fromkeys(e.get('path', '') for e in spec.get('evidence', [])):
        path = source_path(a.repo, relative)
        if not path or not detail or budget <= 180:
            continue
        section, used = resolved_regions(a.repo, relative, detail, min(140, budget - 180))
        if 'implementation unresolved' not in section:
            code_sections.append(section)
            budget -= used
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
    code_sections.append('### %s:%d-%d (verified: named function %s; bounded excerpt, request continuation if the body extends past this range)\n%s' % (
        rel_path, start + 1, start + take, ident,
        '\n'.join('%5d %s' % (i + 1, file_lines[i]) for i in range(start, start + take))))
    budget -= take

# Code regions: an NG TicketSpec supplies verified anchors. Legacy tickets use
# the established demand-token search below.
if spec:
    for evidence in spec.get('evidence', []):
        path = evidence.get('path', '')
        if not path or not os.path.exists(path) or budget <= 0:
            continue
        if evidence.get('symbol'):
            row = resolve_candidate(a.repo,evidence['symbol'],caller='engine-packet',budget=min(120,budget))
            if row['status']=='resolved':
                code_sections.append(render_symbol(row)); budget -= row['supplied_end']-row['start']+1
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
for _, f, lines, hits in (scored[:4] if not spec else []):
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

# Discover the contract's named parts as well as its generated capability label.
discovery = discover_capability({'key': prim, 'specification': capability_spec or {'required_behavior': reason}},
                                'engine-packet', limit=6, base=a.kb)
hits = [describe(lookup) + '\nDiscovery purpose: ' + lookup['discovery_role']
        for lookup in discovery['lookups']]
# Pinned source and named fixtures share the same bounded budget with search
# results. Never zero the pinned budget or refill it for incidental hits.
seen_symbols = set()
candidates = discovery['candidates'] + ([e['symbol'] for e in spec.get('evidence', []) if e.get('symbol')] if spec else [])
for candidate in candidates:
    if budget <= 0 or not candidate.get('symbol_id') or candidate['symbol_id'] in seen_symbols: continue
    seen_symbols.add(candidate['symbol_id'])
    row = resolve_candidate(a.repo, candidate, candidate.get('request_id', ''), 'engine-packet', min(120, budget))
    if row['status'] == 'resolved':
        code_sections.append(render_symbol(row)); budget -= row['supplied_end'] - row['start'] + 1
kb_hits = '\n\n'.join(hits)
if spec:
    verification = verification_context(a.repo, spec)
    if verification:
        code_sections.append(verification)
if spec and spec.get('execution', {}).get('context_requests'):
    code_sections.append(requested_context('\n'.join(
        'NEED: ' + request for request in spec['execution']['context_requests'][:3]), a.repo, spec))


# Shape-test convention: show the head of a recent shape test as template.
test_tmpl = ''
for cand in ['backend/cards/shape_dealt_damage_test.go', 'backend/cards/shape_becomes_targeted_test.go']:
    if os.path.exists(cand):
        test_tmpl = '### %s (convention template, first 60 lines)\n%s' % (
            cand, '\n'.join(open(cand).read().splitlines()[:60]))
        break

tool_budget = '''## TOOL BUDGET
Local read-only source tools are available in this isolated checkout. Use
targeted reads/searches to verify exact lines (~10 tool calls budget), including
missing or truncated declarations and test fixtures. Do not edit files, run
tests, use the network, commit, or integrate; the harness owns those actions.
Then emit the strict output format below in your FINAL message. If essential
evidence remains missing, return an honest bounded verdict.'''
if a.no_tools:
    tool_budget = '''## NO-TOOLS ADAPTER
No repository tools are available in this call. Use only the line-numbered
evidence in this packet. Do not issue a tool call. If essential exact source
is absent, use the bounded `NEED:` continuation defined below; otherwise
return an edit block or a verdict in this response.'''

print('''# ENGINE-PIPELINE TASK — satisfy ONE bounded behavior contract

Ticket %s: %s
Primitive demand: `%s`
Capability ID: `%s`
Atomic capability specification:
%s
Park reason:
%s

You are extending the Go MTG engine (repo openmagic, module magic-backend,
run from backend/). First distinguish existing behavior from the specific remaining gap. A generated
capability name is a search label, not an instruction to add a new primitive.
Decompose the requirement into existing operations, connections, and missing
behavior. Operation-only search hits are candidates, not proof of full support.
Use the public converter/cast/trigger/resolution path for the discriminating
test; a private-helper test alone can miss lost fields or later defaults.
If existing code satisfies the entire contract, a discriminating test-only
patch is valid. Otherwise change only the demonstrated gap. Missing evidence
requires NEED, not an invented framework. Choose classification reuse, connection, engine_gap, or insufficient_evidence.
Include one short assessment line (example):
CAPABILITY_ASSESSMENT: {"classification":"connection","existing_symbols":["qualified symbol"],"remaining_gap":"specific behavior or none","verification":"public-path test or missing evidence"}
Then deliver the normal edit blocks or verdict. This adds no model round.
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
