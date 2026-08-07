#!/usr/bin/env python3
"""map-pipeline stage C: apply SEARCH/REPLACE edit blocks from model output.

Reads model output on stdin. Exit codes: 0 applied, 4 park verdict (prints
verdict line), 5 malformed/no blocks, 6 search text not found or ambiguous
(prints details for the retry prompt).
"""
import re, sys, os

out = sys.stdin.read()
mv = re.search(r'^VERDICT:\s*([A-Z_]+)', out, re.M)
blocks = re.findall(r'<<<FILE (.+?)\n<<<SEARCH\n(.*?)\n===REPLACE\n(.*?)\n>>>END',
                    out, re.S)
if mv and not blocks:
    print(mv.group(0))
    rm = re.search(r'^REASON:.*$', out, re.M)
    if rm:
        print(rm.group(0))
    sys.exit(4)
if not blocks:
    print('no edit blocks and no verdict found in model output')
    sys.exit(5)

errors = []
staged = []
for path, search, replace in blocks:
    path = path.strip()
    if path.startswith('backend/game/'):
        errors.append('%s: backend/game/ is off-limits (auto-park rule)' % path)
        continue
    if not os.path.exists(path):
        errors.append('%s: file does not exist' % path)
        continue
    src = open(path, encoding='utf-8').read()
    n = src.count(search)
    if n == 0:
        errors.append('%s: SEARCH text not found (must be copied verbatim, no line numbers)' % path)
    elif n > 1:
        errors.append('%s: SEARCH text ambiguous (%d matches) — include more context lines' % (path, n))
    else:
        staged.append((path, search, replace))

if errors:
    print('\n'.join(errors))
    sys.exit(6)
for path, search, replace in staged:
    src = open(path, encoding='utf-8').read()
    open(path, 'w', encoding='utf-8').write(src.replace(search, replace, 1))
    print('applied: %s' % path)
sys.exit(0)
