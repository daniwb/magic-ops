#!/bin/bash
# Dispatcher-Fabrik: tmux-Session "dispatcher" mit Dispatcher-Watchdog + 2 Workern.
# 2 Worker = Sweet Spot (3+ → Rate-Limits, siehe Worker-Analyse 2026-06).
# Neustart-sicher: jedes Fenster ist ein Restart-Loop.
set -euo pipefail

SESSION="dispatcher"
DISP_BIN="/opt/development/magic-claude/services/dispatcher/v4/dispatcher-v4"
export PORT=":9999"
export DB_PATH="/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db"
WORKER="/opt/development/magic-claude/scripts/dispatcher-worker-real.sh"

# Alte Instanzen stoppen. WICHTIG: tmux kill-session killt NICHT die Kind-
# Prozesse (Loops reparenten zu init und laufen weiter). Ohne umfassendes pkill
# häufen sich über Neustarts mehrfache Worker/Builder + teure Claude-Calls an
# (Vorfall 2026-07-21: 4 primds-Loops + 8 deepseek-pro-Calls parallel).
tmux kill-session -t "$SESSION" 2>/dev/null || true
pkill -9 -f "dispatcher-v4" 2>/dev/null || true
pkill -9 -f "dispatcher-worker-real" 2>/dev/null || true
pkill -9 -f "dispatcher-worker-deepseek" 2>/dev/null || true
pkill -9 -f "dispatcher-worker-ollama" 2>/dev/null || true
pkill -9 -f "primitive-builder-deepseek" 2>/dev/null || true
pkill -9 -f "primitive-builder-v4" 2>/dev/null || true
# verwaiste Claude-Calls der Worker/Builder (flash/pro/glm) beenden
pkill -9 -f "claude -p --model deepseek" 2>/dev/null || true
pkill -9 -f "claude -p --model glm-" 2>/dev/null || true
sleep 3
# NB: NIEMALS /tmp/prim-builder-v4.lock löschen — das bricht den flock-Schutz
# (gelöschte Lock-Datei = neuer Halter bekommt eigenen Lock → Doppel-Builder).

# Dispatcher mit Watchdog
tmux new-session -d -s "$SESSION" -n disp \
  "while true; do PORT=:9999 DB_PATH='/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db' $DISP_BIN >> /tmp/dispatcher-v4.log 2>&1; echo \"[\$(date -Is)] dispatcher exited, restart in 5s\" >> /tmp/dispatcher.log; sleep 5; done"

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

# Sonnet-Primitive-Dauerläufer nur mit Claude-Budget (teilt den Lock mit dem
# DeepSeek-primds — nur EINER soll bauen). Gleicher Gate wie die Claude-Worker.
tmux new-window -t "$SESSION" -n prim \
  "while true; do MAX_PRIMS=10 bash /opt/development/magic-claude/scripts/dispatcher-primitive-builder-v4.sh >> /tmp/prim-builder.log 2>&1; sleep 300; done"

fi

# w3 = Ollama-Cloud-Worker (glm-5.2:cloud). Default AUS (2026-07-21: Ollama-
# Weekly-Quota erschöpft). OLLAMA_WORKER=1 reaktiviert nach Ollama-Reset.
if [ "${OLLAMA_WORKER:-0}" = "1" ]; then
tmux new-window -t "$SESSION" -n w3 \
  "while true; do bash /opt/development/magic-claude/scripts/dispatcher-worker-ollama.sh >> /tmp/disp-worker-w3.log 2>&1; echo \"[\$(date -Is)] w3 exited, restart in 60s\" >> /tmp/disp-worker-w3.log; sleep 60; done"
fi

# DeepSeek-Überbrückung (bis Claude-weekly-Reset): 1 Card-Worker (wd, flash→pro)
# + 1 Primitive-Builder (primds, pro). Beide sparen die DeepSeek-Peak-Hours aus
# (UTC 1-4h + 6-10h, doppelte Kosten). DEEPSEEK_WORKERS=0 schaltet sie ab.
# 2 DeepSeek-Card-Worker (wd + wd2). KEIN primds-Primitive-Builder mehr
# (2026-07-21: deepseek-v4-pro auf Primitiven zu teuer — 2 Handler reichen
# länger). DEEPSEEK_PRIM=1 holt den Primitive-Builder zurück.
if [ "${DEEPSEEK_WORKERS:-1}" = "1" ]; then
for W in wd wd2; do
tmux new-window -t "$SESSION" -n "$W" \
  "while true; do bash /opt/development/magic-claude/scripts/dispatcher-worker-deepseek.sh $W >> /tmp/disp-worker-$W.log 2>&1; echo \"[\$(date -Is)] $W exited, restart 30s\" >> /tmp/disp-worker-$W.log; sleep 30; done"
done
fi
if [ "${DEEPSEEK_PRIM:-0}" = "1" ]; then
tmux new-window -t "$SESSION" -n primds \
  "bash /opt/development/magic-claude/scripts/dispatcher-primitive-builder-deepseek.sh >> /tmp/prim-builder-ds.log 2>&1"
fi

echo "Fabrik läuft: tmux attach -t $SESSION"
echo "Logs: /tmp/dispatcher.log /tmp/disp-worker-w1.log /tmp/disp-worker-w2.log"
