#!/usr/bin/env python3
"""map/engine-pipeline stage C: apply edit blocks from model output.

Reads model output on stdin. --allow-game permits backend/game/ edits
(engine tier). Supports SEARCH/REPLACE blocks and NEWFILE blocks.
Exit codes: 0 applied, 4 park verdict (prints verdict line), 5 malformed/no
blocks, 6 search text not found / ambiguous / path violation (prints details
for the retry prompt).
"""
import re, sys, os

ALLOW_GAME = '--allow-game' in sys.argv

out = sys.stdin.read()
mv = re.search(r'^VERDICT:\s*([A-Z_]+)', out, re.M)
blocks = re.findall(r'<<<FILE (.+?)\n<<<SEARCH\n(.*?)\n===REPLACE\n(.*?)\n>>>END',
                    out, re.S)
newfiles = re.findall(r'<<<NEWFILE (.+?)\n(.*?)\n>>>END', out, re.S)
# Alternate @@@ markers: llama-server's peg-native/harmony parser 500s on
# outputs containing <<< sequences (local gpt-oss lane, 2026-08-07), so
# local packs instruct @@@-style equivalents.
blocks += re.findall(r'@@@FILE (.+?)\n@@@SEARCH\n(.*?)\n@@@REPLACE\n(.*?)\n@@@END',
                     out, re.S)
newfiles += re.findall(r'@@@NEWFILE (.+?)\n(.*?)\n@@@END', out, re.S)
if mv and not blocks and not newfiles:
    print(mv.group(0))
    rm = re.search(r'^REASON:.*$', out, re.M)
    if rm:
        print(rm.group(0))
    sys.exit(4)
if not blocks and not newfiles:
    print('no edit blocks and no verdict found in model output')
    sys.exit(5)

errors = []
staged = []
for path, search, replace in blocks:
    path = path.strip()
    if path.startswith('backend/game/') and not ALLOW_GAME:
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

staged_new = []
for path, content in newfiles:
    path = path.strip()
    if path.startswith('backend/game/') and not ALLOW_GAME:
        errors.append('%s: backend/game/ is off-limits (auto-park rule)' % path)
    elif os.path.exists(path):
        errors.append('%s: NEWFILE but file already exists — use SEARCH/REPLACE' % path)
    elif '..' in path or path.startswith('/'):
        errors.append('%s: invalid path' % path)
    else:
        staged_new.append((path, content))

if errors:
    print('\n'.join(errors))
    sys.exit(6)
for path, search, replace in staged:
    src = open(path, encoding='utf-8').read()
    open(path, 'w', encoding='utf-8').write(src.replace(search, replace, 1))
    print('applied: %s' % path)
for path, content in staged_new:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    open(path, 'w', encoding='utf-8').write(content if content.endswith('\n') else content + '\n')
    print('created: %s' % path)
sys.exit(0)
