#!/usr/bin/env bash
# Compatibility entry point for the existing reboot cron: start only Factory NG.
# Idempotent: never kill shared tmux sessions or unrelated model processes.
set -euo pipefail
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:/usr/local/go/bin:$PATH"
cd /opt/development/magic-ops
mkdir -p /tmp/orch
exec 9>/tmp/orch/dispatcher-admin.lock
flock -n 9 || exit 75

if [ "${1:-}" = stop ]; then
  curl -fsS --max-time 15 -X POST 'http://localhost:9999/factory-ng/control?action=stop'
  exit 0
fi
dashboard_command='while true; do PORT=:9999 DB_PATH=/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db BACKLOG=/opt/development/kanboard-backlog/reparse-tasks.jsonl /opt/development/magic-ops/services/dispatcher/v4/dispatcher-v4 >> /tmp/dispatcher-v4.log 2>&1 & dispatcher_pid=$!; wait "$dispatcher_pid"; sleep 5; done'
if ! tmux has-session -t dispatcher 2>/dev/null; then
  tmux new-session -d -s dispatcher -n disp "$dashboard_command"
fi
start_window() {
  local name="$1" command="$2"
  if ! tmux list-windows -t dispatcher -F '#{window_name}' | command grep -qxF "$name"; then
    tmux new-window -d -t dispatcher -n "$name" "$command"
  fi
}
start_window disp "$dashboard_command"
if [ ! -f state/factory-ng-paused ]; then
  start_window factory-ng 'exec bash /opt/development/magic-ops/launchers/launch-factory-ng.sh'
fi
start_window factory-watch 'while true; do cd /opt/development/magic-ops || exit 1; python3 scripts/factory-ng-watchdog.py --interval 600 >> /tmp/orch/factory-ng-watchdog.log 2>&1 & watchdog_pid=$!; wait "$watchdog_pid"; sleep 15; done'
start_window kb 'exec bash /opt/development/magic-ops/launchers/launch-kb.sh'
start_window factory-viz 'while true; do cd /opt/development/magic-ops || exit 1; python3 scripts/factory-ng-coverage-snapshot.py >> /tmp/orch/factory-ng-viz.log 2>&1; age=$(( $(date +%s) - $(stat -c %Y state/factory-ng-galaxy.json 2>/dev/null || echo 0) )); if [ "$age" -ge 540 ]; then python3 scripts/factory-ng-galaxy-snapshot.py --iterations 30 >> /tmp/orch/factory-ng-viz.log 2>&1; fi; sleep 60; done'
echo 'Factory NG dashboard, controller, watchdog, card-knowledge and visualization are supervised.'
