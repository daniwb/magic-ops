#!/bin/bash
# Startet Dispatcher (Watchdog) + Orchestrator in tmux-Session "dispatcher".
# Idempotent: vorhandene Fenster werden nicht doppelt gestartet. Von @reboot-Cron
# und manuell nutzbar. Der Orchestrator selbst managt die Card-/VOCAB-Phasen.
set -uo pipefail

SESSION="dispatcher"
DISP_BIN="/opt/development/magic-claude/services/dispatcher/v4/dispatcher-v4"
DB_PATH="/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db"
ORCH="/opt/development/magic-claude/scripts/dispatcher-orchestrator.sh"

# Session anlegen falls nicht vorhanden
tmux has-session -t "$SESSION" 2>/dev/null || tmux new-session -d -s "$SESSION" -n disp \
  "while true; do PORT=:9999 DB_PATH='$DB_PATH' '$DISP_BIN' >> /tmp/dispatcher-v4.log 2>&1; echo \"[\$(date -Is)] dispatcher exited, restart 5s\" >> /tmp/dispatcher.log; sleep 5; done"

# disp-Fenster sicherstellen (falls Session existierte aber ohne Watchdog)
tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx disp || tmux new-window -t "$SESSION" -n disp \
  "while true; do PORT=:9999 DB_PATH='$DB_PATH' '$DISP_BIN' >> /tmp/dispatcher-v4.log 2>&1; echo \"[\$(date -Is)] dispatcher exited, restart 5s\" >> /tmp/dispatcher.log; sleep 5; done"

# Dispatcher hochkommen lassen
for i in $(seq 1 20); do curl -fsS -m2 http://localhost:9999/vocab-list >/dev/null 2>&1 && break; sleep 1; done

# Orchestrator-Fenster (nur wenn nicht schon da). Restart-Loop, damit ein Absturz
# des Orchestrators sich selbst neu startet (Card-Worker werden vom EXIT-trap gestoppt).
if tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx orch; then
  echo "Orchestrator läuft bereits."
else
  tmux new-window -t "$SESSION" -n orch \
    "while true; do bash '$ORCH' >> /tmp/orch/orchestrator.log 2>&1; echo \"[\$(date -Is)] orchestrator exited, restart 15s\" >> /tmp/orch/orchestrator.log; sleep 15; done"
  echo "Orchestrator gestartet (tmux $SESSION:orch)."
fi
