#!/bin/bash
# Dispatcher Cutover — clean old branches, stop old workers, start dispatcher+new workers
# Run this once before going live

set -e

log() { echo "[CUTOVER] $*"; }

log "Step 1: Kill old bugfixer workers..."
pkill -f "bugfixer" || true
pkill -f "kanboard-launch" || true
sleep 2

log "Step 2: Clean old branches in main magic-new repo..."
cd /opt/development/magic-new
git fetch origin
# Delete all old bugfix/task-* branches locally
for branch in $(git branch | grep 'bugfix/task-'); do
  log "  Deleting $branch"
  git branch -D "$branch" || true
done

# Delete on origin (optional, risky — skip if unsure)
# git push origin --delete bugfix/task-* || true

log "Step 3: Cleanup old worker worktrees..."
# Remove stale worktrees that won't be used
for wt in /opt/development/magic-new-w*; do
  if [ -d "$wt" ]; then
    log "  Checking $wt..."
    # If more than 1h old and not in use, can remove
    # For now, just log
  fi
done

log "Step 4: Move dispatcher binary and create systemd unit..."
mkdir -p /opt/development/bin
cp /opt/development/magic-claude/services/dispatcher/dispatcher /opt/development/bin/
chmod +x /opt/development/bin/dispatcher

# Create systemd unit
cat > /etc/systemd/system/dispatcher.service << 'EOF'
[Unit]
Description=Bugfixer Dispatcher
After=network.target

[Service]
Type=simple
ExecStart=/opt/development/bin/dispatcher
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

log "Step 5: Enable and start dispatcher..."
systemctl daemon-reload
systemctl enable dispatcher
systemctl start dispatcher
sleep 2

# Verify it's running
if systemctl is-active --quiet dispatcher; then
  log "✓ Dispatcher is running"
else
  log "✗ Dispatcher failed to start"
  journalctl -u dispatcher -n 20
  exit 1
fi

log "Step 6: Start new workers..."
# Start 2 workers (the sweet spot)
for i in 1 2; do
  nohup bash /opt/development/magic-claude/scripts/dispatcher-worker.sh "worker-$i" "/work/clone-$i" > /tmp/worker-$i.log 2>&1 &
  log "  Started worker-$i (PID $!)"
done

log "✓ Cutover complete! Dispatcher is live."
log "Monitor with: journalctl -u dispatcher -f"
log "Status: curl http://localhost:9999/status"
