#!/bin/bash
# Manuelle Pause für Orchestrator/Card-Worker/VOCAB-Batch.
# Laufende Arbeit läuft DURCH (aktueller 5er-Batch, aktuelles Card-Ticket);
# NEUE Batches/Tickets werden übersprungen. Auto-Resume nach Ablauf — die
# Skripte prüfen die Ablaufzeit selbst, kein Resume-Cron nötig. Überlebt Reboot
# (persistente Datei; @reboot-Launcher startet einen Pause-bewussten Orchestrator).
#
#   dispatcher-pause.sh [STUNDEN]   Pause setzen (default 24)
#   dispatcher-pause.sh status      Status zeigen
#   dispatcher-pause.sh clear       Pause sofort aufheben (Resume)
set -uo pipefail
PAUSE_FILE="${PAUSE_FILE:-/opt/development/magic-claude/.orch-pause-until}"

case "${1:-24}" in
  clear|--clear|off)
    rm -f "$PAUSE_FILE"; echo "Pause aufgehoben — System läuft ab nächstem Zyklus wieder."; exit 0 ;;
  status|--status)
    if [ -f "$PAUSE_FILE" ] && [ "$(date +%s)" -lt "$(cat "$PAUSE_FILE" 2>/dev/null || echo 0)" ]; then
      echo "PAUSIERT bis $(date -d @"$(cat "$PAUSE_FILE")" '+%F %T %Z') ($(( ($(cat "$PAUSE_FILE") - $(date +%s)) / 60 )) min verbleibend)"
    else echo "aktiv (keine Pause)"; fi
    exit 0 ;;
esac

HOURS="${1:-24}"
case "$HOURS" in (*[!0-9]*) echo "STUNDEN muss eine Ganzzahl sein"; exit 1;; esac
until=$(date -d "+${HOURS} hours" +%s)
echo "$until" > "$PAUSE_FILE"
echo "Pause gesetzt: bis $(date -d @"$until" '+%F %T %Z') (${HOURS}h)."
echo "→ Laufende Arbeit läuft durch, neue Batches/Card-Tickets werden übersprungen."
echo "→ Auto-Resume nach Ablauf. Vorzeitig beenden: dispatcher-pause.sh clear"
