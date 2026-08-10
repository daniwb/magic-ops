#!/usr/bin/env bash
mkdir -p /tmp/work && cd /tmp/work || exit 1
while true; do
  cd /tmp/work 2>/dev/null || exit 1
  TIER=engine bash /opt/development/magic-ops/scripts/dispatcher-worker-reparse.sh r1 /tmp/work/disp-r1 >> /tmp/orch/reparse-r1.log 2>&1
  echo "[$(date -Is)] r1 exit, restart 15s" >> /tmp/orch/reparse-r1.log
  sleep 15
done
