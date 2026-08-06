#!/usr/bin/env python3
"""flip-frontier — how close review cards are to flipping (Dani 2026-08-06).
Re-parses every review-status carddb record and histograms remaining misses.
The 1-miss bucket is the frontier: those cards flip the moment their last
shape lands. Written to /tmp/orch/flip-frontier.json for the dispatcher
dashboard (merged into /pilestats). Cron: 17 */2 * * *  (~3 min compute).
"""
import collections
import glob
import json
import sys
import time

sys.path.insert(0, '/opt/development/magic-new/scripts/paragraph')
from reparse import reparse_card  # noqa: E402

hist = collections.Counter()
last_blocker = collections.Counter()
total = 0
for f in glob.glob('/opt/development/magic-new/backend/data/carddb/*.json'):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if not isinstance(d, dict):
        continue
    for name, rec in d.items():
        if not isinstance(rec, dict) or rec.get('status') != 'review':
            continue
        try:
            r = reparse_card(rec)
        except Exception:
            continue
        total += 1
        m = r.get('misses') or []
        if r['eligible']:
            hist[0] += 1
        else:
            hist[min(len(m), 3)] += 1
            if len(m) == 1:
                last_blocker[m[0][0]] += 1

out = {
    'frontier_ts': int(time.time()),
    'frontier_review': total,
    'frontier_eligible': hist[0],
    'frontier_1': hist[1],
    'frontier_2': hist[2],
    'frontier_3plus': hist[3],
}
# last-blocker ranking (Dani 2026-08-06): which shape is the LAST miss on
# the most cards — the highest-flip-yield priority signal.
for i, (k, v) in enumerate(last_blocker.most_common(5)):
    out['frontier_top%d' % (i + 1)] = v
    out['frontier_top%d_name' % (i + 1)] = k
with open('/tmp/orch/flip-frontier.json', 'w') as fh:
    json.dump(out, fh)
print(json.dumps(out))
