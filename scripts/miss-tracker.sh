#!/bin/bash
# miss-tracker.sh — hourly corpus KPI snapshot (2026-08-09, Dani-approved
# "measure misses not tickets"). Appends one JSON line to
# state/miss-history.jsonl: review-pile size + total-misses from a full
# reparse.py scan (~23s). Dashboard /stats and the hourly digest read this.
set -u
OM=/opt/development/test/openmagic
OPS=/opt/development/magic-ops
HIST="$OPS/state/miss-history.jsonl"
mkdir -p "$OPS/state"
out=$(cd "$OM" && timeout 300 python3 scripts/paragraph/reparse.py 2>/dev/null | head -5)
total=$(printf '%s' "$out" | command grep -oP 'total-misses: \K\d+' | head -1)
cards=$(printf '%s' "$out" | command grep -oP 'review-pile cards scanned: \K\d+' | head -1)
[ -z "${total:-}" ] && exit 0   # scan failed (e.g. mid-rebase checkout) — skip beat
printf '{"ts":%d,"total":%s,"cards":%s}\n' "$(date +%s)" "$total" "$cards" >> "$HIST"

# Re-rank map todo tickets by expected miss-unlock (title's "(N misses").
# Priority 10..55 — circle-requeues (60) still outrank. Idempotent, hourly,
# survives gen_fleet_tasks regenerations (Dani 2026-08-09: Sonnet budget goes
# to the biggest unlocks first).
python3 - <<'PYEOF' 2>/dev/null
import sqlite3, re
db = sqlite3.connect('/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db')
c = db.cursor()
for tid, title in c.execute("select id,title from tickets where state='todo' and title like 'REPARSE-MAP%'").fetchall():
    m = re.search(r'(\d+)\s+miss', title) or re.search(r'\((\d+)\s+cards', title)
    n = int(m.group(1)) if m else 10
    c.execute("update tickets set priority=? where id=? and priority between 0 and 55",
              (max(10, min(55, 10 + n//4)), tid))
db.commit()
PYEOF
