#!/bin/bash
# Dispatcher-Worker v1 — connects to Dispatcher via HTTP
# Usage: dispatcher-worker.sh <worker-id> <clone-path>

set -e

WORKER_ID="${1:-worker-1}"
CLONE_PATH="${2:-/work/clone-$WORKER_ID}"
DISPATCHER_URL="http://localhost:9999"
HEARTBEAT_INTERVAL=60
REPO_URL="https://github.com/daniwb/magic-new"

log() { echo "[$(date '+%H:%M:%S')] $WORKER_ID: $*"; }

# Setup worker clone if needed
if [ ! -d "$CLONE_PATH" ]; then
  log "Creating clone at $CLONE_PATH"
  mkdir -p "$(dirname "$CLONE_PATH")"
  git clone "$REPO_URL" "$CLONE_PATH"
fi

cd "$CLONE_PATH"

# Main loop
while true; do
  log "Requesting ticket..."

  CLAIM_RESP=$(curl -s -m 5 "$DISPATCHER_URL/claim?worker=$WORKER_ID" 2>&1)
  [ -z "$CLAIM_RESP" ] && { log "No response from dispatcher"; sleep 5; continue; }
  TICKET_ID=$(echo "$CLAIM_RESP" | jq -r '.id // empty' 2>/dev/null)

  if [ -z "$TICKET_ID" ]; then
    log "No ticket available, waiting..."
    sleep 5
    continue
  fi

  log "Got ticket: $TICKET_ID"

  # Heartbeat loop (background)
  heartbeat_loop() {
    while true; do
      sleep "$HEARTBEAT_INTERVAL"
      log "Heartbeat for $TICKET_ID"
      curl -s "$DISPATCHER_URL/heartbeat?ticket=$TICKET_ID" > /dev/null 2>&1 || true
    done
  }
  heartbeat_loop &
  HB_PID=$!

  # Fix (simplified for MVP)
  if fix_result=$(timeout 600 bash -c "cd '$CLONE_PATH' && git fetch origin && git checkout -b 'worker-$WORKER_ID/$TICKET_ID' origin/main && echo 'Fixed'"); then
    log "Fix succeeded for $TICKET_ID"

    # Push branch
    git push origin "worker-$WORKER_ID/$TICKET_ID"
    PATCH_URL="origin/worker-$WORKER_ID/$TICKET_ID"

    # Report
    curl -s -X POST "$DISPATCHER_URL/report" \
      -H "Content-Type: application/json" \
      -d "{\"ticket_id\":\"$TICKET_ID\",\"status\":\"fixed\",\"patch_url\":\"$PATCH_URL\"}"

    log "Reported $TICKET_ID as fixed"
  else
    log "Fix failed for $TICKET_ID"
    curl -s -X POST "$DISPATCHER_URL/report" \
      -H "Content-Type: application/json" \
      -d "{\"ticket_id\":\"$TICKET_ID\",\"status\":\"retry\",\"note\":\"$fix_result\"}"
  fi

  kill $HB_PID 2>/dev/null || true
  wait $HB_PID 2>/dev/null || true
done
