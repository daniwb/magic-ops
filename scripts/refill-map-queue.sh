#!/usr/bin/env bash
# refill-map-queue — keeps the dispatcher's REPARSE-MAP todo pool fed.
# r1 idled ~5h on 2026-08-06 because the queue drained at midnight and
# refill was manual. Regenerates fleet tasks from the CURRENT build plan
# (gen_fleet_tasks reads corpus/build-plan.jsonl, writes OUTSIDE the repo)
# and ingests when the pool is low. Planner reruns stay session-driven.
# Cron: */30. Log: /tmp/orch/refill.log
set -uo pipefail
REPO=/opt/development/test/openmagic
DB=/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db
LOG=/tmp/orch/refill.log
THRESH=${THRESH:-10}

log() { printf '[%s] %s\n' "$(date -Is)" "$*" >> "$LOG"; }

TODO=$(python3 - <<EOF
import sqlite3
c=sqlite3.connect('$DB')
print(list(c.execute("select count(*) from tickets where state='todo' and title like 'REPARSE-MAP%'"))[0][0])
EOF
)

# Stale-handler sweep (Dani 2026-08-07): handler tickets were classified at
# creation time; every flip wave since can make a queued card fully parse as
# a plain v2 record (status=auto, no parse_errors). Building a handler then
# REPLACES the clean record (hasHandler neutralizes record fields) and wastes
# a ~25min worker session. Close such tickets before workers claim them.
STALE=$(python3 - <<EOF
import sqlite3, re, json, glob
c = sqlite3.connect('$DB')
rows = list(c.execute("select id,title from tickets where state='todo' and title like 'REPARSE-HANDLER%'"))
cards = {}
for tid, title in rows:
    m = re.match(r'REPARSE-HANDLER: \[[^\]]*\] (.+)\$', title)
    if m: cards[m.group(1).strip()] = tid
closed = 0
for f in glob.glob('$REPO/backend/data/carddb/*.json'):
    if f.endswith(('_handlers.json', '_unresolved.json')): continue
    try: d = json.load(open(f))
    except Exception: continue
    for n in set(d) & set(cards):
        r = d[n]
        if r.get('status') == 'auto' and not r.get('parse_errors') and r.get('abilities'):
            cur = c.execute("update tickets set state='done' where id=? and state='todo'", (cards[n],))
            closed += max(cur.rowcount, 0)
print(closed)
c.commit()
EOF
)
[ "${STALE:-0}" -gt 0 ] && log "stale-handler sweep: closed $STALE ticket(s) whose card is already auto in carddb"

[ "$TODO" -ge "$THRESH" ] && exit 0

cd "$REPO" || exit 1
python3 scripts/paragraph/gen_fleet_tasks.py >> "$LOG" 2>&1
python3 - <<EOF
import sqlite3
c=sqlite3.connect('$DB')
c.execute("update meta set v='0' where k='backlog_offset'"); c.commit()
EOF
ADDED=$(curl -s -m 15 "http://localhost:9999/action?do=ingest&n=300")
# Frontier-driven priorities (Dani 2026-08-06): shapes that are the LAST
# blocker on the most review cards get worked first — max flips per landing.
python3 - <<PYEOF
import sqlite3, json
try:
    fr = json.load(open('/tmp/orch/flip-frontier.json'))
except Exception:
    raise SystemExit
c = sqlite3.connect('$DB')
for i in range(1, 6):
    name = fr.get('frontier_top%d_name' % i)
    if name:
        c.execute("update tickets set priority=? where state='todo' and title like 'REPARSE-MAP%' and title like ?",
                  (50 - (i - 1) * 5, '%' + name + '%'))
c.commit()
PYEOF
log "map todo was $TODO (<$THRESH) — regenerated + ingested: $ADDED (frontier priorities applied)"
