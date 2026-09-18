#!/usr/bin/env bash
set -euo pipefail

ROOT="${MAGIC_STACK_ROOT:-/data/magic-stack}"
DEVELOPMENT="$ROOT/development"
OPS="$DEVELOPMENT/magic-ops"
ORCH="$ROOT/orch"
PID_FILE="$ORCH/magic-control.pid"

export PATH="$HOME/.local/bin:$ROOT/toolchain/go/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="$ROOT/pydeps${PYTHONPATH:+:$PYTHONPATH}"
export OPS
export FACTORY_NG_ROOT="$OPS"
export FACTORY_NG_SOURCE="$DEVELOPMENT/test/openmagic"
export OPENMAGIC_ROOT="$FACTORY_NG_SOURCE"
export MAGIC_NEW_ROOT="$DEVELOPMENT/magic-new"
export OPENMAGIC_BUILD_PLAN="$FACTORY_NG_SOURCE/corpus/build-plan.jsonl"
export KB_REPO="$FACTORY_NG_SOURCE"
export CARDDB="$DEVELOPMENT/magic-new/backend/data/carddb"
export WORKERS_CONFIG="$OPS/config/workers.json"
export DB_PATH="$OPS/services/dispatcher/v4/dispatcher.db"
export BACKLOG="$DEVELOPMENT/kanboard-backlog/reparse-tasks.jsonl"
export GOCACHE="$DEVELOPMENT/.gocache-magic"
export GO_CACHE_OPS_ROOT="$OPS"
export GO_CACHE_ROOT="$GOCACHE"

if [ -f "$OPS/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$OPS/.env"
  set +a
fi

mkdir -p "$ORCH" /tmp/work "$GOCACHE"
factory_paused=0
if [ -f "$OPS/state/factory-ng-paused" ]; then
  factory_paused=1
  echo "Factory NG controller is paused; dashboard and supporting services will still start." >&2
fi
if [ -f "$PID_FILE" ]; then
  current_pid=$(<"$PID_FILE")
  if [[ "$current_pid" =~ ^[0-9]+$ ]] && kill -0 "$current_pid" 2>/dev/null \
    && [ -r "/proc/$current_pid/cmdline" ] \
    && tr '\0' ' ' <"/proc/$current_pid/cmdline" | grep -Fq "$0"; then
    echo "Magic Control is already running (pid $current_pid)." >&2
    exit 1
  fi
fi

for command in python3 codex claude; do
  command -v "$command" >/dev/null || {
    echo "Required native command is unavailable: $command" >&2
    exit 1
  }
done

# Worker controls add windows to this session.  It is intentionally separate
# from this supervisor, so restarting the dashboard never kills active lanes.
if ! tmux has-session -t dispatcher 2>/dev/null; then
  tmux new-session -d -s dispatcher -n control 'exec bash'
fi

pids=()
start_service() {
  local log="$1"
  shift
  "$@" >>"$ORCH/$log" 2>&1 &
  pids+=("$!")
}
stop_services() {
  local pid
  trap - EXIT TERM INT HUP
  for pid in "${pids[@]:-}"; do kill -TERM "$pid" 2>/dev/null || true; done
  for pid in "${pids[@]:-}"; do wait "$pid" 2>/dev/null || true; done
  rm -f "$PID_FILE"
}
trap 'stop_services; exit 0' TERM INT HUP
trap stop_services EXIT

printf '%s\n' "$$" >"$PID_FILE"
cd "$OPS"
start_service dispatcher-v4.log env PORT=:9999 "$OPS/services/dispatcher/v4/dispatcher-v4"
# The pause flag can be changed from the dashboard after this supervisor has
# started.  Keep a small native monitor so clearing it starts the controller
# without another dashboard/API restart; recreating it after a normal exit
# retains the existing durable-controller supervision behavior.
start_service factory-ng-controller.log bash -c '
  while :; do
    if [ ! -f "$1/state/factory-ng-paused" ]; then
      if ! tmux list-windows -t dispatcher -F "#{window_name}" | grep -qxF factory-ng; then
        tmux new-window -d -t dispatcher -n factory-ng "exec bash $1/launchers/launch-factory-ng.sh"
      fi
    fi
    sleep 15
  done
' _ "$OPS"
start_service factory-ng-watchdog.log python3 "$OPS/scripts/factory-ng-watchdog.py" --interval 600
start_service kb.log python3 "$OPS/scripts/card-knowledge-service.py"
start_service factory-ng-viz.log bash -c 'while :; do python3 "$1"; sleep 60; done' _ "$OPS/scripts/factory-ng-coverage-snapshot.py"
start_service magic-backend.log bash -c 'cd "$1"; exec env SERVER_PORT=8090 "$2"' _ "$DEVELOPMENT/magic-new" "$DEVELOPMENT/magic-new/bin/magic-api-server"
start_service magic-frontend.log python3 -m http.server 3000 --directory "$DEVELOPMENT/magic-new/frontend"

wait -n "${pids[@]}"
exit 1
