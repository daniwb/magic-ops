#!/usr/bin/env bash
# og1 — ARCHIVED 2026-08-12 (Dani: "we don't have anymore access to it, as
# I don't pay it anymore"). Ollama Cloud subscription for glm-5.2:cloud was
# cancelled; every call returns 403 "this model requires a subscription,
# upgrade for access: https://ollama.com/upgrade" (confirmed via raw
# response, see memory ollama_cloud_403_subscription.md). DO NOT re-enable
# by editing this file back to the old loop — the account has no access,
# it will just burn ticket-cycles on instant 403s again (happened for ~30min
# on 2026-08-12 before caught, ~28 tickets falsely deprioritized).
# If Ollama Cloud access is restored in the future, the old lane body is
# preserved below in the comment block for reference.
echo "[$(date -Is)] og1 is ARCHIVED (Ollama Cloud subscription cancelled 2026-08-12) — refusing to start. See launchers/launch-og1.sh header." >&2
exit 1

# --- archived lane body (glm-5.2:cloud via Ollama Cloud staged MAP pipeline) ---
# W=og1
# L=/tmp/orch/pipeline-lane-$W.log
# mkdir -p /tmp/orch /tmp/work
# while true; do
#   ANTHROPIC_BASE_URL="${OG1_URL:-http://127.0.0.1:11434}" ANTHROPIC_AUTH_TOKEN=ollama \
#     PIPE_MODEL="${OG1_MODEL:-glm-5.2:cloud}" PACE_DISABLE=1 PIPE_MAX_TURNS="${OG1_MAX_TURNS:-15}" \
#     bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
#   echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
#   sleep 30
# done
