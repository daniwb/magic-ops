#!/usr/bin/env bash
# engine-lane — staged ENGINE lane (Dani 2026-08-08): works the primitive-
# parked pile. Picks blocked tickets carrying a missing_prim spec and runs
# the 7-step engine-pipeline on each: primitive build -> land through the
# integrator -> requeue the ticket at priority 60 so the map lanes close the
# circle. Companion to pipeline-lane.sh (map tier); Sonnet-priced, shares
# the Variante-C pace gate.
#
# Usage: engine-lane.sh WORKER_ID   (e.g. e1); env: PIPE_MODEL
set -uo pipefail
WORKER_ID="${1:?worker id}"
DISPATCHER="${DISPATCHER:-http://localhost:9999}"
OPS=/opt/development/magic-ops
REPO=/opt/development/test/openmagic
DB=$OPS/services/dispatcher/v4/dispatcher.db
export PIPE_MODEL="${PIPE_MODEL:-claude-sonnet-5}"
SKIPLIST="/tmp/orch/${WORKER_ID}-skip.txt"; touch "$SKIPLIST"
log() { printf '[%s] %s: %s\n' "$(date +%H:%M:%S)" "$WORKER_ID" "$*"; }
source "$OPS/scripts/lib-pace-gate.sh"

wait_for_landing() { # $1 branch — poll until merged into origin/main (max 25 min)
  local i=0
  while [ $i -lt 25 ]; do
    (cd "$REPO" && git fetch -q origin main "$1" 2>/dev/null)
    n=$(cd "$REPO" && git rev-list --count "origin/main..origin/$1" 2>/dev/null || echo x)
    [ "$n" = 0 ] && return 0
    sleep 60; i=$((i + 1))
  done
  return 1
}

while :; do
  if ! pace_ok; then log "pace-gate: over daily step — pause"; sleep 1800; continue; fi
  TICKET=$(python3 - <<PYEOF
import sqlite3, os
c = sqlite3.connect('$DB')
try:
    skip = set(open('$SKIPLIST').read().split())
except Exception:
    skip = set()
rows = c.execute("""select id from tickets where state='blocked' and missing_prim is not null and missing_prim != ''
    and missing_prim not like 'PHANTOM-%' and missing_prim not in ('parser-spine','unclassified-park')
    order by priority desc, id asc""").fetchall()
for (tid,) in rows:
    # skip tickets whose engine-pipeline already ran (circle attempts leave
    # a log) — re-tries were 0-for-8 on the first e1 shift; spend only on
    # never-tried tickets.
    if str(tid) in skip or os.path.exists('/tmp/orch/engine-pipeline-%d.log' % tid):
        continue
    row = c.execute("select worker_id, updated_at from tickets where id=?", (tid,)).fetchone()
    # respect another lane's fresh mark (taken within the last hour)
    import time
    if row and row[0] and row[0] != '$WORKER_ID' and time.time() - (row[1] or 0) < 3600:
        continue
    print(tid)
    break
PYEOF
)
  if [ -z "$TICKET" ]; then log "no primitive-parked tickets — sleep 300"; sleep 300; continue; fi
  # TAKE the ticket (Dani 2026-08-08): mark worker_id+updated_at so the
  # dashboard shows the engine lane's work and a second engine lane skips it.
  python3 -c "
import sqlite3, time
c = sqlite3.connect('$DB')
c.execute(\"update tickets set worker_id='$WORKER_ID', updated_at=? where id=$TICKET\", (int(time.time()),)); c.commit()"
  log "engine ticket #$TICKET"
  ELOG="/tmp/orch/engine-pipeline-$TICKET.log"; : > "$ELOG"
  CLONE="/tmp/work/${WORKER_ID}-clone" bash "$OPS/scripts/engine-pipeline.sh" "$TICKET" --push
  erc=$?
  # one attempt per ticket per lane lifetime — the pile is deep; a failed
  # build stays blocked for the manual round rather than churning.
  echo "$TICKET" >> "$SKIPLIST"
  if [ $erc -eq 0 ] && wait_for_landing "reparse/engine-task-$TICKET"; then
    log "#$TICKET primitive LANDED — requeue for the map lanes (the circle)"
    curl -s -m 10 "$DISPATCHER/action?do=requeue&id=$TICKET" >/dev/null 2>&1 || true
    python3 -c "
import sqlite3
c = sqlite3.connect('$DB')
c.execute(\"update tickets set priority=60 where id=$TICKET\"); c.commit()" 2>/dev/null || true
  else
    log "#$TICKET engine-pipeline rc=$erc — stays blocked"
  fi
  sleep 5
done
