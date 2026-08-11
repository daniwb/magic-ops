#!/usr/bin/env bash
# rg1 — ollama-cloud GLM-5.2 worker ($0, weekly quota, auto-parks + self-resumes).
# 2026-08-10 (Dani): ENGINE tier — same queue as Sonnet r1, so GLM and
# Sonnet grind the class-round pile side by side (Sonnet-vs-GLM signal).
# Override model via RG1_MODEL.
W=rg1
D=/tmp/work/disp-$W
L=/tmp/orch/reparse-$W.log
mkdir -p /tmp/work && cd /tmp/work || exit 1
while true; do
  cd /tmp/work 2>/dev/null || exit 1
  TIER=engine OLLAMA_WORKER=1 OLLAMA_MODEL="${RG1_MODEL:-glm-5.2:cloud}" PACE_DISABLE=1 \
    bash /opt/development/magic-ops/scripts/dispatcher-worker-reparse.sh "$W" "$D" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
