#!/bin/bash
# A/B-Auswertung: Katalog-Modus "headings" (orch-1) vs "index" (orch-2).
#
# Hintergrund (gemessen 2026-07-29): der statische Katalog geht PRO TURN in den
# System-Prompt. index = 92846 tok/Turn, headings = 41935 tok/Turn (-55%).
# Offene Frage ist NICHT die Token-Ersparnis (die ist belegt), sondern ob
# "headings" die Qualität kostet: sieht das Modell ohne Eintragsliste nicht mehr,
# dass ein Primitiv existiert -> mehr falsche MISSING_PRIMITIVE/[VOCAB]?
#
# Entscheidungsregel: headings gewinnt, wenn tok/Ticket deutlich sinkt UND die
# Park-/VOCAB-Rate NICHT nennenswert steigt. Steigt sie, ist die Ersparnis
# erkauft (jedes falsche [VOCAB] kostet ~3M einmalig + ~1M/Woche Dauer-Steuer).
#
# Usage: catalog-ab-report.sh [SEIT_EPOCH]   (default: letzte 24h)
set -uo pipefail
DB="${DB:-/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db}"
SINCE="${1:-$(( $(date +%s) - 86400 ))}"

echo "=== Katalog-A/B — Tickets seit $(date -d @"$SINCE" -Is) ==="
WORKERS=""
for f in /opt/development/magic-ops/catalog-mode-*; do
  [ -e "$f" ] || continue
  id="${f##*/catalog-mode-}"
  echo "  $id = $(cat "$f")"
  WORKERS="$WORKERS $id"
done
WORKERS="$(echo $WORKERS)"
echo

python3 - "$DB" "$SINCE" $WORKERS <<'PY'
import sqlite3, sys, statistics
db = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True); since=int(sys.argv[2])
workers = sys.argv[3:] or ['orch-1','orch-2']
print(f"{'worker':8} {'n':>4} {'median tok':>11} {'mean tok':>10} {'parked':>7} {'park%':>6}")
for w in workers:
    rows=db.execute("""select coalesce(tokens,0), state from tickets
        where worker_id=? and updated_at>? and tokens>0""",(w,since)).fetchall()
    if not rows: print(f"{w:8} {0:>4}   (noch keine Daten)"); continue
    tok=[r[0] for r in rows]
    parked=sum(1 for r in rows if r[1] in ('blocked','wait'))
    print(f"{w:8} {len(tok):>4} {statistics.median(tok)/1e6:>10.2f}M {statistics.mean(tok)/1e6:>9.2f}M "
          f"{parked:>7} {100*parked/len(rows):>5.0f}%")
print()
# neue [VOCAB]-Tickets, die JEDER Worker ausgelöst hat (Qualitäts-Signal)
for w in workers:
    n=db.execute("""select count(*) from tickets where title like '[VOCAB]%' and created_at>?
        and id in (select vocab_id from tickets where worker_id=? and vocab_id is not null)""",
        (since,w)).fetchone()[0]
    print(f"  neue [VOCAB] ausgelöst von {w}: {n}")
PY

echo
echo "=== tatsächliche Turns pro Lauf (num_turns, seit 2026-07-29 instrumentiert) ==="
for w in $WORKERS; do
  f="/tmp/disp-$w-turns.log"
  if [ -s "$f" ]; then
    printf "  %-7s " "$w"
    awk '{for(i=1;i<=NF;i++) if($i ~ /^turns=/){split($i,a,"=");
          if(a[2] ~ /^[0-9]+$/){s+=a[2]; n++; if(a[2]>mx)mx=a[2]}}}
         END{if(n) printf "runs=%d  avg_turns=%.1f  max=%d\n", n, s/n, mx; else print "keine Turn-Daten"}' "$f"
  else
    printf "  %-7s noch keine Turn-Daten\n" "$w"
  fi
done
