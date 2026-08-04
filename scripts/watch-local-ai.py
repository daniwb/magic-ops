#!/usr/bin/env python3
"""watch-local-ai.py [worker] [-n N] [-f] — the local AI worker's actual
conversation (claude CLI transcript). Default: rl1, last 120 raw lines.
-n N shows the last N transcript lines, -f follows live."""
import glob, json, os, sys, time

w = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else 'rl1'
follow = '-f' in sys.argv
n = 120
if '-n' in sys.argv:
    try:
        n = int(sys.argv[sys.argv.index('-n') + 1])
    except Exception:
        pass
d = os.path.expanduser('~/.claude/projects/-tmp-work-disp-' + w)
files = sorted(glob.glob(d + '/*.jsonl'), key=os.path.getmtime)
if not files:
    sys.exit('no transcript for %s (%s)' % (w, d))
f = files[-1]
print('== transcript:', f)

def render(line):
    try:
        dd = json.loads(line)
    except Exception:
        return
    m = dd.get('message') or {}
    role = m.get('role') or dd.get('type', '?')
    c = m.get('content')
    if isinstance(c, list):
        for b in c:
            t = b.get('type')
            if t == 'text':
                print('[%s] %s' % (role, b.get('text', '')[:300]))
            elif t == 'tool_use':
                print('[%s>TOOL %s] %s' % (role, b.get('name'), json.dumps(b.get('input', {}))[:200]))
            elif t == 'tool_result':
                rc = b.get('content')
                if isinstance(rc, list):
                    rc = ' '.join(x.get('text', '') for x in rc if isinstance(x, dict))
                print('[tool<] %s' % str(rc)[:200])
    elif isinstance(c, str):
        print('[%s] %s' % (role, c[:300]))

with open(f) as fh:
    lines = fh.readlines()
for line in lines[-n:]:
    render(line)
if follow:
    with open(f) as fh:
        fh.seek(0, 2)
        while True:
            line = fh.readline()
            if line:
                render(line)
            else:
                time.sleep(1)
