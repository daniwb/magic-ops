#!/usr/bin/env bash
# rl1 — handler-tier worker via llmproxy (llm.k.ezq.ch) through the shim :4102.
# Default model gpt-oss:120b since 2026-08-04 (45 tok/s; qwen3-coder:30b = 5 tok/s fallback).
W=rl1
D=/tmp/work/disp-$W
L=/tmp/orch/reparse-$W.log
mkdir -p /tmp/work && cd /tmp/work || exit 1
while true; do
  cd /tmp/work 2>/dev/null || exit 1
  TIER=handler OLLAMA_WORKER=1 OLLAMA_URL=http://127.0.0.1:4102 \
    OLLAMA_MODEL="${RL1_MODEL:-gpt-oss:120b}" PACE_DISABLE=1 \
    CLAUDE_TIMEOUT=5400 WORKER_MAX_TURNS=200 \
    bash /opt/development/magic-ops/scripts/dispatcher-worker-reparse.sh "$W" "$D" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
