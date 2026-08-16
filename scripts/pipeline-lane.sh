#!/usr/bin/env bash
# pipeline-lane — the staged Sonnet lane (Dani 2026-08-07): claims plain
# REPARSE-MAP tickets via the dispatcher (tier=map) and runs the CIRCLE per
# ticket:
#   map-pipeline  → green: report fixed
#                 → park NEEDS_PRIMITIVE: report parked (files the demand)
#                     then engine-pipeline on the same ticket; if that lands,
#                     requeue + re-run map-pipeline (park → primitive → green)
#                 → exit 2: report retry (counter++) + deprioritize, so the
#                     agentic fleet (r1) picks it up — the escalation ladder.
# Leases/heartbeats via the normal claim/report API → dashboard-visible.
#
# Usage: pipeline-lane.sh WORKER_ID   (e.g. p1); env:
#   PIPE_MODEL (default claude-sonnet-5), USAGE_LIMIT_PCT (default 99 — emergency brake; daily pacing is operator judgment)
set -uo pipefail
WORKER_ID="${1:?worker id}"
DISPATCHER="${DISPATCHER:-http://localhost:9999}"
OPS="${OPS:-/opt/development/magic-ops}"
REPO="${REPO:-/opt/development/test/openmagic}"
export PIPE_MODEL="${PIPE_MODEL:-claude-sonnet-5}"
LOG_PREFIX="[pipeline-lane]"
SKIPLIST="/tmp/orch/${WORKER_ID}-skip.txt"; touch "$SKIPLIST"
log() { printf '[%s] %s: %s\n' "$(date +%H:%M:%S)" "$WORKER_ID" "$*"; }

# Usage gating = the canonical Variante-C daily-step pace gate (Dani
# 2026-07-27): day-N of the real 7d quota window unlocks N/7 of the budget
# at the 20:00-CH boundary. lib-pace-gate.sh owns caching (TTL 180s,
# fail-open only after 30min blind) and the 5h hard ceiling. The earlier
# ad-hoc 75%/99% flat gate here ignored that canon (2026-08-08).
source "$OPS/scripts/lib-pace-gate.sh"
source "$OPS/scripts/lib-prim-extract.sh"
usage_gate() {
  if ! pace_ok; then log "pace-gate: over daily step — pause"; return 1; fi
  return 0
}

report() { # $1 ticket $2 status $3 reason $4 prim $5 why $6 note $7 tokens
  jq -n --arg t "$1" --arg w "$WORKER_ID" --arg s "$2" --arg r "$3" \
        --arg p "$4" --arg y "$5" --arg n "$6" --argjson tok "${7:-0}" \
    '{ticket_id:$t, worker_id:$w, status:$s, reason:$r,
      missing_primitive:$p, primitive_why:$y, note:$n, tokens:$tok, skipped:[]}' \
  | curl -s -X POST "$DISPATCHER/report" -H 'Content-Type: application/json' -d @- >/dev/null 2>&1 || true
}

tokens_from_log() { # sum raw token counts from a pipeline log
  command grep -a "tokens:" "$1" 2>/dev/null | python3 -c "
import sys,re
t=0
for l in sys.stdin:
    for m in re.finditer(r'(?:in|out|cache_r|cache_w)=(\d+)', l): t+=int(m.group(1))
print(t)" 2>/dev/null || echo 0
}

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
  if ! usage_gate; then sleep 1800; continue; fi
  EXCL=$(command grep -oE '^[0-9]+$' "$SKIPLIST" 2>/dev/null | head -400 | paste -sd, -)
  CLAIM=$(curl -s -m 30 "$DISPATCHER/claim?worker=$WORKER_ID&tier=map&exclude=$EXCL" 2>/dev/null || echo '{}')
  TICKET=$(printf '%s' "$CLAIM" | jq -r '.id // empty' 2>/dev/null)
  if [ -z "$TICKET" ]; then log "queue empty — sleep 120"; sleep 120; continue; fi
  TITLE=$(printf '%s' "$CLAIM" | jq -r '.title // ""')
  log "ticket #$TICKET: $TITLE"

  if command grep -qx "$TICKET" "$SKIPLIST"; then
    # already failed here — hand back without burning a retry so the
    # agentic fleet can take it; long sleep avoids a tight reclaim loop.
    report "$TICKET" retry infra "" "" "pipeline-lane skip (already exit-2 here)"
    log "#$TICKET on skiplist — released"; sleep 90; continue
  fi

  # heartbeat while the pipeline runs (lease stays visible on the dashboard)
  # dispatcher LeaseDuration is 180s — beat immediately, then every 60s like the fleet workers
  ( while :; do curl -s -m 10 "$DISPATCHER/heartbeat?ticket=$TICKET" >/dev/null 2>&1 || true; sleep 60; done ) >/dev/null 2>&1 &
  HB=$!

  PLOG="/tmp/orch/pipeline-$TICKET.log"; : > "$PLOG"
  PIPE_WORKER_ID="$WORKER_ID" DISPATCHER="$DISPATCHER" CLONE="/tmp/work/${WORKER_ID}-clone" bash "$OPS/scripts/map-pipeline.sh" "$TICKET" --push
  rc=$?
  TOK=$(tokens_from_log "$PLOG")

  case $rc in
    0)
      report "$TICKET" fixed "" "" "" "map-pipeline green (staged)" "$TOK"
      log "#$TICKET FIXED (map-pipeline, ${TOK} tok)";;
    4)
      PRIM=$(extract_prim "/tmp/orch/pipeline-$TICKET-reply-"*.md)
      WHY=$(command grep -am1 '^REASON:' "/tmp/orch/pipeline-$TICKET-reply-"*.md 2>/dev/null | head -c 400)
      REPLY=$(ls -1t "/tmp/orch/pipeline-$TICKET-reply-"*.md 2>/dev/null | head -1)
      CAP_RESULT=$(python3 "$OPS/scripts/capability-contract.py" --ticket "$TICKET" --reply "$REPLY" --dispatcher "$DISPATCHER" 2>>"$PLOG")
      read -r CID CSTATE <<<"$CAP_RESULT"
      if ! [[ "$CID" =~ ^[0-9]+$ ]]; then
        report "$TICKET" parked capability_review "" "$WHY" "atomic capability contract missing/heterogeneous; manual split required" "$TOK"
        log "#$TICKET sent to capability review — no engine round"
        kill $HB 2>/dev/null
        sleep 5
        continue
      fi
      if [ "$CSTATE" = implemented ]; then
        report "$TICKET" parked capability_review "$PRIM" "$WHY" "capability #$CID already implemented but mapping still parked; manual parser review required" "$TOK"
        log "#$TICKET capability #$CID already implemented — no duplicate engine round"
        kill $HB 2>/dev/null
        sleep 5
        continue
      fi
      report "$TICKET" parked structured_capability "$PRIM" "$WHY" "map-pipeline atomic capability #$CID" "$TOK"
      log "#$TICKET parked on capability #$CID ($PRIM) — trying engine-pipeline"
      ELOG="/tmp/orch/engine-pipeline-$TICKET.log"; : > "$ELOG"
      CAPABILITY_ID="$CID" PIPE_WORKER_ID="$WORKER_ID" DISPATCHER="$DISPATCHER" CLONE="/tmp/work/${WORKER_ID}-engine-clone" bash "$OPS/scripts/engine-pipeline.sh" "$TICKET" --push
      erc=$?
      BRANCH="reparse/capability-$CID"
      if [ $erc -eq 0 ] && wait_for_landing "$BRANCH"; then
        COMMIT=$(cd "$REPO" && git rev-parse "origin/$BRANCH" 2>/dev/null)
        jq -n --argjson id "$CID" --arg branch "$BRANCH" --arg commit "$COMMIT" \
          '{id:$id,branch:$branch,commit:$commit}' \
          | curl -s -m 15 -X POST "$DISPATCHER/capability/complete" -H 'Content-Type: application/json' -d @- >/dev/null
        log "#$TICKET capability #$CID LANDED — dependent map tickets requeued"
      else
        log "#$TICKET engine-pipeline rc=$erc — stays blocked for a manual round"
      fi;;
    2)
      echo "$TICKET" >> "$SKIPLIST"
      report "$TICKET" retry "" "" "" "map-pipeline exhausted — escalate to agentic" "$TOK"
      # local $0 lanes must not wreck the unlock-ranking for the Sonnet shift
      # (Dani 2026-08-09): they skiplist locally, no global deprioritize.
      if [ "${LANE_NO_DEPRIO:-0}" != "1" ]; then
        python3 -c "
import sqlite3
c=sqlite3.connect('$OPS/services/dispatcher/v4/dispatcher.db')
c.execute(\"update tickets set priority=-10 where id=$TICKET and state='todo'\"); c.commit()" 2>/dev/null || true
      fi
      log "#$TICKET escalated (retry counter++, deprioritized)";;
    *)
      # Skiplist too (2026-08-10): without this, a ticket whose pack
      # deterministically blows the model's max-turns/empty-reply case loops
      # forever on this worker — found live on og1/#2874 (GLM-cloud, 2 back-
      # to-back "empty twice — abort" cycles, re-claimed a 3rd time).
      echo "$TICKET" >> "$SKIPLIST"
      report "$TICKET" retry infra "" "" "pipeline infra error rc=$rc" "$TOK"
      log "#$TICKET infra error rc=$rc — skiplisted, returned"; sleep 60;;
  esac
  kill $HB 2>/dev/null
  sleep 5
done
