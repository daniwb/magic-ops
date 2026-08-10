#!/usr/bin/env bash
# rg1 — ollama-cloud GLM-5.2 worker (phase.rs-gates era) ($0, weekly quota, auto-parks + self-resumes).
# Since 2026-08-08: HANDLER tier on gpt-oss:120b-cloud (same weights as the
# local handler lane validated for weeks) — grinds the per-card handler
# mountain when the quota window is open. Override model via RG1_MODEL.
W=rg1
D=/tmp/work/disp-$W
L=/tmp/orch/reparse-$W.log
mkdir -p /tmp/work && cd /tmp/work || exit 1
while true; do
  cd /tmp/work 2>/dev/null || exit 1
  TIER=handler OLLAMA_WORKER=1 OLLAMA_MODEL="${RG1_MODEL:-glm-5.2:cloud}" PACE_DISABLE=1 \
    bash /opt/development/magic-ops/scripts/dispatcher-worker-reparse.sh "$W" "$D" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
