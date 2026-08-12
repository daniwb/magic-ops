#!/usr/bin/env bash
# p3 — third staged Sonnet pipeline lane, identical to p1/p2 (map->engine->map
# circle per ticket). Own clone dirs + skiplist via WORKER_ID. See
# docs/pipeline-workflows.md.
W=p3
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  PIPE_MODEL="${P3_MODEL:-claude-sonnet-5}" USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-99}" \
    bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
