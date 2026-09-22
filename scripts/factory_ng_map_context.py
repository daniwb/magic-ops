"""Show the real parser handoff and current verb branches in prepared Map work."""
import ast
import copy
import sys
from pathlib import Path


def prepared_ticket_view(ticket):
    """Keep the contract and source identities; summarize historical search logs."""
    view = copy.deepcopy(ticket)
    for item in view.get('evidence', []):
        trace = item.pop('lookup_trace', None)
        if isinstance(trace, list):
            item['lookup_summary'] = {
                'historical_requests': len(trace),
                'recent': [{key: row[key] for key in ('query', 'status', 'strategy') if key in row}
                           for row in trace[-3:] if isinstance(row, dict)],
                'full_trace': 'retained in the canonical TicketSpec and observation artifacts'}
    return view


def trace_card(parser, card):
    original = parser.map_atom
    atom_module = getattr(parser, 'O', None)
    original_atom = getattr(atom_module, 'parse_atom', None)
    trigger_module = getattr(parser, 'T', None)
    original_trigger = getattr(trigger_module, 'slot_parse', None)
    parsed = []
    def traced_atom(*args, **kwargs):
        result = original_atom(*args, **kwargs)
        code = original_atom.__code__
        path = Path(code.co_filename)
        parsed.append({'clause': args[0] if args else kwargs.get('cl'),
                       'function': code.co_name, 'path': 'scripts/paragraph/' + path.name,
                       'verb': result[0]})
        del parsed[:-1]
        return result
    calls = []
    def traced_trigger(*args, **kwargs):
        previous_profile = sys.getprofile()
        returned = {}
        def profile(frame, event, value):
            if event == 'return' and frame.f_code is original_trigger.__code__:
                returned.update(line=frame.f_lineno, values={
                    key: copy.deepcopy(frame.f_locals[key]) for key in ('event', 'receiver', 'subject', 'spell')
                    if key in frame.f_locals})
            if previous_profile:
                previous_profile(frame, event, value)
        sys.setprofile(profile)
        try:
            result = original_trigger(*args, **kwargs)
        finally:
            sys.setprofile(previous_profile)
        if result[0] < 3 and len(calls) < 30:
            calls.append({'stage': 'trigger_spine', 'verb': None, 'args': None,
                          'clause': args[0] if args else None, 'result': copy.deepcopy(result),
                          'parser_values': returned.get('values', {}),
                          'caller_line': sys._getframe(1).f_lineno,
                          'atom_parser': {'function': original_trigger.__name__,
                                          'path': 'scripts/paragraph/' + Path(original_trigger.__code__.co_filename).name,
                                          'return_line': returned.get('line')}})
        return result
    def traced(*args, **kwargs):
        verb = args[0] if args else kwargs.get('verb')
        arguments = copy.deepcopy(args[1] if len(args) > 1 else kwargs.get('args'))
        result = original(*args, **kwargs)
        if len(calls) < 30:
            frame = sys._getframe(1)
            clause = next((frame.f_locals[key] for key in ('ch', 'clause', 'text')
                           if isinstance(frame.f_locals.get(key), str)), None)
            calls.append({'verb': verb, 'args': arguments, 'kind': kwargs.get('kind'),
                          'clause': clause, 'caller_line': frame.f_lineno,
                          'atom_parser': copy.deepcopy(parsed[-1]) if parsed and parsed[-1]['verb'] == verb else None,
                          'result': copy.deepcopy(result)})
        return result
    parser.map_atom = traced
    if original_atom:
        atom_module.parse_atom = traced_atom
    if original_trigger:
        trigger_module.slot_parse = traced_trigger
    try:
        result = parser.reparse_card(card)
    finally:
        parser.map_atom = original
        if original_atom:
            atom_module.parse_atom = original_atom
        if original_trigger:
            trigger_module.slot_parse = original_trigger
    return result, calls


def upstream_regions(repo, calls, budget=240):
    """For failed atom typing, show the parser and matching grammar rows."""
    from factory_ng_context import source_path
    sections, seen = [], set()
    def add(relative, lo, hi):
        nonlocal budget
        path = source_path(repo, relative)
        if not path or budget <= 0: return
        lines = path.read_text().splitlines()
        lo, hi = max(1, lo), min(len(lines), hi, lo + budget - 1)
        if (relative, lo, hi) in seen or hi < lo: return
        seen.add((relative, lo, hi))
        sections.append('### %s:%d-%d (actual upstream atom parser)\n%s' % (
            relative, lo, hi, '\n'.join('%5d %s' % (i, lines[i-1]) for i in range(lo, hi+1))))
        budget -= hi - lo + 1
    for call in calls:
        if call.get('args') is not None or not call.get('atom_parser'): continue
        atom = call['atom_parser']
        path = source_path(repo, atom['path'])
        if not path: continue
        tree = ast.parse(path.read_text())
        if atom.get('return_line'):
            add(atom['path'], atom['return_line'] - 35, atom['return_line'] + 10)
        # Grammar rows precede the general parse loop, which may be long.
        for node in ast.walk(tree):
            if (isinstance(call.get('verb'), str) and isinstance(node, ast.Tuple) and node.elts and isinstance(node.elts[0], ast.Constant)
                    and node.elts[0].value == call['verb']):
                add(atom['path'], node.lineno, node.end_lineno)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == atom['function']:
                add(atom['path'], node.lineno, min(node.end_lineno, node.lineno + 89))
        line = call.get('caller_line')
        if line: add('scripts/paragraph/reparse.py', line - 35, line + 10)
    return sections, budget


def map_regions(repo, calls, budget=340):
    """AST locations survive unrelated insertions in the 20k-line parser."""
    relative = 'scripts/paragraph/reparse.py'
    text = (Path(repo) / relative).read_text()
    tree = ast.parse(text)
    function = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'map_atom'), None)
    if function is None:
        return [], budget
    lines = text.splitlines()
    ranges = [(function.lineno, min(function.end_lineno, function.lineno + 19))]
    verbs = list(dict.fromkeys(c['verb'] for c in sorted(calls, key=lambda c: c['result'] is not None)
                              if isinstance(c.get('verb'), str)))
    for verb in verbs[:4]:
        if any(c.get('verb') == verb and c.get('args') is None for c in calls):
            # Raw-clause fallbacks run before map_atom. A missing argument
            # cannot be repaired by adding a branch below its None guard.
            helpers = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                       and n.name.startswith('_' + verb + '_')]
            for helper in helpers[:2]:
                ranges.append((helper.lineno, min(helper.end_lineno, helper.lineno + 99)))
        branches = [n for n in ast.walk(function) if isinstance(n, ast.If)
                    and any(isinstance(t, ast.Name) and t.id == 'verb' for t in ast.walk(n.test))
                    and any(isinstance(t, ast.Constant) and t.value == verb for t in ast.walk(n.test))]
        branches.sort(key=lambda n: n.lineno)
        for node in ([branches[0], branches[-1]] if len(branches) > 1 else branches):
            # An elif chain's end_lineno includes its later siblings. Its own
            # body is the bounded useful region, without unrelated branches.
            end = node.body[-1].end_lineno
            ranges.append((node.lineno, min(end, node.lineno + 139)))
    sections, seen = [], set()
    for lo, hi in ranges:
        if budget <= 0: break
        if (lo, hi) in seen: continue
        seen.add((lo, hi))
        hi = min(hi, lo + budget - 1)
        sections.append('### %s:%d-%d (current parser handoff/verb branch)\n%s' % (
            relative, lo, hi, '\n'.join('%5d %s' % (n + 1, lines[n]) for n in range(lo - 1, hi))))
        budget -= hi - lo + 1
    return sections, budget
