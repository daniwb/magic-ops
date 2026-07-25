#!/bin/bash
# Dispatcher-Fabrik: tmux-Session "dispatcher" mit Dispatcher-Watchdog + 2 Workern.
# 2 Worker = Sweet Spot (3+ → Rate-Limits, siehe Worker-Analyse 2026-06).
# Neustart-sicher: jedes Fenster ist ein Restart-Loop.
set -euo pipefail

SESSION="dispatcher"
DISP_BIN="/opt/development/magic-claude/services/dispatcher/dispatcher"
WORKER="/opt/development/magic-claude/scripts/dispatcher-worker-real.sh"

# Alte Instanzen stoppen (nohup-Dispatcher + evtl. alte Session)
tmux kill-session -t "$SESSION" 2>/dev/null || true
pkill -f "dispatcher$" 2>/dev/null || true
pkill -f "dispatcher-worker-real" 2>/dev/null || true
sleep 2

# Dispatcher mit Watchdog
tmux new-session -d -s "$SESSION" -n disp \
  "while true; do $DISP_BIN >> /tmp/dispatcher.log 2>&1; echo \"[\$(date -Is)] dispatcher exited, restart in 5s\" >> /tmp/dispatcher.log; sleep 5; done"

sleep 3  # Dispatcher (inkl. Startup-Recovery) vor den Workern hochkommen lassen

# Claude-Worker nur wenn explizit angefordert (2026-07-20: weekly bei 91% —
# Claude-Handler abgesetzt bis zum 7d-Reset; CLAUDE_WORKERS=1 reaktiviert sie)
CLAUDE_WORKERS="${CLAUDE_WORKERS:-0}"
if [ "$CLAUDE_WORKERS" = "1" ]; then
# 2 Worker, je eigener Clone, je Restart-Loop
tmux new-window -t "$SESSION" -n w1 \
  "while true; do bash $WORKER w1 /tmp/work/disp-w1 >> /tmp/disp-worker-w1.log 2>&1; echo \"[\$(date -Is)] w1 exited, restart in 10s\" >> /tmp/disp-worker-w1.log; sleep 10; done"
tmux new-window -t "$SESSION" -n w2 \
  "while true; do bash $WORKER w2 /tmp/work/disp-w2 >> /tmp/disp-worker-w2.log 2>&1; echo \"[\$(date -Is)] w2 exited, restart in 10s\" >> /tmp/disp-worker-w2.log; sleep 10; done"

fi

# Primitive-Dauerläufer: Batches à 10 in Schleife (flock-koordiniert mit dem
# 02:00-Cron; Usage-Gate 5h+7d bremst, nachts volles 5h-Fenster)
tmux new-window -t "$SESSION" -n prim \
  "while true; do MAX_PRIMS=10 bash /opt/development/magic-claude/scripts/dispatcher-primitive-builder.sh >> /tmp/prim-builder.log 2>&1; sleep 300; done"

# w3 = Ollama-Cloud-Worker (glm-5.2:cloud, separate Quota): Readiness-Probe
# wartet auf Quota, dann normale Worker-Schleife
tmux new-window -t "$SESSION" -n w3 \
  "while true; do bash /opt/development/magic-claude/scripts/dispatcher-worker-ollama.sh >> /tmp/disp-worker-w3.log 2>&1; echo \"[\$(date -Is)] w3 exited, restart in 60s\" >> /tmp/disp-worker-w3.log; sleep 60; done"

echo "Fabrik läuft: tmux attach -t $SESSION"
echo "Logs: /tmp/dispatcher.log /tmp/disp-worker-w1.log /tmp/disp-worker-w2.log"
