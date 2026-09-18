#!/usr/bin/env bash
# Durable controller supervision, shared by reboot and dashboard Start.
set -uo pipefail
OPS="${FACTORY_NG_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$OPS" || exit 1
export OPS FACTORY_NG_ROOT="$OPS"
export FACTORY_NG_SOURCE="${FACTORY_NG_SOURCE:-$OPS/../test/openmagic}"
export OPENMAGIC_ROOT="$FACTORY_NG_SOURCE"
export MAGIC_NEW_ROOT="${MAGIC_NEW_ROOT:-$OPS/../magic-new}"
export CARDDB="${CARDDB:-$MAGIC_NEW_ROOT/backend/data/carddb}"
export GO_CACHE_OPS_ROOT="$OPS"
export GO_CACHE_ROOT="${GO_CACHE_ROOT:-$OPS/../.gocache-magic}"
export GOCACHE="$GO_CACHE_ROOT"
export PYTHONPATH="$OPS/../../pydeps${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$OPS/../../toolchain/go/bin:$PATH"
if [ -f "$OPS/.env" ]; then
  set -a
  . "$OPS/.env"
  set +a
fi
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:/usr/local/go/bin:$PATH"
mkdir -p /tmp/orch
stop_controller() {
  trap '' TERM INT HUP
  if [ -n "${controller_pid:-}" ]; then
    kill -TERM "$controller_pid" 2>/dev/null || true
    wait "$controller_pid" 2>/dev/null || true
  fi
  exit 0
}
trap stop_controller TERM INT HUP
while true; do
  [ ! -f state/factory-ng-paused ] || exit 0
  python3 scripts/factory-ng-controller.py --interval 15 --producer-interval 300 >> /tmp/orch/factory-ng.log 2>&1 &
  controller_pid=$!
  wait "$controller_pid"
  sleep 15
done
