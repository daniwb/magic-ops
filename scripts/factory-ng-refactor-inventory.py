#!/usr/bin/env python3
"""Read-only Map/Engine inventory; emits evidence, never patches or tickets."""
import argparse, hashlib, json, pathlib, re

OPS = pathlib.Path('/opt/development/magic-ops')

def sha(p): return 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()


def go_block(body, start):
    """Return the brace-delimited Go block beginning at/after start.

    This deliberately keeps Inventory v0 deterministic and conservative.  It
    skips quoted strings and comments so a brace in a diagnostic literal cannot
    turn two unrelated switches into one alleged duplicate-dispatch finding.
    """
    opening = body.find('{', start)
    if opening < 0:
        return None
    depth, i, mode = 0, opening, None
    while i < len(body):
        ch, nxt = body[i], body[i + 1:i + 2]
        if mode == 'line_comment':
            if ch == '\n': mode = None
        elif mode == 'block_comment':
            if ch == '*' and nxt == '/': mode, i = None, i + 1
        elif mode in ('"', '`'):
            if ch == '\\' and mode == '"': i += 1
            elif ch == mode: mode = None
        elif ch == '/' and nxt == '/': mode, i = 'line_comment', i + 1
        elif ch == '/' and nxt == '*': mode, i = 'block_comment', i + 1
        elif ch in ('"', '`'): mode = ch
        elif ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return opening, i + 1
        i += 1
    return None


def direct_case_labels(body, block):
    """Case labels directly owned by one switch, not by nested switches."""
    opening, closing = block
    labels, depth, i, mode = [], 0, opening + 1, None
    while i < closing - 1:
        ch, nxt = body[i], body[i + 1:i + 2]
        if mode == 'line_comment':
            if ch == '\n': mode = None
        elif mode == 'block_comment':
            if ch == '*' and nxt == '/': mode, i = None, i + 1
        elif mode in ('"', '`'):
            if ch == '\\' and mode == '"': i += 1
            elif ch == mode: mode = None
        elif ch == '/' and nxt == '/': mode, i = 'line_comment', i + 1
        elif ch == '/' and nxt == '*': mode, i = 'block_comment', i + 1
        elif ch in ('"', '`'): mode = ch
        elif ch == '{': depth += 1
        elif ch == '}': depth -= 1
        elif depth == 0:
            match = re.match(r'case\s+"([^"]+)"\s*:', body[i:])
            if match:
                labels.append(match.group(1)); i += match.end() - 1
        i += 1
    return labels


def named_function_block(body, name):
    match = re.search(r'^func\s+' + re.escape(name) + r'\s*\(', body, re.M)
    return go_block(body, match.end()) if match else None


def first_switch_block(body, within):
    start, end = within
    match = re.search(r'\bswitch\b', body[start:end])
    return go_block(body, start + match.start()) if match else None
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source', type=pathlib.Path, default=pathlib.Path('/opt/development/test/openmagic'))
    ap.add_argument('--output', type=pathlib.Path, required=True)
    a=ap.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    files=[a.source/'scripts/paragraph/reparse.py', a.source/'backend/cards/converter.go']
    for p in files:
        if not p.is_file(): raise SystemExit('missing source: '+str(p))
    text={str(p.relative_to(a.source)):p.read_text() for p in files}
    symbols=[]
    for path, body in text.items():
        pattern=r'^def\s+(\w+)' if path.endswith('.py') else r'^func\s+(?:\([^)]*\)\s*)?(\w+)'
        symbols += [{'path':path,'symbol':m.group(1),'line':body[:m.start()].count('\n')+1} for m in re.finditer(pattern,body,re.M)]
    converter = text['backend/cards/converter.go']
    switch_blocks=[]
    for match in re.finditer(r'\bswitch\b', converter):
        block = go_block(converter, match.start())
        if block:
            switch_blocks.append(block)
    cases=[]
    repeated_by_switch=[]
    for block in switch_blocks:
        labels=direct_case_labels(converter, block); cases.extend(labels)
        repeats=sorted({label for label in labels if labels.count(label)>1})
        if repeats:
            repeated_by_switch.append({'line': converter[:block[0]].count('\n') + 1, 'labels': repeats})
    proposals=[]
    if repeated_by_switch:
        proposals.append({'id':'refactor:converter-duplicate-case-audit','rank':1,'confidence':'review-required','evidence':{'duplicate_case_labels_by_switch':repeated_by_switch,'source':'backend/cards/converter.go'},'risk':'semantic dispatch overlap','benefit':'remove ambiguous duplicate dispatch only after behavior snapshots','suggested_child_ticket':{'class':'refactor','scope':['backend/cards/converter.go'],'acceptance':['freeze affected DSL conversion snapshots','add discriminating regression test','prove no residual duplicate case labels in the identified switch']}})
    keyword_function=named_function_block(converter, 'applyKeywordCost')
    keyword_switch=first_switch_block(converter, keyword_function) if keyword_function else None
    keyword_cases=direct_case_labels(converter, keyword_switch) if keyword_switch else []
    if keyword_switch and keyword_cases:
        proposals.append({'id':'refactor:keyword-cost-switch-extraction-assessment','rank':len(proposals)+1,'confidence':'review-required','evidence':{'function':'applyKeywordCost','switch_line':converter[:keyword_switch[0]].count('\n')+1,'case_count':len(keyword_cases),'source':'backend/cards/converter.go'},'risk':'keyword-cost semantics','benefit':'only consider splitting into small tested handlers','suggested_child_ticket':{'class':'refactor','scope':['backend/cards/converter.go'],'acceptance':['freeze representative keyword-cost snapshots','no behavior change','scope remeasurement']}})
    index={'schema':'factory.refactor-inventory/v0','source_root':str(a.source),'inputs':[{'path':str(p.relative_to(a.source)),'sha256':sha(p)} for p in files],'symbols':symbols,'converter_case_count':len(cases)}
    (a.output/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    (a.output/'proposals.json').write_text(json.dumps(proposals,indent=2)+'\n')
    (a.output/'report.md').write_text('# Refactor Inventory v0\n\nRead-only evidence; proposals are not tickets or patches.\n\n'+'\n'.join('* '+p['id'] for p in proposals)+'\n')
    # A manifest cannot truthfully hash itself.  Excluding its prior output
    # also makes a rerun byte-reproducible instead of carrying a stale hash.
    manifest={p.name:sha(p) for p in sorted(a.output.iterdir()) if p.is_file() and p.name != 'manifest.json'}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
if __name__=='__main__': main()
