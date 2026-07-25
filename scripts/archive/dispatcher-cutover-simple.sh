#!/bin/bash
# Dispatcher Cutover — LIVE (simplified, no systemd)
# This stops old workers and starts dispatcher + new workers

set -e

log() { echo "[$(date '+%H:%M:%S')] CUTOVER: $*"; }

log "=== STARTING CUTOVER ==="

log "Step 1: Killing old bugfixer workers..."
pkill -f "bugfixer" || true
pkill -f "kanboard-launch" || true
pkill -f "dispatcher-worker" || true
sleep 2

log "Step 2: Cleaning old branches from main repo..."
cd /opt/development/magic-new
git fetch origin
for branch in $(git branch 2>/dev/null | grep 'bugfix/task-' || true); do
  log "  Deleting local branch: $branch"
  git branch -D "$branch" 2>/dev/null || true
done

log "Step 3: Starting Dispatcher in background..."
rm -f /tmp/dispatcher.db  # Fresh start
nohup /opt/development/magic-claude/services/dispatcher/dispatcher > /tmp/dispatcher.log 2>&1 &
DISPATCHER_PID=$!
log "  Dispatcher PID: $DISPATCHER_PID"
sleep 2

# Check dispatcher is running
if curl -s http://localhost:9999/status > /dev/null 2>&1; then
  log "✓ Dispatcher is responsive"
else
  log "✗ Dispatcher failed to respond"
  cat /tmp/dispatcher.log
  exit 1
fi

log "Step 4: Starting Worker 1..."
mkdir -p /tmp/work/clone-1
nohup bash /opt/development/magic-claude/scripts/dispatcher-worker.sh "worker-1" "/tmp/work/clone-1" > /tmp/worker-1.log 2>&1 &
WORKER1_PID=$!
log "  Worker-1 PID: $WORKER1_PID"

log "Step 5: Starting Worker 2..."
mkdir -p /tmp/work/clone-2
nohup bash /opt/development/magic-claude/scripts/dispatcher-worker.sh "worker-2" "/tmp/work/clone-2" > /tmp/worker-2.log 2>&1 &
WORKER2_PID=$!
log "  Worker-2 PID: $WORKER2_PID"

sleep 3

log ""
log "=== CUTOVER COMPLETE ==="
log "Dispatcher:  $DISPATCHER_PID"
log "Worker-1:    $WORKER1_PID"
log "Worker-2:    $WORKER2_PID"
log ""
log "Monitor dispatcher: tail -f /tmp/dispatcher.log"
log "Monitor worker-1:   tail -f /tmp/worker-1.log"
log "Monitor worker-2:   tail -f /tmp/worker-2.log"
log "Status:             curl http://localhost:9999/status"
log ""
log "Running for 1 hour... Check back at $(date -d '+1 hour' '+%H:%M:%S')"
