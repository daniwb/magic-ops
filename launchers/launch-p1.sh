#!/usr/bin/env bash
# p1 — the staged Sonnet pipeline lane (map->engine->map circle per ticket).
# Claims tier=map via the dispatcher; escalation to the agentic fleet happens
# through normal retry counters. See docs/pipeline-workflows.md.
W=p1
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  PIPE_MODEL="${P1_MODEL:-claude-sonnet-5}" USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-99}" \
    bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
