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
python3 - <<'PYEOF'
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
