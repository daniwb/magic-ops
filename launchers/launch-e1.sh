#!/usr/bin/env bash
# e1 — staged Sonnet ENGINE lane (engine-lane.sh over the primitive-parked
# pile; replaced p2's map role 2026-08-08 — map runs on p1, engine on e1).
W=e1
L=/tmp/orch/engine-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  PIPE_MODEL="${E1_MODEL:-claude-sonnet-5}" \
    bash /opt/development/magic-ops/scripts/engine-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
