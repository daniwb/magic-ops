"""Bounded API evidence for the staged Qwen worker; no model tool authority."""
from pathlib import Path
import re
from factory_ng_context import source_path
from factory_ng_knowledge import search, resolve_candidate
from factory_ng_symbols import symbols, render

# API seams implicated by observed compile failures. Database candidates are
# re-resolved in the ticket checkout; registration types absent from the index
# can be found by the same structural parser in these bounded source files.
QUERIES = ('Zone', 'Player', 'Target', 'Primitive', 'regEffect', 'RemoveCard', 'AddCard', 'NewCard')
FILES = ('backend/game/zone.go', 'backend/game/player.go', 'backend/game/targeting.go',
         'backend/game/card.go', 'backend/cards/registry.go')
MAX_LINES = 480
MAX_CHARS = 32000


def api_evidence(repo):
    paths = [p for p in FILES if source_path(repo, p)]
    if not paths:
        return ''
    local = symbols(repo, paths)
    sections, seen, remaining = [], set(), MAX_LINES
    database_available = True
    for query in QUERIES:
        candidates = []
        if database_available:
            lookup = search(query, 'qwen-staged-api', limit=2)
            database_available = lookup.get('status') != 'service_error'
            candidates = lookup.get('candidates', [])
        # Filter same-named unrelated search hits and path traversal before
        # asking the structural resolver to inspect any file.
        candidates = [r for r in candidates if r.get('name') == query and r.get('symbol_id')
                      and r.get('path') in FILES and source_path(repo, r['path'])]
        candidates += [r for r in local if r['name'] == query]
        for candidate in candidates[:4]:
            identity = candidate['symbol_id']
            if identity in seen or remaining <= 0:
                continue
            seen.add(identity)
            row = resolve_candidate(repo, candidate, caller='qwen-staged-api', budget=min(100, remaining))
            if row['status'] != 'resolved':
                continue
            section = render(row)
            if sum(len(s) for s in sections) + len(section) > MAX_CHARS:
                continue
            sections.append(section)
            remaining -= row['supplied_end'] - row['start'] + 1
    if not sections:
        return ''
    return ('\n\n## HARNESS-VERIFIED API DECLARATIONS\n'
            'These declarations were read from this ticket checkout, not copied from the database. '
            'They supply types and calling conventions; they do not authorize edits outside scope. '
            'Use the exact declared types and signatures. Truncated excerpts are marked; '
            'request needed source rather than inventing missing fields.\n' + '\n\n'.join(sections))


def scope_inventory(repo, ticket):
    """Make file creation rules and required test declarations explicit."""
    from factory_ng_safety import named_test_pattern
    paths = ticket.get('scope', {}).get('allowed_paths', [])[:40]
    rows, tests = [], set()
    for relative in paths:
        path = source_path(repo, relative)
        if path:
            rows.append('EXISTS (SEARCH/REPLACE only): ' + relative)
            if relative.endswith('_test.go'):
                tests.update(re.findall(r'^func\s+(Test\w+)\s*\(', path.read_text(), re.M))
        else:
            # A missing file is not permission to edit outside ticket scope.
            rows.append('NOT READABLE OR ABSENT (verify before NEWFILE): ' + relative)
    for gate in ticket.get('gates', []):
        pattern = named_test_pattern(gate)
        if pattern and re.fullmatch(r'\^Test\w+\$', pattern):
            name = pattern[1:-1]
            rows.append('Required test ' + name + ': ' +
                        ('declared in allowed test files' if name in tests else
                         'NOT declared in allowed test files; supply this exact behavioral test, preserving the contract.'))
    return ('\n\n## CURRENT SCOPE FILES AND REQUIRED TEST DECLARATIONS\n' +
            '\n'.join(rows))[:12000]
