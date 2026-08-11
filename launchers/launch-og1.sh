#!/usr/bin/env bash
# og1 — ollama-cloud GLM-5.2 worker on the STAGED MAP pipeline (NOT agentic).
# 2026-08-10 (Dani): pipeline stays the fleet default for map tickets
# (RUNBOOK: "pipeline-first fleet default" — 76% success excl. parks vs
# engine's 12% agentic-free-form problem is a different tier, not this
# decision). Runs the identical 7-step map-pipeline as p1, just routed
# through Ollama Cloud instead of the Anthropic API — same ANTHROPIC_BASE_URL
# override dispatcher-worker-reparse.sh's OLLAMA_WORKER=1 branch uses, no
# code changes needed since map-pipeline.sh's model_call() shells out to the
# plain `claude` CLI (respects ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN) when
# PIPE_BASE_URL is unset. $0 cost, own weekly quota — PACE_DISABLE=1 so the
# Sonnet pace gate never blocks it. Override model via OG1_MODEL.
# PIPE_MAX_TURNS=15 (2026-08-11): GLM tries tool calls despite being told it
# has none (confirmed via a caught raw response: stop_reason="tool_use",
# num_turns=6, terminal_reason="max_turns" on the map-pipeline's default of
# 5) — each blocked attempt burns a turn it can't get back, so it hits the
# ceiling mid-task far more than Sonnet does on the same budget. Raises both
# map-pipeline's default (5) and engine-pipeline's (10); p1 is unaffected
# since it doesn't set this var.
W=og1
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  ANTHROPIC_BASE_URL="${OG1_URL:-http://127.0.0.1:11434}" ANTHROPIC_AUTH_TOKEN=ollama \
    PIPE_MODEL="${OG1_MODEL:-glm-5.2:cloud}" PACE_DISABLE=1 PIPE_MAX_TURNS="${OG1_MAX_TURNS:-15}" \
    bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
