#!/usr/bin/env bash
# Daily REPARSE-FLEET health + statistics report, emailed to dani@sunier.li.
#
# Reparse-era rewrite (2026-08-02): the factory is now dispatcher (:9999) +
# reparse workers + integrator (interactive Fable session or integrator-lite
# cron). The report answers: is anything waiting for human judgment, are the
# workers alive, what landed, how does the card DB move.
#
# Sends via the local Postfix relay (Infomaniak, see setup-mail-relay.sh).
# Cron: 30 6 * * *
set -uo pipefail

REPO="/opt/development/test/openmagic"
LIVE="/opt/development/magic-new"
MAIL_TO="${REPORT_TO:-dani@sunier.li}"
MAIL_FROM="${REPORT_FROM:-dani@sunier.li}"
CREDS="$HOME/.claude/.credentials.json"
DB="/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db"
REVIEW_LIST="$LIVE/.bugfixer-logs/integrator-needs-review.txt"
LITE_LOG="$LIVE/.bugfixer-logs/integrator-lite.log"
STATE="$LIVE/.bugfixer-logs/daily-report-state.txt"

SINCE_GIT=$(date -d '24 hours ago' '+%Y-%m-%d %H:%M')
SINCE_EPOCH=$(date -d '24 hours ago' +%s)
TODAY=$(date '+%Y-%m-%d %H:%M %Z')

# ---- card DB counts (+ delta vs last report) ----
read -r TOT FULL REV <<<"$(python3 - <<'EOF'
import json, glob
tot=full=rev=0
for f in glob.glob('/opt/development/magic-new/backend/data/carddb/*.json'):
    if '/_' in f: continue
    for c in json.load(open(f)).values():
        if not isinstance(c, dict): continue
        tot += 1
        if c.get('status') == 'review': rev += 1
        else: full += 1
print(tot, full, rev)
EOF
)"
D_TOT="?"; D_FULL="?"
if [ -f "$STATE" ]; then
  read -r P_TOT P_FULL _ < "$STATE" || true
  [ -n "${P_TOT:-}" ] && D_TOT=$(( TOT - P_TOT )) && D_FULL=$(( FULL - P_FULL ))
fi
echo "$TOT $FULL $REV" > "$STATE"

# ---- fleet throughput (24h) ----
LANDED=$(git -C "$REPO" log --since="$SINCE_GIT" --oneline --grep='reparse' main 2>/dev/null | grep -vc '^$' || echo 0)
AUTO_LANDED=$(awk -v s="$(date -d '24 hours ago' -Is)" '$0 > "["s && /LANDED \+ deployed/' "$LITE_LOG" 2>/dev/null | wc -l | tr -d ' ')
read -r Q_TODO Q_WORK Q_DONE24 Q_PARK24 <<<"$(python3 - <<EOF
import sqlite3
try:
    db = sqlite3.connect('file:$DB?mode=ro', uri=True, timeout=10)
    todo = db.execute("select count(*) from tickets where state='todo'").fetchone()[0]
    work = db.execute("select count(*) from tickets where state='working'").fetchone()[0]
    done = db.execute("select count(*) from tickets where state='done' and updated_at>$SINCE_EPOCH and title like 'REPARSE%'").fetchone()[0]
    park = db.execute("select count(*) from tickets where state in ('blocked','wait') and updated_at>$SINCE_EPOCH and title like 'REPARSE%'").fetchone()[0]
    print(todo, work, done, park)
except Exception:
    print('? ? ? ?')
EOF
)"

# ---- demand table top 5 ----
DEMAND=$(cd "$REPO" && timeout 180 python3 scripts/paragraph/reparse.py --review-pile 2>/dev/null | sed -n '5,9p')

# ---- health checks ----
WARN=""
# 1) needs-review queue (the judgment inbox — cron cannot land these)
if [ -s "$REVIEW_LIST" ]; then
  WARN="${WARN}🧐 REVIEW NÖTIG ($(wc -l < "$REVIEW_LIST") Branch(es) warten auf interaktive Session):"$'\n'"$(sed 's/^/  /' "$REVIEW_LIST")"$'\n'
fi
# 2) workers alive? (tmux windows + recent log lines)
WORKERS_OK=""
for w in r1 r2; do
  last=$(stat -c %Y "/tmp/orch/reparse-$w.log" 2>/dev/null || echo 0)
  age=$(( $(date +%s) - last ))
  if ! tmux list-windows -t dispatcher -F '#{window_name}' 2>/dev/null | grep -qx "$w"; then
    WARN="${WARN}⚠️  Worker $w: kein tmux-Fenster — Fleet-Relaunch nötig (dispatcher-reparse-launch.sh 2)."$'\n'
  elif [ "$age" -gt 7200 ]; then
    WARN="${WARN}⚠️  Worker $w: seit $((age/60)) min keine Log-Aktivität — hängt evtl."$'\n'
  else
    WORKERS_OK="$WORKERS_OK $w"
  fi
done
# 3) dispatcher reachable
curl -fsS -m5 http://localhost:9999/stats >/dev/null 2>&1 || WARN="${WARN}⚠️  Dispatcher :9999 nicht erreichbar."$'\n'
# 4) auth failures in worker stderr
AUTH_FAILS=$(find /tmp -maxdepth 1 -name 'disp-r*-claude.err' -newermt "$SINCE_GIT" 2>/dev/null \
  | xargs grep -liE 'invalid authentication|failed to authenticate' 2>/dev/null | wc -l | tr -d ' ')
[ "${AUTH_FAILS:-0}" -gt 0 ] && WARN="${WARN}🔑 AUTH-AUSFALL: Worker-Claude-Läufe mit 401 — '/login' in einer Session nötig. HÖCHSTE PRIORITÄT."$'\n'
# 5) regression cron status (letzter Lauf rot?)
REG=$(tail -2 "$LIVE/.bugfixer-logs/regression-cron.log" 2>/dev/null | grep -c 'FAIL' || true)
[ "${REG:-0}" -gt 0 ] && WARN="${WARN}⚠️  Regression-Cron meldet ROT — .bugfixer-logs/regression-cron.log prüfen."$'\n'
[ -z "$WARN" ] && VERDICT="✅ Gesund — Fleet läuft, nichts wartet auf Review." || VERDICT="$WARN"

# ---- usage ----
USAGE="(nicht abrufbar)"
if [ -r "$CREDS" ]; then
  TOK=$(jq -r '.claudeAiOauth.accessToken // empty' "$CREDS" 2>/dev/null)
  if [ -n "$TOK" ]; then
    U=$(curl -fsS --max-time 15 -H "Authorization: Bearer $TOK" \
         -H "anthropic-beta: oauth-2025-04-20" \
         https://api.anthropic.com/api/oauth/usage 2>/dev/null)
    [ -n "$U" ] && USAGE=$(printf '%s' "$U" | jq -r '"5h=\(.five_hour.utilization)%  7d=\(.seven_day.utilization)%  7d-sonnet=\(.seven_day_sonnet.utilization)%"' 2>/dev/null || echo "(parse-Fehler)")
  fi
fi
DISK=$(df -h / | awk 'NR==2{print $5" voll, "$4" frei (von "$2")"}')

# ---- compose ----
SUBJECT="[magefield-fleet] Tagesreport $(date '+%Y-%m-%d') — DB $TOT (+${D_TOT}), $([ -z "$WARN" ] && echo OK || echo 'REVIEW/WARNUNG')"
BODY=$(cat <<EOF
Magefield Reparse-Fleet — Tagesreport
Stand: $TODAY  (Fenster: letzte 24h)

== Gesundheit ==
$VERDICT

== Card-DB ==
  Spielbar gesamt:   $TOT  (${D_TOT:+Δ24h: +$D_TOT})
  Voll implementiert: $FULL  (Δ24h: +${D_FULL})
  Review-Tier:        $REV
  Live-Dashboard:     http://localhost:9999/dashboard

== Fleet (24h) ==
  Tasks gelandet (main):     $LANDED Commits
  davon integrator-lite:     $AUTO_LANDED (unbemannt)
  Dispatcher-Queue:          $Q_TODO todo / $Q_WORK working
  Tickets done/geparkt 24h:  $Q_DONE24 / $Q_PARK24
  Worker aktiv:             ${WORKERS_OK:- KEINE}

== Demand-Table Top 5 (Review-Pile-Blocker) ==
$DEMAND

== Claude Usage ==
  $USAGE

== System ==
  Disk: $DISK

--
Automatischer Report von scripts/kanboard-daily-report.sh (Reparse-Ära)
EOF
)

SUBJECT_ENC="=?UTF-8?B?$(printf '%s' "$SUBJECT" | base64 -w0)?="
BODY_B64=$(printf '%s\n' "$BODY" | base64 -w0)
printf 'Subject: %s\nFrom: magefield-fleet <%s>\nTo: %s\nMIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\nContent-Transfer-Encoding: base64\n\n%s\n' \
  "$SUBJECT_ENC" "$MAIL_FROM" "$MAIL_TO" "$BODY_B64" \
  | /usr/sbin/sendmail -f "$MAIL_FROM" -t

echo "[$(date -Is)] report sent to $MAIL_TO (landed=$LANDED warn=$([ -z "$WARN" ] && echo no || echo yes))"
