#!/usr/bin/env bash
# pipe-qwen — agentic map-tier lane against local Qwen3.8-27B on the vulcan
# toolbox box (192.168.1.251:8080, llama-server).
#
# SUPERSEDES the original staged (single-shot) design (2026-08-16): that
# approach never worked reliably even after fixing every infra bug found
# along the way (tool-call hallucination, budget too small, format
# corruption) — the model just doesn't answer well cold from a pre-packed
# context dump. Switched to a real agentic tool loop instead (PIPE_ENGINE=
# qwen-agentic, see map-pipeline.sh model_call() and qwen-agentic-call.py):
# qwen explores far more efficiently with real read_file/grep/list_dir
# tools than it ever answered from a static pack.
#
# Root-cause fix underneath BOTH modes (2026-08-17): server default
# temperature (1.0) was above either of Qwen3's own documented presets, and
# "thinking" was never suppressed — turned out genuinely unbounded, up to
# 24000 tokens burned purely on reasoning with zero output, repeatedly.
# chat_template_kwargs.enable_thinking:false + Qwen3's non-thinking preset
# (temp 0.7/top_p 0.8/top_k 20/min_p 0) fixed it completely: a ticket that
# failed for 3.5hr staged (and for hours across 5 agentic attempts
# pre-fix) completed correctly — real patch, verified full gate pass — in
# 12.5 minutes once fixed.
W=pipe-qwen
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  PIPE_ENGINE=qwen-agentic \
    PIPE_BASE_URL="${QWEN_BASE_URL:-http://192.168.1.251:8080}" \
    PIPE_MODEL="${QWEN_MODEL:-./Qwen3.8-27B/Qwen3.8-27B-Q8_0.gguf}" \
    USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-99}" \
    PIPE_AGENTIC_MAX_TURNS="${QWEN_MAX_TURNS:-25}" \
    PIPE_MAX_TOKENS_CAP="${QWEN_MAX_TOKENS_CAP:-8000}" \
    bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
