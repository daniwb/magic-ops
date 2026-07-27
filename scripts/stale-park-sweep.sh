#!/bin/bash
# Stale-park sweep: find parked/blocked card tickets whose claimed-missing
# primitive/shape NOW matches the current catalogs. Deterministic grep, no LLM,
# READ-ONLY — prints candidates + writes a dated report; requeueing stays a
# deliberate separate step (Sonnet/human precheck first; see
# reports/ollama-triage-summary-2026-07-27.md, funnel rule: grep flags,
# stronger judge confirms, nothing parks or un-parks purely mechanically).
# Standing use: runs after each vocab batch (hooked in dispatcher-vocab-batch.sh).
set -uo pipefail
OPS="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${REPO:-/opt/development/test/openmagic}"
DB="${DB:-/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db}"
REPORT="${REPORT:-$OPS/reports/stale-park-sweep-$(date +%Y-%m-%d-%H%M).md}"

python3 - "$REPO" "$DB" "$OPS" <<'PY' | tee "$REPORT"
import sqlite3, re, subprocess, sys
repo, dbpath, ops = sys.argv[1], sys.argv[2], sys.argv[3]
db = sqlite3.connect(f'file:{dbpath}?mode=ro', uri=True)
cat = subprocess.run(['python3', f'{ops}/scripts/concise-catalog.py',
    f'{repo}/scripts/skills/primitive-catalog.md'], capture_output=True, text=True).stdout
cat += open(f'{repo}/scripts/skills/shape-catalog.md').read()
cat = cat.lower(); catlines = cat.split('\n'); squash = cat.replace('_','').replace(' ','')
STOP={'the','a','an','of','to','with','and','or','this','that','by','for','on','in','cant','cannot'}
def probe(kebab):
    words=[w for w in re.split(r'[-_]', kebab.lower()) if w and w not in STOP]
    s=''.join(words)
    if s and s in squash: return f"exact-name: {s}"
    for ln in catlines:
        if words and all(w in ln for w in words): return f"all-words: {ln.strip()[:100]}"
    return None
rows = db.execute("select id,title,missing_prim,state from tickets "
                  "where missing_prim!='' and state in ('blocked','wait') order by id").fetchall()
from datetime import date
print(f"# Stale-park sweep — {date.today()}\n")
hits=0
for tid,title,prim,state in rows:
    r=probe(prim)
    if r:
        hits+=1
        print(f"- **#{tid}** [{state}] {title}\n  - claimed missing: `{prim}`\n  - catalog match: {r}")
print(f"\n{hits} candidate(s) of {len(rows)} parked tickets. Next: Sonnet/manual "
      f"precheck each claim against the FULL catalog entry, then requeue confirmed "
      f"ones (state='todo', retry_count=0, priority=1, + events row + LOCAL-TRIAGE note in descr).")
PY
