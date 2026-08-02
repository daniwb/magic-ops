#!/bin/bash
# Startet die REPARSE-Fabrik: Dispatcher v4 (BACKLOG=reparse-tasks.jsonl) +
# N Reparse-Worker (default 1 — Tasks teilen sich reparse.py als Hot-File;
# 2. Worker NUR wenn das Gate der Engpass ist, harte Kappe 2) in tmux
# Session "dispatcher". Ersetzt dispatcher-orchestrator-launch.sh (v1-Ära,
# Card/VOCAB-Phasen) für die Reparse-Ära.
#
# Usage:
#   dispatcher-reparse-launch.sh [N]   N Worker starten (default 1, max 2)
#   dispatcher-reparse-launch.sh stop  Session + alle Kind-Loops killen
set -uo pipefail

SESSION="dispatcher"
DISP_BIN="/opt/development/magic-ops/services/dispatcher/v4/dispatcher-v4"
DB_PATH="/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db"
BACKLOG="/opt/development/kanboard-backlog/reparse-tasks.jsonl"
WORKER="/opt/development/magic-ops/scripts/dispatcher-worker-reparse.sh"

kill_orphans() {
  # tmux kill-session killt Kind-Loops NICHT (reparenten zu init) — Runaway-
  # Vorfall 2026-07-21. Umfassendes pkill aller Worker-/Builder-Muster.
  pkill -9 -f 'dispatcher-worker-reparse' 2>/dev/null || true
  pkill -9 -f 'dispatcher-worker-real' 2>/dev/null || true
  pkill -9 -f 'dispatcher-worker-deepseek' 2>/dev/null || true
  pkill -9 -f 'dispatcher-worker-ollama' 2>/dev/null || true
  pkill -9 -f 'dispatcher-primitive-builder' 2>/dev/null || true
  pkill -9 -f 'dispatcher-orchestrator' 2>/dev/null || true
  pkill -9 -f 'claude -p --model' 2>/dev/null || true
  pkill -9 -x dispatcher-v4 2>/dev/null || true
}

if [ "${1:-}" = "stop" ]; then
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  kill_orphans
  echo "Session '$SESSION' + Kind-Prozesse gestoppt."
  exit 0
fi

N="${1:-1}"
[ "$N" -gt 2 ] && { echo "Harte Kappe: max 2 Worker (Hot-File reparse.py)"; N=2; }

tmux kill-session -t "$SESSION" 2>/dev/null || true
kill_orphans
sleep 1

mkdir -p /tmp/orch /tmp/work

# Dispatcher-Watchdog (BACKLOG zeigt auf die Reparse-Demand-Tasks)
tmux new-session -d -s "$SESSION" -n disp \
  "while true; do PORT=:9999 DB_PATH='$DB_PATH' BACKLOG='$BACKLOG' '$DISP_BIN' >> /tmp/dispatcher-v4.log 2>&1; echo \"[\$(date -Is)] dispatcher exited, restart 5s\" >> /tmp/dispatcher.log; sleep 5; done"

for i in $(seq 1 20); do curl -fsS -m2 http://localhost:9999/stats >/dev/null 2>&1 && break; sleep 1; done

for i in $(seq 1 "$N"); do
  tmux new-window -t "$SESSION:" -n "r$i" \
    "while true; do bash '$WORKER' 'r$i' '/tmp/work/disp-r$i' >> /tmp/orch/reparse-r$i.log 2>&1; echo \"[\$(date -Is)] r$i exit, restart 15s\" >> /tmp/orch/reparse-r$i.log; sleep 15; done"
done

# Fable-Engine-Worker (TIER=engine): claimt nur REPARSE-ENGINE-Tickets.
# FABLE_WORKERS=0 deaktiviert (Default 1 seit 2026-08-02, Dani).
if [ "${FABLE_WORKERS:-1}" = "1" ]; then
  tmux new-window -t "$SESSION:" -n rf1 \
    "while true; do TIER=engine bash '$WORKER' 'rf1' '/tmp/work/disp-rf1' >> /tmp/orch/reparse-rf1.log 2>&1; echo \"[\$(date -Is)] rf1 exit, restart 15s\" >> /tmp/orch/reparse-rf1.log; sleep 15; done"
fi

echo "Reparse-Fabrik läuft: dispatcher (:9999, BACKLOG=$(basename "$BACKLOG")) + $N Worker + Fable-Engine-Worker rf1."
echo "  Attach: tmux attach -t $SESSION   Logs: tail -f /tmp/orch/reparse-r1.log"
