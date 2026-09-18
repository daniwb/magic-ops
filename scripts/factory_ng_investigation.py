"""A single read-only evidence investigation after a staged evidence failure."""
import hashlib
import json
import re
from factory_ng_context import source_path

STAGED = 'claude-staged@1.0.0'
AGENTIC = 'claude-agentic@1.0.0'
AGENTIC_PROFILES = {AGENTIC, 'claude-agentic-test@1.0.0'}

EVIDENCE_INSTRUCTIONS = '''
If essential source or API evidence is missing, request up to three specific
NEED: source-path-or-symbol
lines. The harness can resolve those once. If evidence is still insufficient,
return no patch and emit:
EVIDENCE_GAP: {"question":"the specific unanswered code/API question","searched":["specific source or symbol already examined"]}
Use this only for missing source/API evidence. Coding mistakes, failed tests,
new Engine primitives, framework-sized work, and integration conflicts are not
evidence gaps. An AMBIGUOUS verdict alone does not authorize exploration.
'''


def evidence_gap(model, profile, attempted=False):
    """Only an explicit evidence failure can spend an agentic investigation."""
    if profile != STAGED or attempted or model.get('exit_code') != 0:
        return None
    reply = model.get('stdout', '')
    if re.search(r'<<<(?:FILE|NEWFILE)|VERDICT:\s*(?:FRAMEWORK|NEEDS_PRIMITIVE|SEMANTIC_GAP)', reply):
        return None
    match = re.search(r'^EVIDENCE_GAP:\s*(\{[^\n]*\})\s*$', reply, re.M)
    if match:
        try:
            gap = json.loads(match[1])
        except ValueError:
            return None
        if (isinstance(gap, dict) and isinstance(gap.get('question'), str) and gap['question'].strip()
                and isinstance(gap.get('searched'), list) and 1 <= len(gap['searched']) <= 8
                and all(isinstance(s, str) and s.strip() for s in gap['searched'])):
            return {'question': gap['question'][:1500], 'searched': [s[:300] for s in gap['searched'][:8]]}
    requests = re.findall(r'^NEED:\s*(.+?)\s*$', reply, re.M)
    if requests:
        # Called only after the normal deterministic NEED pass has been tried.
        return {'question': 'Locate the missing source needed for: ' + '; '.join(requests[:3])[:1500],
                'searched': requests[:3]}
    return None


def investigation_prompt(ticket, gap):
    return ('Investigate this one staged evidence failure. Do not implement the ticket, '
            'propose patches, change requirements, or run tests. Locate exact APIs and a relevant '
            'existing test/example. Use at most six source ranges (120 lines each, 480 total). '
            'If the evidence cannot be found, return EVIDENCE_UNRESOLVED with the reason.\n'
            'Return exactly one line in this format:\n'
            'EVIDENCE_JSON: {"sources":[{"path":"backend/game/example.go","start_line":1,"end_line":20}],'
            '"summary":"brief finding"}\n\n'
            'Ticket: ' + ticket['id'] + '\n'
            'Required behavior:\n' + '\n'.join(ticket.get('required_behavior', [])) + '\n'
            'Evidence failure:\n' + json.dumps(gap, sort_keys=True) + '\n')


def validate_evidence(reply, repo):
    """Forward source read by the harness, never investigator-authored patches."""
    if len(reply) > 12000 or '<<<' in reply:
        raise ValueError('investigation must return bounded source references, not a patch')
    match = re.fullmatch(r'\s*EVIDENCE_JSON:\s*(\{[^\n]*\})\s*', reply)
    if not match:
        raise ValueError('investigation returned no structured evidence')
    value = json.loads(match[1])
    sources = value.get('sources') if isinstance(value, dict) else None
    if not isinstance(sources, list) or not 1 <= len(sources) <= 6:
        raise ValueError('investigation requires one to six source ranges')
    sections, anchors, total = [], [], 0
    for item in sources:
        if not isinstance(item, dict):
            raise ValueError('invalid source reference')
        relative, lo, hi = item.get('path'), item.get('start_line'), item.get('end_line')
        path = source_path(repo, relative) if isinstance(relative, str) else None
        if not path or type(lo) is not int or type(hi) is not int or not 1 <= lo <= hi or hi - lo >= 120:
            raise ValueError('invalid or out-of-scope source range')
        lines = path.read_text().splitlines()
        total += hi - lo + 1
        if hi > len(lines) or total > 480:
            raise ValueError('source range exceeds file or evidence budget')
        anchors.append({'path': relative, 'start_line': lo, 'end_line': hi,
                        'sha256': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()})
        sections.append('### %s:%d-%d\n%s' % (relative, lo, hi,
                        '\n'.join('%5d %s' % (n + 1, lines[n]) for n in range(lo - 1, hi))))
    evidence = '\n\n'.join(sections)
    if len(evidence) > 32000:
        raise ValueError('source evidence exceeds character budget')
    return evidence, anchors
