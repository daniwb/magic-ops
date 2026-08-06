#!/usr/bin/env bash
W=ro1
D=/tmp/work/disp-$W
L=/tmp/orch/reparse-$W.log
mkdir -p /tmp/work && cd /tmp/work || exit 1
while true; do
  cd /tmp/work 2>/dev/null || exit 1
  OLLAMA_WORKER=1 OLLAMA_MODEL=glm-5.2:cloud PACE_DISABLE=1 \
    bash /opt/development/magic-ops/scripts/dispatcher-worker-reparse.sh "$W" "$D" >> "$L" 2>&1
  echo "[$(date -Is)] $W exit, restart 30s" >> "$L"
  sleep 30
done
