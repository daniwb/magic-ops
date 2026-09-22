#!/usr/bin/env bash
# engine-lane — drains the open-capability backlog directly, instead of
# waiting for a map-tier ticket to coincidentally re-surface a capability
# via its park's capability contract (the only way engine-pipeline.sh used
# to get invoked; see pipeline-lane.sh case 4). Dani 2026-08-24: the map
# queue is starved (single-digit todo count) while 80+ capabilities sit
# 'open' — nothing was systematically working through them.
#
# engine-pipeline-pack.py already supports this standalone: with
# --capability it pulls capability_key/summary/specification_json
# (required_behavior + source_misses examples) straight from the DB, no
# /tmp/orch reply file needed — so we can drive it from any ticket still
# linked to the capability via ticket_capabilities, even a very old one.
#
# Picks the oldest open capability with a linked (state='blocked') ticket,
# read-only against dispatcher.db (WAL mode -> safe to read while the Go
# service writes). No dispatcher-side lease exists for capabilities, so
# this lane claims one itself via an atomic mkdir lock in
# /tmp/orch/capability-locks/ (2026-08-25: pipe-ox + pipe-glm52 both run
# this lane now — first version relied on the attempts table as a soft
# lock, but that row only gets written AFTER the ~2min pack-build step,
# leaving a race window; confirmed live when both workers grabbed
# capability #3 within 40s of each other).
#
# Usage: engine-lane.sh WORKER_ID   (e.g. pipe-glm52); env:
#   PIPE_MODEL/PIPE_ENGINE/... same vocabulary as pipeline-lane.sh
set -uo pipefail
WORKER_ID="${1:?worker id}"
DISPATCHER="${DISPATCHER:-http://localhost:9999}"
OPS="${OPS:-/opt/development/magic-ops}"
REPO="${REPO:-/opt/development/test/openmagic}"
DB="$OPS/services/dispatcher/v4/dispatcher.db"
[ -f "$OPS/.env" ] && set -a && source "$OPS/.env" && set +a
export PIPE_MODEL="${PIPE_MODEL:-claude-sonnet-5}"
SKIPLIST="/tmp/orch/${WORKER_ID}-engine-skip.txt"; touch "$SKIPLIST"
log() { printf '[%s] %s: %s\n' "$(date +%H:%M:%S)" "$WORKER_ID" "$*"; }

source "$OPS/scripts/lib-pace-gate.sh"
source "$OPS/scripts/lib-pace-gate-codex.sh"

# Same gating rules as pipeline-lane.sh's usage_gate() — kept in sync
# manually (small enough not to be worth a shared-lib extraction yet).
usage_gate() {
  if [ "${PIPE_ENGINE:-}" = codex ]; then
    if ! pace_ok_codex; then log "codex pace-gate: over daily step — pause"; return 1; fi
    return 0
  fi
  if [ "${PIPE_ENGINE:-}" = qwen-agentic ]; then
    return 0
  fi
  if [ "${PIPE_ENGINE:-}" = openrouter ] || [ "${PIPE_ENGINE:-}" = openrouter-agentic ]; then
    local cooldown
    cooldown=$(python3 "$OPS/scripts/openrouter_cooldown.py" status 2>/dev/null)
    if [ $? -ne 0 ]; then
      log "$(printf '%s' "$cooldown" | jq -r '"OpenRouter cooldown: \(.remaining_seconds)s remaining, 429 stage \(.consecutive_429s)"' 2>/dev/null || echo 'OpenRouter cooldown active')"
      return 1
    fi
    return 0
  fi
  if ! pace_ok; then log "pace-gate: over daily step — pause"; return 1; fi
  return 0
}

candidates() { # stdout: "CID TICKET" per line, oldest open capability first, skiplist excluded
  python3 - "$DB" "$SKIPLIST" <<'PYEOF'
import sqlite3, sys
db, skipfile = sys.argv[1], sys.argv[2]
skip = set()
try:
    with open(skipfile) as f:
        skip = {int(l) for l in f if l.strip().isdigit()}
except FileNotFoundError:
    pass
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
rows = c.execute("""select c.id, tc.ticket_id from capabilities c
                     join ticket_capabilities tc on tc.capability_id = c.id
                     where c.state='open' and tc.state='blocked'
                     order by c.id""").fetchall()
for cid, tid in rows:
    if cid not in skip:
        print(cid, tid)
PYEOF
}

LOCKDIR="/tmp/orch/capability-locks"; mkdir -p "$LOCKDIR"
try_lock() { # $1 capability id -> 0 if claimed
  local lock="$LOCKDIR/$1"
  # Reclaim a stale lock (worker crashed mid-round) — 25min > the slowest
  # measured engine round (~10min) plus wait_for_landing's own ceiling.
  if [ -d "$lock" ]; then
    local age=$(( $(date +%s) - $(stat -c %Y "$lock" 2>/dev/null || echo 0) ))
    [ "$age" -gt 1500 ] && rmdir "$lock" 2>/dev/null
  fi
  mkdir "$lock" 2>/dev/null
}

next_capability() { # stdout: "CID TICKET" of the first candidate we could lock, or empty
  local cid tid
  while IFS=' ' read -r cid tid; do
    [ -z "$cid" ] && continue
    if try_lock "$cid"; then
      echo "$cid $tid"
      return 0
    fi
  done < <(candidates)
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
  if ! usage_gate; then
    if [ "${PIPE_ENGINE:-}" = openrouter ] || [ "${PIPE_ENGINE:-}" = openrouter-agentic ]; then sleep 15; else sleep 1800; fi
    continue
  fi
  read -r CID TICKET < <(next_capability)
  if [ -z "${CID:-}" ]; then
    log "no open capability with a linked ticket — sleep 300"
    sleep 300; continue
  fi
  log "capability #$CID (via ticket #$TICKET)"

  ELOG="/tmp/orch/engine-pipeline-$TICKET.log"; : > "$ELOG"
  CAPABILITY_ID="$CID" PIPE_WORKER_ID="$WORKER_ID" DISPATCHER="$DISPATCHER" \
    CLONE="/tmp/work/${WORKER_ID}-engine-clone" bash "$OPS/scripts/engine-pipeline.sh" "$TICKET" --push
  erc=$?
  BRANCH="reparse/capability-$CID"

  case $erc in
    0)
      if wait_for_landing "$BRANCH"; then
        COMMIT=$(cd "$REPO" && git rev-parse "origin/$BRANCH" 2>/dev/null)
        jq -n --argjson id "$CID" --arg branch "$BRANCH" --arg commit "$COMMIT" \
          '{id:$id,branch:$branch,commit:$commit}' \
          | curl -s -m 15 -X POST "$DISPATCHER/capability/complete" -H 'Content-Type: application/json' -d @- >/dev/null
        log "capability #$CID LANDED — dependent map tickets requeued"
      else
        echo "$CID" >> "$SKIPLIST"
        log "capability #$CID pushed but didn't land within 25min — skiplisted, needs manual check"
      fi;;
    4)
      echo "$CID" >> "$SKIPLIST"
      log "capability #$CID parked (FRAMEWORK/AMBIGUOUS) — skiplisted, stays for a manual engine round";;
    *)
      # rc=1 (infra) covers both "deterministically broken pack" (empty
      # reply from a real response — skiplist, it'll never succeed on
      # retry) AND "upstream HTTP 429" (transient provider-side rate
      # limit — confirmed 2026-08-25 on z-ai/glm-5.2:free: OpenRouter's
      # free tier is backed by a provider-shared pool, unrelated to our
      # own account/key limits). Only the former deserves a permanent
      # skiplist; blacklisting on a 429 would burn through the whole
      # capability backlog on false negatives within minutes (exactly
      # what happened to #3-6 before this fix — see chat history).
      if command grep -q "HTTP 429" "$ELOG" 2>/dev/null; then
        log "capability #$CID rc=$erc — upstream 429, NOT skiplisted; shared cooldown active"
      else
        echo "$CID" >> "$SKIPLIST"
        log "capability #$CID rc=$erc — skiplisted"
      fi;;
  esac
  rmdir "$LOCKDIR/$CID" 2>/dev/null
  sleep 5
done
