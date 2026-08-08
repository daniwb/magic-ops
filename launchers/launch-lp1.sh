#!/usr/bin/env bash
# lp1 — LOCAL staged HANDLER lane (map->handler pattern, per-card) on
# gpt-oss:120b via the anthropic shim :4102. $0 per ticket; GPU is
# single-lane — never run both lp1 and rl1. Usage gate bypassed. Switched
# from map to handler tier 2026-08-08 (map lane's upstream reliability was
# too flaky for shape-gated work; handler-pipeline was validated green
# earlier — Cemetery Gatekeeper #2193, 9.5 min, $0 — and self-contained
# per-card scope tolerates an occasional bad attempt better).
W=lp1
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  PIPE_MODEL="${LP1_MODEL:-gpt-oss:120b}" \
    PIPE_BASE_URL="http://127.0.0.1:4102" \
    PACE_DISABLE=1 \
    bash /opt/development/magic-ops/scripts/handler-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
