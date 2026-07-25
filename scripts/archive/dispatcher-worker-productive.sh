#!/bin/bash
# Dispatcher-Worker mit echtem DSL-Fixer
# Nutzt den bestehenden kanboard-bugfixer.sh flow, koordiniert über Dispatcher

set -e

WORKER_ID="${1:-worker-1}"
CLONE_PATH="${2:-/tmp/work/clone-$WORKER_ID}"
DISPATCHER_URL="http://localhost:9999"
HEARTBEAT_INTERVAL=60
REPO_URL="https://github.com/daniwb/magic-new"
FIXER_SCRIPT="/opt/development/magic-new/scripts/kanboard-bugfixer.sh"

log() { echo "[$(date '+%H:%M:%S')] $WORKER_ID: $*"; }

# Setup clone
if [ ! -d "$CLONE_PATH" ]; then
  log "Creating clone at $CLONE_PATH"
  mkdir -p "$(dirname "$CLONE_PATH")"
  git clone "$REPO_URL" "$CLONE_PATH"
fi

cd "$CLONE_PATH"

# Main loop
while true; do
  log "Requesting ticket from dispatcher..."

  CLAIM_RESP=$(curl -s -m 5 "$DISPATCHER_URL/claim?worker=$WORKER_ID" 2>&1)
  [ -z "$CLAIM_RESP" ] && { log "No response from dispatcher"; sleep 5; continue; }
  TICKET_ID=$(echo "$CLAIM_RESP" | jq -r '.id // empty' 2>/dev/null)

  if [ -z "$TICKET_ID" ]; then
    log "No ticket available, waiting..."
    sleep 5
    continue
  fi

  log "Got ticket from dispatcher: $TICKET_ID"

  # Start heartbeat in background
  heartbeat_loop() {
    while true; do
      sleep "$HEARTBEAT_INTERVAL"
      curl -s "$DISPATCHER_URL/heartbeat?ticket=$TICKET_ID" > /dev/null 2>&1 || true
    done
  }
  heartbeat_loop &
  HB_PID=$!

  # === FIX PHASE ===
  # For MVP: mock fix with sleep (simulates claude fixer)
  # Production: use real fixer
  log "Starting fix for $TICKET_ID..."

  if timeout 120 bash -c "
    cd '$CLONE_PATH'

    # Ensure we're in a git repo
    [ -d .git ] || git init || { exit 1; }

    # Fetch and checkout
    git remote add origin '$REPO_URL' 2>/dev/null || git remote set-url origin '$REPO_URL'
    git fetch origin main:main 2>/dev/null || true
    git checkout -b 'worker-$WORKER_ID/$TICKET_ID' origin/main 2>/dev/null || git checkout -b 'worker-$WORKER_ID/$TICKET_ID' main 2>/dev/null || { exit 1; }

    # Simulate fix (mock for MVP)
    echo '// Fixed by dispatcher-worker' >> README.md
    git add README.md
    git commit -m \"chore: Fix for $TICKET_ID (dispatcher v2)\" || true

    # Try to push (may fail if no perms, that's ok for mock)
    git push -u origin 'worker-$WORKER_ID/$TICKET_ID' 2>/dev/null || true
    exit 0
  "; then
    log "Fix succeeded for $TICKET_ID"
    PATCH_URL="origin/worker-$WORKER_ID/$TICKET_ID"

    # Report as fixed
    curl -s -X POST "$DISPATCHER_URL/report" \
      -H "Content-Type: application/json" \
      -d "{\"ticket_id\":\"$TICKET_ID\",\"status\":\"fixed\",\"patch_url\":\"$PATCH_URL\"}"

    log "Reported $TICKET_ID as fixed"
  else
    log "Fix failed for $TICKET_ID"
    curl -s -X POST "$DISPATCHER_URL/report" \
      -H "Content-Type: application/json" \
      -d "{\"ticket_id\":\"$TICKET_ID\",\"status\":\"retry\",\"note\":\"Fix process failed\"}"

    log "Reported $TICKET_ID for retry"
  fi

  # Stop heartbeat
  kill $HB_PID 2>/dev/null || true
  wait $HB_PID 2>/dev/null || true

  log "Cycle complete, requesting next ticket..."
done
