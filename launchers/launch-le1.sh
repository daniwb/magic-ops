#!/usr/bin/env bash
# le1 — LOCAL engine lane (Dani 2026-08-09): engine-pipeline on gpt-oss:120b
# via the shim :4102, $0. Experiment: local engine capability was unproven
# (test-only phantom greens 2026-08-08) — has_nontest_code gate now rejects
# that failure mode, so honest outcomes only.
W=le1
L=/tmp/orch/engine-lane-$W.log
mkdir -p /tmp/orch
while true; do
  PIPE_MODEL="${LE1_MODEL:-gpt-oss:120b}" PIPE_BASE_URL="http://127.0.0.1:4102" PACE_DISABLE=1 \
    bash /opt/development/magic-ops/scripts/engine-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
