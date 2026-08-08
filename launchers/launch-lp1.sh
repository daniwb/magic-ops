#!/usr/bin/env bash
# lp1 — LOCAL staged pipeline lane (map->engine->map circle) on gpt-oss:120b
# via the anthropic shim :4102. $0 per ticket; replaces rl1 (GPU is
# single-lane — never run both). Usage gate bypassed: local model spends no
# Claude budget. Validated green 2026-08-07 (local pipeline + bugfix rounds).
W=lp1
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  PIPE_MODEL="${LP1_MODEL:-gpt-oss:120b}" \
    PIPE_BASE_URL="http://127.0.0.1:4102" \
    PACE_DISABLE=1 \
    bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
