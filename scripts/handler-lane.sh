#!/usr/bin/env bash
# handler-lane — staged handler-tier lane (map-pipeline pattern, one card per
# ticket). Companion to pipeline-lane.sh (map tier); no park->engine circle
# here since a handler ticket has no shape/primitive escalation — a park just
# reports parked and moves on (fleet vocab triage handles it same as rl1).
#
# Usage: handler-lane.sh WORKER_ID   (e.g. lp1); env:
#   PIPE_MODEL (default claude-sonnet-5), PIPE_BASE_URL (local shim),
#   PACE_DISABLE=1 for $0 lanes
set -uo pipefail
WORKER_ID="${1:?worker id}"
DISPATCHER="${DISPATCHER:-http://localhost:9999}"
OPS=/opt/development/magic-ops
SKIPLIST="/tmp/orch/${WORKER_ID}-skip.txt"; touch "$SKIPLIST"
log() { printf '[%s] %s: %s\n' "$(date +%H:%M:%S)" "$WORKER_ID" "$*"; }
source "$OPS/scripts/lib-pace-gate.sh"

report() { # $1 ticket $2 status $3 note $4 tokens
  jq -n --arg t "$1" --arg w "$WORKER_ID" --arg s "$2" --arg n "$3" --argjson tok "${4:-0}" \
    '{ticket_id:$t, worker_id:$w, status:$s, reason:"", missing_primitive:"", primitive_why:"", note:$n, tokens:$tok, skipped:[]}' \
  | curl -s -X POST "$DISPATCHER/report" -H 'Content-Type: application/json' -d @- >/dev/null 2>&1 || true
}

tokens_from_log() {
  command grep -a "tokens:" "$1" 2>/dev/null | python3 -c "
import sys,re
t=0
for l in sys.stdin:
    for m in re.finditer(r'(?:in|out|cache_r|cache_w)=(\d+)', l): t+=int(m.group(1))
print(t)" 2>/dev/null || echo 0
}

while :; do
  if ! pace_ok; then log "pace-gate: over daily step — pause"; sleep 300; continue; fi
  CLAIM=$(curl -s -m 30 "$DISPATCHER/claim?worker=$WORKER_ID&tier=handler" 2>/dev/null || echo '{}')
  TICKET=$(printf '%s' "$CLAIM" | jq -r '.id // empty' 2>/dev/null)
  if [ -z "$TICKET" ]; then log "queue empty — sleep 120"; sleep 120; continue; fi
  TITLE=$(printf '%s' "$CLAIM" | jq -r '.title // ""')
  log "ticket #$TICKET: $TITLE"

  if command grep -qx "$TICKET" "$SKIPLIST"; then
    report "$TICKET" retry "handler-lane skip (already exit-2 here)"
    log "#$TICKET on skiplist — released"; sleep 90; continue
  fi

  ( while :; do curl -s -m 10 "$DISPATCHER/heartbeat?ticket=$TICKET" >/dev/null 2>&1 || true; sleep 60; done ) >/dev/null 2>&1 &
  HB=$!

  PLOG="/tmp/orch/handler-pipeline-$TICKET.log"; : > "$PLOG"
  CLONE="/tmp/work/${WORKER_ID}-hclone" bash "$OPS/scripts/handler-pipeline.sh" "$TICKET" --push
  rc=$?
  TOK=$(tokens_from_log "$PLOG")

  case $rc in
    0) report "$TICKET" fixed "handler-pipeline green (staged)" "$TOK"; log "#$TICKET FIXED (${TOK} tok)";;
    4) report "$TICKET" parked "handler-pipeline park" "$TOK"; log "#$TICKET parked";;
    2) echo "$TICKET" >> "$SKIPLIST"
       report "$TICKET" retry "handler-pipeline exhausted" "$TOK"
       log "#$TICKET escalated (exhausted)";;
    *) report "$TICKET" retry "handler-pipeline infra error rc=$rc" "$TOK"
       log "#$TICKET infra error rc=$rc — returned"; sleep 60;;
  esac
  kill $HB 2>/dev/null
  sleep 5
done
