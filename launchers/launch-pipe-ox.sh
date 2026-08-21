#!/usr/bin/env bash
# pipe-ox — same staged single-shot map-tier lane as p1, but the model call
# goes through OpenRouter's free `stealth/ox-alpha` reasoning model instead
# of `claude -p` (PIPE_ENGINE=openrouter, see map-pipeline.sh's
# model_call()). Same circle (map -> engine-pipeline -> map), same
# dispatcher claim/report protocol. No pace-gate against a metered account
# (free tier, no usage-percentage API) — relies on OpenRouter's own
# server-side rate limiting; model_call() detects HTTP 429 and logs it
# distinctly.
#
# Needs OPENROUTER_API_KEY in /opt/development/magic-ops/.env (gitignored,
# sourced by pipeline-lane.sh) — create that file yourself, never commit it.
#
# Worker name defaults to pipe-ox; pass a different one ($1) to run a second
# instance in parallel (e.g. `launch-pipe-ox.sh pipe-ox2`) — pipeline-lane.sh
# derives a distinct CLONE dir and skiplist per worker name, so this is the
# same pattern p1/p2/p3 used historically. Both instances share the same
# OPENROUTER_API_KEY (rate limits are per-key account-wide, not per-worker —
# 20 req/min, 1000 req/day once past the $10-credit threshold, confirmed
# live 2026-08-21).
W="${1:-pipe-ox}"
L=/tmp/orch/pipeline-lane-$W.log
mkdir -p /tmp/orch /tmp/work
while true; do
  PIPE_ENGINE=openrouter \
    PIPE_MODEL="${OPENROUTER_MODEL:-stealth/ox-alpha}" \
    PIPE_MAX_TOKENS_CAP="${OX_MAX_TOKENS_CAP:-8000}" \
    PIPE_REASONING_TOKENS="${OX_REASONING_TOKENS:-3000}" \
    PIPE_MAX_NEED_ROUNDS="${OX_MAX_NEED_ROUNDS:-4}" \
    USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-99}" \
    bash /opt/development/magic-ops/scripts/pipeline-lane.sh "$W" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
