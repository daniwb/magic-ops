"""Bounded Python source selection by syntax, including single-quoted branches."""
import ast
import re


def select_python_regions(text, detail, limit=3):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    names = set(re.findall(r'\b[A-Za-z_]\w*\b', detail))
    quoted = set(re.findall(r"[`\"']([A-Za-z_]\w*)[`\"']", detail))
    important = (quoted or names) - {'value', 'event', 'subject', 'target', 'filter', 'controller', 'amount', 'to', 'from', 'kind'}
    assignment_names = important & (quoted | {name for name in names if '_' in name or name.isupper()})
    verb_request = re.search(r"verb\s*==\s*['\"]([a-z_]+)['\"]", detail)
    candidates = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names:
            # A request for a branch inside a huge function should select the
            # branch before consuming the budget on the function's header.
            candidates.append((1, node.lineno, node.end_lineno))
        if isinstance(node, ast.If):
            literals = {n.value for n in ast.walk(node.test) if isinstance(n, ast.Constant)
                        and isinstance(n.value, str)}
            if literals & names:
                priority = (0 if verb_request and verb_request[1] in literals else
                            2 if literals & important else 4)
                if priority == 0:
                    body_literals = {n.value for statement in node.body for n in ast.walk(statement)
                                     if isinstance(n, ast.Constant) and isinstance(n.value, str)}
                    priority -= len(body_literals & important)
                candidates.append((priority, node.lineno, node.body[-1].end_lineno))
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id in assignment_names for t in targets):
                candidates.append((1, max(1, node.lineno - 5), node.end_lineno + 15))
        # Miss labels and event/target keys often live in a call or a dict,
        # rather than an if condition. Return their actual construction.
        if isinstance(node, (ast.Call, ast.Dict)):
            literals = {n.value for n in ast.walk(node) if isinstance(n, ast.Constant)
                        and isinstance(n.value, str)}
            if literals & important:
                candidates.append((2 - min(.9, len(literals & important) / 10), max(1, node.lineno - 5), node.end_lineno + 5))
    regions = []
    for _, lo, hi in sorted(candidates):
        lo, hi = lo - 1, min(len(text.splitlines()), hi)
        if any(a <= lo and hi <= b for a, b in regions):
            continue
        if hi - lo > 180 and any(lo <= a and b <= hi for a, b in regions):
            continue
        regions.append((lo, hi))
        if len(regions) == limit:
            break
    return regions
