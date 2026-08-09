#!/usr/bin/env bash
# lp1 — local staged lane on gpt-oss:120b via shim :4102, $0.
# 2026-08-09: back on MAP tier (handler todo drained; 104 map slices open).
# LANE_NO_DEPRIO: local failures skiplist locally but keep global priorities
# intact for the Sonnet shift at 20:00.
W=lp1
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch
while true; do
  PIPE_MODEL="${LP1_MODEL:-gpt-oss:120b}" PIPE_BASE_URL="http://127.0.0.1:4102" PACE_DISABLE=1 LANE_NO_DEPRIO=1 \
    bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
