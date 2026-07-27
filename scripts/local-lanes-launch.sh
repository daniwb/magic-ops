#!/bin/bash
# Standing loop for the local-GPU lanes (idempotent, analog orchestrator-launch):
# tmux session "local-lanes" runs every cycle:
#   switch AN  -> local-triage-queue.sh N_TRIAGE, dann local-record-builder.sh N_RECORDS
#   switch AUS (LOCAL_GPU_OFF) -> nur kurz schlafen, GPU bleibt stumm
# Zykluspause: CYCLE_SLEEP (default 45 min). Log: /tmp/local-lanes.log
set -uo pipefail
OPS="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="local-lanes"
N_TRIAGE="${N_TRIAGE:-10}"
N_RECORDS="${N_RECORDS:-5}"
CYCLE_SLEEP="${CYCLE_SLEEP:-2700}"

tmux has-session -t "$SESSION" 2>/dev/null && { echo "local-lanes läuft bereits."; exit 0; }
tmux new-session -d -s "$SESSION" \
  "while true; do
     if [ -f '$OPS/LOCAL_GPU_OFF' ]; then sleep 120; continue; fi
     echo \"[\$(date -Is)] lane cycle start\" >> /tmp/local-lanes.log
     bash '$OPS/scripts/local-triage-queue.sh' $N_TRIAGE >> /tmp/local-lanes.log 2>&1
     bash '$OPS/scripts/local-record-builder.sh' $N_RECORDS >> /tmp/local-lanes.log 2>&1
     echo \"[\$(date -Is)] lane cycle done — sleep $CYCLE_SLEEP s\" >> /tmp/local-lanes.log
     sleep $CYCLE_SLEEP
   done"
echo "local-lanes gestartet (tmux $SESSION): Triage $N_TRIAGE + Records $N_RECORDS pro Zyklus, Pause $((CYCLE_SLEEP/60)) min, Switch-Check alle 2 min bei AUS."
