#!/bin/bash
# burn-workers-launch.sh — 2 zusätzliche Card-Worker, die den RESTLICHEN
# Wochen-Budget verbrauchen, bevor er um 18:00 UTC ungenutzt verfällt.
#
# USAGE_LIMIT_PCT=0 schaltet das Usage-Gate AUS (der normale Gate blockt bei
# 99%). Die Worker laufen also bewusst in die letzten Prozente. Ist das echte
# API-Limit erreicht, greift die Infra-Erkennung im Worker selbst.
#
# SELBST-STOPP am DEADLINE: sonst laufen nach dem Reset 4 Worker parallel
# (Orchestrator startet seine 2 wieder) — und laut Messung sind 3+ Worker
# kontraproduktiv (62% Rate-Limit-Fehler).
#
# Die beiden Worker fahren zugleich das Katalog-A/B (burn-1=headings,
# burn-2=index), damit der Burn auch Vergleichsdaten liefert.
set -uo pipefail
WORKER=/opt/development/magic-claude/scripts/dispatcher-worker-real.sh
DEADLINE=$(date -u -d "${DEADLINE_UTC:-2026-07-29 18:00:00}" +%s)
for slot in 1 2; do
  id="burn-$slot"; clone="/tmp/work/$id"; log="/tmp/orch/$id.log"
  pidf="/tmp/orch/$id.pgid"
  if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then
    echo "$id läuft bereits"; continue
  fi
  rm -rf "$clone"; mkdir -p "$clone"
  setsid bash -c "
    while [ \"\$(date +%s)\" -lt $DEADLINE ]; do
      USAGE_LIMIT_PCT=0 bash '$WORKER' '$id' '$clone' >> '$log' 2>&1
      echo \"[\$(date -Is)] $id cycle end, restart 10s\" >> '$log'
      sleep 10
    done
    echo \"[\$(date -Is)] $id DEADLINE erreicht — beende (Orchestrator übernimmt)\" >> '$log'
    rm -f '$pidf'
  " >/dev/null 2>&1 &
  echo $! > "$pidf"
  echo "$id gestartet (mode=$(cat /opt/development/magic-ops/catalog-mode-$id), pgid $(cat $pidf))"
done
echo "Deadline: $(date -u -d @$DEADLINE -Is) — danach stoppen sich beide selbst."
