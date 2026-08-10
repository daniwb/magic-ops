#!/usr/bin/env bash
# rg2 — ollama-cloud GLM-5.2 DEFAULT-tier (same queue as Sonnet r1: class rounds) (gates era; watch ratchet+spot-checks) ($0, weekly quota, auto-parks + self-resumes).
# Since 2026-08-08: HANDLER tier on gpt-oss:120b-cloud (same weights as the
# local handler lane validated for weeks) — grinds the per-card handler
# mountain when the quota window is open. Override model via RG2_MODEL.
W=rg2
D=/tmp/work/disp-$W
L=/tmp/orch/reparse-$W.log
mkdir -p /tmp/work && cd /tmp/work || exit 1
while true; do
  cd /tmp/work 2>/dev/null || exit 1
  TIER=engine OLLAMA_WORKER=1 OLLAMA_MODEL="${RG2_MODEL:-glm-5.2:cloud}" PACE_DISABLE=1 \
    bash /opt/development/magic-ops/scripts/dispatcher-worker-reparse.sh "$W" "$D" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
