#!/usr/bin/env bash
# gocache-guard — the shared build cache hit 32G and ENOSPC'd the box twice
# (2026-08-05 + 08-06). Retain warm artifacts while disk space is healthy;
# clean at the hard size cap or under disk pressure through the cache barrier.
# Cron: 40 * * * *
set -euo pipefail
CACHE="${GO_CACHE_ROOT:-/opt/development/.gocache-magic}"
RUNNER="${GO_CACHE_OPS_ROOT:-/opt/development/magic-ops}/scripts/go-cache-run.sh"
SIZE_GIB=$(du -sk "$CACHE" 2>/dev/null | awk '{printf "%d", $1/1024/1024}')
FREE_GIB=$(df -Pk "$CACHE" | awk 'NR == 2 {printf "%d", $4/1024/1024}')
MAX_GIB="${GO_CACHE_CLEAN_AT_GIB:-40}"
MIN_FREE_GIB="${GO_CACHE_MIN_FREE_GIB:-20}"
# Do not discard a useful cache merely because it crossed the old 20 GiB
# threshold. Preserve an absolute cap as well as a free-space reserve.
[[ "${SIZE_GIB:-0}" -lt 1 ]] && exit 0
if (( SIZE_GIB < MAX_GIB && FREE_GIB >= MIN_FREE_GIB )); then
  exit 0
fi
if "$RUNNER" clean; then
  echo "[$(date -Is)] centralized Go cache was ${SIZE_GIB}G, disk free ${FREE_GIB}G (cap ${MAX_GIB}G, reserve ${MIN_FREE_GIB}G) — safely cleaned" >> "${GO_CACHE_GUARD_LOG:-/tmp/orch/gocache-guard.log}"
fi
