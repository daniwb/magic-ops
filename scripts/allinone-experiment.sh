#!/bin/bash
# allinone-experiment.sh — EIN Card-Worker, der alles selbst macht.
#
# Frage: ist "eine Session baut Primitiv UND Karte" billiger als der heutige
# Split? Heute kostet eine Karte, der ein Primitiv fehlt, DREI Sessions:
#   1. Park-Run     — voller Katalog (~93k Token/Turn), liefert KEINE Karte
#   2. VOCAB-Batch  — 2 Claude-Calls (100 + 60 Turns) für das Primitiv
#   3. Requeue-Run  — voller Katalog NOCHMAL, jetzt baut er die Karte
# Der All-in-One-Modus bezahlt den Katalog-Kontext nur EINMAL und spart die
# Übergaben — dafür braucht er mehr Turns pro Session (Engine-Exploration).
# Welche Seite gewinnt, ist offen; genau das soll gemessen werden.
#
# NICHT AUTOMATISCH STARTEN. Bewusst ein einzelner Worker: er teilt sich die
# Queue mit den laufenden orch-1/orch-2, und 3+ parallele Worker sind laut
# eigener Messung kontraproduktiv (62% Rate-Limit-Fehler).
#
#   starten : bash allinone-experiment.sh start
#   stoppen : bash allinone-experiment.sh stop
#   messen  : bash allinone-experiment.sh report
set -uo pipefail

WORKER_ID="${WORKER_ID:-allin-1}"
CLONE="/tmp/work/$WORKER_ID"
LOG="/tmp/orch/$WORKER_ID.log"
PIDF="/tmp/orch/$WORKER_ID.pgid"
WORKER=/opt/development/magic-claude/scripts/dispatcher-worker-real.sh
MARK="/tmp/orch/$WORKER_ID.started-at"   # Startzeitpunkt = Beginn des Messfensters

case "${1:-}" in
  start)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "$WORKER_ID läuft bereits (pgid $(cat "$PIDF"))"; exit 0
    fi
    mkdir -p /tmp/orch; rm -rf "$CLONE"; mkdir -p "$CLONE"
    date +%s > "$MARK"
    # ALLINONE=1 ist der einzige Verhaltensunterschied; alles andere (Gates,
    # Fix-Loop, Fast-Gate, merge_deploy_push, Token-Buchhaltung) ist identisch
    # zu orch-1/orch-2 — sonst würde der Vergleich zwei Dinge zugleich messen.
    setsid bash -c "
      while true; do
        ALLINONE=1 bash '$WORKER' '$WORKER_ID' '$CLONE' >> '$LOG' 2>&1
        echo \"[\$(date -Is)] $WORKER_ID cycle end, restart 10s\" >> '$LOG'
        sleep 10
      done
    " >/dev/null 2>&1 &
    echo $! > "$PIDF"
    echo "$WORKER_ID gestartet (ALLINONE=1, pgid $(cat "$PIDF")). Messfenster ab $(date -Is)."
    echo "Auswerten mit: bash $0 report"
    ;;
  stop)
    pg=$(cat "$PIDF" 2>/dev/null || echo "")
    if [ -n "$pg" ]; then
      kill -TERM -- -"$pg" 2>/dev/null; sleep 3; kill -KILL -- -"$pg" 2>/dev/null
      rm -f "$PIDF"; echo "$WORKER_ID gestoppt"
    else
      echo "$WORKER_ID läuft nicht"
    fi
    ;;
  report)
    SINCE="${2:-$(cat "$MARK" 2>/dev/null || echo 0)}"
    python3 - "$WORKER_ID" "$SINCE" <<'PY'
import sqlite3, sys, statistics
wid, since = sys.argv[1], int(sys.argv[2])
db = sqlite3.connect('file:/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db?mode=ro', uri=True)

def cards(worker):
    return db.execute("""select id,title,coalesce(tokens,0),state from tickets
        where worker_id=? and updated_at>? and tokens>0""", (worker, since)).fetchall()

print(f"=== All-in-One vs. Split — Tickets seit epoch {since} ===\n")
print(f"{'mode':22} {'geliefert':>9} {'geparkt':>8} {'tok/karte':>11} {'tok total':>10}")
rows_all = cards(wid)
# Vergleichsgruppe: die normalen Worker im GLEICHEN Zeitfenster, gleiche Queue.
rows_split = [r for w in ('orch-1','orch-2') for r in cards(w)]

def line(label, rows, extra_tok=0):
    if not rows:
        print(f"{label:22} {'(keine Daten)':>9}"); return
    done   = [r for r in rows if r[3] == 'done']
    parked = [r for r in rows if r[3] in ('blocked','wait')]
    tot    = sum(r[2] for r in rows) + extra_tok
    per    = tot/len(done) if done else float('nan')
    print(f"{label:22} {len(done):>9} {len(parked):>8} {per/1e6:>10.2f}M {tot/1e6:>9.1f}M")

line("all-in-one", rows_all)

# Der Split ist NUR ehrlich vergleichbar, wenn die VOCAB-Builds mitgezählt
# werden, die seine Parks ausgelöst haben — sonst sieht Parken gratis aus.
vocab_tok = db.execute("""select coalesce(sum(tokens),0) from tickets
    where type='vocab' and updated_at>?""", (since,)).fetchone()[0]
line("split (nur Karten)", rows_split)
line("split + VOCAB-Kosten", rows_split, vocab_tok)
print(f"\n  VOCAB-Token im Fenster (dem Split zugerechnet): {vocab_tok/1e6:.1f}M")

built = db.execute("""select count(*) from events where ts>? and msg like '%PRIMITIVE_BUILT%'""",(since,)).fetchone()[0]
print(f"  Primitive vom All-in-One-Worker gebaut: {built}")
print("\n  Hinweis: kleine Stichproben und ungleiche Ticket-Schwierigkeit machen")
print("  das RICHTUNGSWEISEND, nicht beweisend. Erst ab ~20 gelieferten Karten")
print("  pro Seite ernst nehmen.")
PY
    ;;
  *)
    echo "usage: $0 {start|stop|report [since_epoch]}"; exit 2 ;;
esac
