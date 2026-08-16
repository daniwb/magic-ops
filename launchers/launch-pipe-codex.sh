#!/usr/bin/env bash
# pipe-codex — same staged single-shot map-tier lane as p1, but the model
# call goes through `codex exec` instead of `claude -p` (PIPE_ENGINE=codex,
# see map-pipeline.sh's model_call()). Same circle (map -> engine-pipeline
# -> map), same dispatcher claim/report protocol. Usage-gated on Codex's
# OWN account rate-limit window (lib-pace-gate-codex.sh), unrelated to the
# Claude pace gate p1/r1 share.
W=pipe-codex
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  PIPE_ENGINE=codex PIPE_MODEL="${CODEX_MODEL:-gpt-5.6-sol}" USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-99}" \
    bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
