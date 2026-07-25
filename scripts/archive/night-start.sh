#!/bin/bash
# Night Mode Startup — Stable Dispatcher v2 Fleet
# Run this für 24/7 operation

echo "=== Dispatcher v2 NIGHT MODE START ==="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Kill old processes
pkill -f "dispatcher" 2>/dev/null || true
pkill -f "dispatcher-worker" 2>/dev/null || true
sleep 2

# Clean
rm -f /tmp/dispatcher.db

# Start Dispatcher (persistent, no timeout)
cd /opt/development/magic-claude/services/dispatcher
nohup ./dispatcher > /tmp/dispatcher.log 2>&1 &
DISP_PID=$!
echo "✅ Dispatcher: PID $DISP_PID"

sleep 3

# Verify
STATUS=$(curl -s http://localhost:9999/status 2>/dev/null)
if [ -z "$STATUS" ]; then
  echo "❌ Dispatcher not responding!"
  exit 1
fi

echo "✅ Dispatcher responding: $STATUS"
echo ""

# Clean clones
rm -rf /tmp/work/real-*
mkdir -p /tmp/work/real-{1,2}

# Start 2 REAL workers
chmod +x /opt/development/magic-claude/scripts/dispatcher-worker-real.sh

nohup bash /opt/development/magic-claude/scripts/dispatcher-worker-real.sh "worker-1" "/tmp/work/real-1" > /tmp/worker-real-1.log 2>&1 &
W1_PID=$!
echo "✅ Worker-1: PID $W1_PID"

nohup bash /opt/development/magic-claude/scripts/dispatcher-worker-real.sh "worker-2" "/tmp/work/real-2" > /tmp/worker-real-2.log 2>&1 &
W2_PID=$!
echo "✅ Worker-2: PID $W2_PID"

sleep 5

echo ""
echo "=== SYSTEM READY FOR NIGHT OPERATION ==="
echo "Dispatcher:  /tmp/dispatcher.log"
echo "Worker-1:    /tmp/worker-real-1.log"
echo "Worker-2:    /tmp/worker-real-2.log"
echo "Status API:  http://localhost:9999/status"
echo ""
echo "Monitor: tail -f /tmp/dispatcher.log"
echo "Kill:    pkill -f dispatcher; pkill -f worker"
