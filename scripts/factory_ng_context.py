"""Bounded, source-aware evidence for Factory NG's prepared adapters."""
import re
from pathlib import Path

SOURCE_ROOTS = ('backend/game/', 'backend/cards/', 'backend/cardfns/', 'scripts/paragraph/')
STOP = set('the this that with from into full body function definition definitions '
           'struct case switch exact current actual source code implementation '
           'containing equivalent fields field declaration file lines and any'.split())
GO_TOKEN = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|`[^`]*`|\'(?:\\.|[^\'\\])*\'', re.S)


def masked(text, strings=False):
    def replace(match):
        token = match.group()
        if strings or token.startswith(('//', '/*')):
            return ''.join('\n' if c == '\n' else ' ' for c in token)
        return token
    return GO_TOKEN.sub(replace, text)


def source_path(repo, relative):
    """Context reads are source-only; edit authorization remains in TicketSpec."""
    if not relative.startswith(SOURCE_ROOTS) or Path(relative).suffix not in ('.go', '.py'):
        return None
    if '..' in Path(relative).parts:
        return None
    root = Path(repo).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def region_end(lines, start):
    """Find a declaration/branch boundary without counting braces in strings."""
    clean = masked('\n'.join(lines), strings=True).splitlines()
    if re.match(r'\s*(case\b|default:)', lines[start]):
        indent = len(lines[start]) - len(lines[start].lstrip())
        for i in range(start + 1, len(lines)):
            if clean[i].strip() and len(clean[i]) - len(clean[i].lstrip()) <= indent:
                if re.match(r'\s*(case\b|default:|})', clean[i]):
                    return i
        return len(lines)
    depth, opened = 0, False
    for i in range(start, len(clean)):
        for char in clean[i]:
            if char == '{':
                opened = True
                depth += 1
            elif char == '}':
                depth -= 1
                if opened and depth == 0:
                    return i + 1
        if i == start and not opened:
            return start + 1
    return len(lines)


def select_regions(text, detail, limit=3):
    """Prefer real dispatch/declarations over comments and incidental uses."""
    lines = text.splitlines()
    code = masked(text).splitlines()
    explicit = re.fullmatch(r'(?:lines?\s+)?(\d+)\s*-\s*(\d+)', detail.strip())
    if explicit:
        lo, hi = int(explicit[1]) - 1, int(explicit[2])
        return [(max(0, lo), min(len(lines), hi))] if 0 <= lo < hi <= len(lines) else []
    symbols = list(dict.fromkeys(s for s in re.findall(r'\b[A-Za-z_]\w{3,}\b', detail)
                                 if s.lower() not in STOP))
    candidates = []
    for order, symbol in enumerate(symbols):
        word = re.compile(r'\b' + re.escape(symbol) + r'\b')
        for i, line in enumerate(code):
            if not word.search(line):
                continue
            if re.match(r'\s*case\b', line) or re.search(r'\bif\b.*==\s*"' + re.escape(symbol) + r'"', line):
                rank = 0
            elif re.match(r'^\s*(?:func\s+(?:\([^)]*\)\s*)?|type\s+|def\s+|class\s+)' + re.escape(symbol) + r'\b', line):
                rank = 1
            else:
                rank = 2
            candidates.append((rank, order, i))
    regions = []
    for rank, _, start in sorted(candidates):
        if any(lo <= start < hi for lo, hi in regions):
            continue
        end = region_end(lines, start) if rank < 2 else min(len(lines), start + 35)
        regions.append((start, max(start + 1, end)))
        if len(regions) == limit:
            break
    return regions


def render_regions(relative, text, detail, budget=180):
    lines = text.splitlines()
    explicit = re.fullmatch(r'(?:lines?\s+)?\d+\s*-\s*\d+', detail.strip())
    if relative.endswith('.py') and not explicit:
        from factory_ng_python_context import select_python_regions
        regions = select_python_regions(text, detail)
    else:
        regions = select_regions(text, detail)
    if not regions:
        # An index exposes actual locations instead of passing a file header
        # off as the requested implementation. Keep original line numbers.
        declarations = [(i, line) for i, line in enumerate(masked(text).splitlines())
                        if re.match(r'^\s*(?:func |type |def |class |case )', line)]
        entries = declarations[:min(budget, 60)]
        return ('### %s (source index; requested implementation unresolved)\n%s' %
                (relative, '\n'.join('%5d %s' % (i + 1, lines[i]) for i, _ in entries))), len(entries)
    sections, used = [], 0
    for lo, hi in regions:
        if used >= budget:
            break
        end = min(hi, lo + budget - used, lo + 180)
        notice = '; truncated, remaining lines %d-%d' % (end + 1, hi) if end < hi else ''
        sections.append('### %s:%d-%d (source match%s)\n%s' % (
            relative, lo + 1, end, notice,
            '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(lo, end))))
        used += end - lo
    return '\n\n'.join(sections), used


def requested_context(reply, repo, ticket=None):
    sections, budget = [], 520
    for request in re.findall(r'^NEED:\s*(.+?)\s*$', reply, re.M)[:3]:
        if budget <= 0: break
        match = re.match(r'([\w./-]+\.(?:go|py))(.*)$', request)
        if not match:
            # A symbol-only NEED uses the same discovery and local resolver.
            from factory_ng_knowledge import search, resolve_candidate
            from factory_ng_symbols import render
            lookup = search(request,'need',limit=3)
            for candidate in lookup.get('candidates',[]):
                if budget <= 0: break
                if not candidate.get('symbol_id'): continue
                row = resolve_candidate(repo,candidate,lookup.get('request_id',''),'need',min(180,budget))
                if row['status'] == 'resolved':
                    sections.append(render(row)); budget -= row['supplied_end']-row['start']+1
            if not lookup.get('candidates'):
                from factory_ng_knowledge import describe
                sections.append(describe(lookup))
            continue
        relative, detail = match.groups()
        path = source_path(repo, relative)
        if path is None:
            continue
        detail = re.sub(r'^\s*[:–—-]?\s*', '', detail)
        section, used = resolved_regions(repo, relative, detail, min(200,budget))
        sections.append(section)
        budget -= used
        dependencies, used = type_context(repo, relative, detail + '\n' + section, min(100, budget))
        if dependencies:
            sections.append(dependencies)
            budget -= used
        if budget <= 0:
            break
    return '\n\n'.join(sections)


def resolved_regions(repo, relative, detail, budget=180):
    """Shared structural Go lookup; explicit line requests remain supported."""
    path = source_path(repo, relative)
    if path is None:
        return 'UNRESOLVED: source path unavailable', 0
    text = path.read_text()
    # A bare filename asks for that file. Small fixtures fit intact; replacing
    # them with a declaration index hid every assertion and public API call.
    if not detail.strip() and len(text.splitlines()) <= budget:
        return render_regions(relative, text, '1-%d' % len(text.splitlines()), budget)
    if relative.endswith('.go') and not re.fullmatch(r'(?:lines?\s+)?\d+\s*-\s*\d+',detail.strip()):
        from factory_ng_symbols import symbols, render
        from factory_ng_knowledge import resolve_candidate
        words = re.findall(r'\b[A-Za-z_]\w*\b',detail)
        rows = symbols(repo,[relative])
        matches = [r for r in rows if r['name'] in words]
        matches.sort(key=lambda r:(0 if r['kind']=='case' else 1,words.index(r['name'])))
        sections,used=[],0
        for candidate in matches[:3]:
            if used >= budget: break
            row=resolve_candidate(repo,candidate,caller='source-context',budget=budget-used)
            if row['status']=='resolved':
                sections.append(render(row)); used+=row['supplied_end']-row['start']+1
        if sections: return '\n\n'.join(sections),used
        if rows: detail=''  # Unknown identity: report an index, never an incidental occurrence.
    return render_regions(relative,text,detail,budget)


def type_context(repo, relative, evidence, budget=100):
    """Resolve at most three directly named types in the same Go package."""
    path=source_path(repo,relative)
    if not path or path.suffix != '.go' or budget <= 0: return '',0
    from factory_ng_symbols import symbols, render
    from factory_ng_knowledge import resolve_candidate
    names=set(re.findall(r'\b[A-Z]\w+\b',masked(evidence)))
    names-=set(re.findall(r'\btype\s+(\w+)\b',evidence))
    if not names: return '',0
    relatives=[str(p.relative_to(Path(repo).resolve())) for p in sorted(path.parent.glob('*.go'))
               if not p.name.endswith('_test.go')]
    rows=[r for r in symbols(repo,relatives) if r['kind']=='type' and r['name'] in names]
    sections,used=[],0
    for candidate in rows[:3]:
        if used>=budget: break
        row=resolve_candidate(repo,candidate,caller='source-types',budget=min(60,budget-used))
        if row['status']=='resolved':
            sections.append(render(row)); used+=row['supplied_end']-row['start']+1
    return '\n\n'.join(sections),used


def referenced_sources(repo, prose):
    """Resolve explicit source filenames in a requirement, without guessing."""
    result = set()
    for name in re.findall(r'(?<![\w/])(?:[\w.-]+/)*[\w.-]+\.(?:go|py)\b', prose):
        if '/' in name:
            # Go diagnostics and requirements often use module-relative
            # game/foo.go or cards/foo.go. Resolve only these known roots.
            relative = 'backend/' + name if name.startswith(('game/', 'cards/')) else name
            if source_path(repo, relative):
                result.add(relative)
        else:
            matches = [str(p.relative_to(repo)) for prefix in SOURCE_ROOTS
                       for p in (Path(repo) / prefix).glob(name) if source_path(repo, str(p.relative_to(repo)))]
            if len(matches) == 1:
                result.add(matches[0])
    return sorted(result)


def preparation_problems(ticket, repo):
    """Reject contradictory immutable instructions before spending model time."""
    allowed = set(ticket.get('scope', {}).get('allowed_paths', []))
    context_only = set(ticket.get('execution', {}).get('context_only_paths', []))
    prose = '\n'.join(ticket.get('required_behavior', []))
    prose += '\n' + ticket.get('capability', {}).get('required_behavior', '')
    problems = []
    for path in referenced_sources(repo, prose):
        if path not in allowed and path not in context_only:
            problems.append({'category': 'scope_contract', 'path': path,
                             'detail': 'Required behavior names source outside edit scope. A successor must authorize the edit or explicitly mark this reference context-only.'})
    # A producer-generated new test cannot reuse a declaration already present
    # in a different file. Never silently rename an immutable gate selector.
    from factory_ng_safety import named_test_pattern
    names = set()
    new_tests = set(re.findall(r'\bAdd\b[^.\n]*\btest\s+named\s+(Test\w+)', prose, re.I))
    for command in ticket.get('gates', []):
        pattern = named_test_pattern(command)
        if pattern and re.fullmatch(r'\^Test\w+\$', pattern):
            if pattern[1:-1] in new_tests:
                names.add(pattern[1:-1])
    if not names:
        return problems
    allowed_files = {Path(repo) / name for name in allowed}
    for directory in ('backend/game', 'backend/cards'):
        for path in sorted((Path(repo) / directory).glob('*_test.go')):
            if path in allowed_files:
                continue
            content = path.read_text()
            # A declaration cannot contain a name absent from the raw file.
            # Avoid masking thousands of unrelated test files on each ticket.
            if not any(name in content for name in names):
                continue
            relative = str(path.relative_to(repo))
            declarations = set(re.findall(r'^func\s+(Test\w+)\s*\(', masked(content), re.M))
            for name in sorted(names & declarations):
                problems.append({'category': 'test_symbol_collision', 'path': relative,
                                 'detail': 'Required test %s already exists outside the editable test files; issue a successor with an unambiguous test contract.' % name})
    return problems


def failure_detail(result, limit=6000):
    """Keep compiler/test diagnostics that precede noisy package-summary tails."""
    text = result.get('stdout', '') + '\n' + result.get('stderr', '')
    lines = []
    for line in text.splitlines():
        if line.startswith('{'):
            import json
            try:
                event = json.loads(line)
                line = event.get('Output', '') if isinstance(event, dict) else ''
            except ValueError:
                pass
        lines.extend(line.splitlines())
    important = [line for line in lines if re.search(r'\.go:\d+|\.py:\d+|--- FAIL|Error:|error:|panic:|required test filter', line)]
    evidence = '\n'.join(dict.fromkeys(important))
    return (evidence[:limit // 2] + '\n' + '\n'.join(lines)[-(limit // 2):]).strip()
