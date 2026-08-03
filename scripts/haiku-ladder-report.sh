#!/bin/bash
# haiku-ladder-report.sh — kann Haiku Karten selbst bauen?
#
# Aufbau: orch-2 fährt HAIKU_ROUNDS=2 (Versuch 1+2 Haiku, erst Versuch 3
# Sonnet), orch-1 bleibt unverändert Sonnet-first. Gleiche Queue, gleiche
# Zeit, gleiche Gates — der einzige Unterschied ist die Modell-Leiter.
#
# Schiedsrichter ist das FAST-GATE (go build + die neuen Tests), nicht das
# Modell selbst. "Haiku hat es gebaut" heisst hier: ein Haiku-Versuch kam
# durchs Gate, ohne dass auf Sonnet eskaliert wurde.
#
# Usage: haiku-ladder-report.sh [SEIT_EPOCH]   (default: letzte 24h)
set -uo pipefail
SINCE_EPOCH="${1:-$(( $(date +%s) - 86400 ))}"
SINCE_HM=$(date -d @"$SINCE_EPOCH" '+%H:%M:%S')
SINCE_DAY=$(date -d @"$SINCE_EPOCH" '+%Y-%m-%d')

echo "=== Haiku-Leiter (orch-2, HAIKU_ROUNDS=$(cat /opt/development/magic-ops/haiku-rounds-orch-2 2>/dev/null || echo 0)) vs Sonnet-first (orch-1) ==="
echo "    seit $SINCE_DAY $SINCE_HM"
echo

# Ein Ticket-Zyklus im Log sieht so aus:
#   ticket #N ... / attempt 1/3 (model X) [/ attempt 2/3 ...] / <Ausgang>
# Ausgang zählt nur, wenn er NACH SINCE liegt.
# Log-Zeilen tragen nur HH:MM:SS ohne Datum — ein Zeit-Vergleich würde auch
# Vortage treffen (genau das hat die erste Version dieses Reports getan und
# 79 "Tickets" gezählt, die gar nicht zum Experiment gehörten). Deshalb ein
# ZEILEN-Marker, der beim Aktivieren der Leiter gesetzt wird.
for w in orch-2 orch-1; do
  short=$([ "$w" = orch-1 ] && echo card-1 || echo card-2)
  log="/tmp/orch/$short.log"
  marker="/tmp/orch/haiku-ladder-start-$short"
  [ -f "$log" ] || { echo "  $w: kein Log"; continue; }
  start=$(cat "$marker" 2>/dev/null || echo 1)
  tail -n +"$start" "$log" | awk -v worker="$w" '
    {
      if ($0 ~ /ticket #/)         { tickets++; haiku=0; esc=0 }
      if ($0 ~ /attempt .*haiku/)  { haiku=1 }
      if ($0 ~ /attempt .*sonnet/) { if (haiku) esc=1 }
      if ($0 ~ /fast-gate grün/) {
        green++
        if (esc)        esc_green++
        else if (haiku) haiku_green++
        else            sonnet_green++
      }
      if ($0 ~ /Versuche gescheitert|wait-triage/) failed++
      if ($0 ~ /parked: missing primitive/)        parked++
    }
    END{
      printf "  %-7s Tickets=%-4d gate-gruen=%-4d  nur-Haiku=%-3d eskaliert=%-3d direkt-Sonnet=%-3d geparkt=%-3d gescheitert=%d\n", \
             worker, tickets+0, green+0, haiku_green+0, esc_green+0, sonnet_green+0, parked+0, failed+0
      if (haiku_green+esc_green > 0)
        printf "            -> Haiku schaffte es allein in %.0f%% der Faelle (%d von %d)\n", \
               100*haiku_green/(haiku_green+esc_green), haiku_green, haiku_green+esc_green
    }'
  echo
done

echo "=== Token/Ticket im selben Fenster (aus der DB) ==="
python3 - "$SINCE_EPOCH" <<'PY'
import sqlite3, sys, statistics
since=int(sys.argv[1])
db=sqlite3.connect('file:/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db?mode=ro',uri=True)
for w in ('orch-2','orch-1'):
    r=db.execute("""select coalesce(tokens,0),state from tickets
        where worker_id=? and updated_at>? and tokens>0""",(w,since)).fetchall()
    if not r: print(f"  {w}: noch keine Daten"); continue
    tok=[x[0] for x in r]; done=sum(1 for x in r if x[1]=='done')
    lbl = "Haiku-Leiter" if w=='orch-2' else "Sonnet-first"
    print(f"  {w} ({lbl:12}) n={len(r):3d} median={statistics.median(tok)/1e6:5.2f}M "
          f"mean={statistics.mean(tok)/1e6:5.2f}M done={100*done/len(r):3.0f}%")
print("\n  Achtung: kleine Stichprobe und ungleiche Ticket-Schwierigkeit —")
print("  erst ab ~20 gelieferten Karten je Arm belastbar.")
PY
