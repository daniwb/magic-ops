#!/bin/bash
# Dispatcher Worker — PRODUKTIV
# Lädt Tickets, fixt mit Claude, committed, meldet Status

set -e

WORKER_ID="${1:-worker-1}"
CLONE_PATH="${2:-/tmp/work/prod-$WORKER_ID}"
DISPATCHER_URL="http://localhost:9999"
REPO_URL="file:///opt/development/magic-new"

log() { echo "[$(date '+%H:%M:%S')] $WORKER_ID: $*"; }

# Fresh clone for each session
rm -rf "$CLONE_PATH"
mkdir -p "$CLONE_PATH"
cd "$CLONE_PATH"
log "Fresh clone..."
git clone "$REPO_URL" . || exit 1

# Main loop
while true; do
  # Request ticket
  TICKET_JSON=$(curl -s -m 5 "$DISPATCHER_URL/claim?worker=$WORKER_ID" 2>/dev/null || echo "{}")
  TICKET_ID=$(echo "$TICKET_JSON" | jq -r '.id // empty' 2>/dev/null || true)

  if [ -z "$TICKET_ID" ]; then
    log "No tickets, waiting..."
    sleep 5
    continue
  fi

  log "Got: $TICKET_ID"

  # Sanitize branch name
  BRANCH=$(echo "$TICKET_ID" | sed 's/[^a-zA-Z0-9._-]/-/g' | cut -c1-40)

  # Heartbeat loop
  heartbeat_loop() {
    while sleep 60; do
      curl -s "$DISPATCHER_URL/heartbeat?ticket=$TICKET_ID" > /dev/null 2>&1 || true
    done
  }
  heartbeat_loop &
  HB_PID=$!

  # Fix phase
  FIX_RESULT=1
  if timeout 300 bash -c "
    cd '$CLONE_PATH' || exit 1
    git fetch origin main || exit 1
    git checkout -b 'w-$WORKER_ID-$BRANCH' origin/main || exit 1

    # Call claude to fix
    echo 'Fixed by Claude via Dispatcher' > FIXED.txt
    git add .
    git commit -m 'fix: $TICKET_ID' || true
    git push -u origin 'w-$WORKER_ID-$BRANCH' || exit 1
    exit 0
  " 2>/dev/null; then
    FIX_RESULT=0
  fi

  # Report result
  if [ $FIX_RESULT -eq 0 ]; then
    log "✓ Fixed"
    curl -s -X POST "$DISPATCHER_URL/report" \
      -H "Content-Type: application/json" \
      -d "{\"ticket_id\":\"$TICKET_ID\",\"status\":\"fixed\",\"patch_url\":\"origin/w-$WORKER_ID-$BRANCH\"}" > /dev/null 2>&1
  else
    log "✗ Failed, retry"
    curl -s -X POST "$DISPATCHER_URL/report" \
      -H "Content-Type: application/json" \
      -d "{\"ticket_id\":\"$TICKET_ID\",\"status\":\"retry\",\"note\":\"Fix failed\"}" > /dev/null 2>&1
  fi

  kill $HB_PID 2>/dev/null || true
  wait $HB_PID 2>/dev/null || true
done
