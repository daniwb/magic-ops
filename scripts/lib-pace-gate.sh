#!/bin/bash
# lib-pace-gate.sh — gemeinsame Weekly-Pace-Gate-Logik für Worker + VOCAB-Batch.
# Sourcen: source /opt/development/magic-claude/scripts/lib-pace-gate.sh
#
# pace_ok()  →  Rückgabe 0 = weiterarbeiten, 1 = pausieren.
#
# Prinzip (Variante C — TAGES-STUFEN, User-Entscheid 2026-07-27):
#   - Das Wochenbudget wird NICHT kontinuierlich, sondern in 7 TAGESSTUFEN
#     freigegeben. Jede Stufe schaltet an der 20:00-CH-Grenze (= dem Anker des
#     echten Quota-Fensters, r7 - 7d) eine weitere Siebtel-Tranche frei:
#         Tag 1 → 14%   Tag 2 → 29%   Tag 3 → 43%   Tag 4 → 57%
#         Tag 5 → 71%   Tag 6 → 86%   Tag 7 → 100%
#     Ist die 7d-Nutzung über der Stufe des laufenden Tages → Stopp bis zur
#     nächsten 20:00-Grenze (dann gibt die nächste Stufe wieder Luft).
#   - Warum Stufen statt Linie: die frühere kontinuierliche Linie
#     ("verstrichener Wochenanteil × TARGET") lag bei TARGET=100 praktisch
#     DECKUNGSGLEICH mit der tatsächlichen Nutzung — schon 1% Überschuss
#     (73% vs. 72%) löste einen vollen Tages-Lock aus (Vorfall 2026-07-27,
#     Worker standen still). Stufen geben pro Tag bewusst Vorlauf: man darf
#     die Tagestranche am Stück verbrauchen und wartet dann bis zum Reset.
#   - Anti-Flatter ist damit inhärent: Pause endet exakt an der nächsten
#     Tagesgrenze, keine Minutentakt-Neubewertung.
#   - 5h-Fenster: harte Decke (Rate-Limit-Schutz), nur TRANSIENTER Pause (kein
#     Tages-Lock), weil das 5h-Fenster sich schnell wieder leert.
#   - fail-open: keine Usage-Daten erreichbar → weiterarbeiten (kein Blockieren
#     wegen API-Ausfall).
set -uo pipefail

PACE_TARGET_PCT="${PACE_TARGET_PCT:-100}"     # Wochen-Ziel-Ceiling (User-Entscheid 2026-07-27: voll ausnutzen statt 90er-Puffer)
PACE_HARD5="${PACE_HARD5:-95}"                # 5h-Decke (nachts 23-06 CH = 100)
PACE_RESUME_HOUR="${PACE_RESUME_HOUR:-20}"    # Wiederanlauf-Stunde (Europe/Zurich)
PACE_WEEK="${PACE_WEEK:-604800}"             # 7 Tage in s
USAGE_CACHE="${USAGE_CACHE:-/tmp/claude-usage-gate.json}"
USAGE_GATE_TTL="${USAGE_GATE_TTL:-180}"
PACE_OFF_FILE="${PACE_OFF_FILE:-/tmp/orch/pace-off-until}"

# Interner Usage-Refresh (gecacht, TTL). Setzt _P_U5 _P_U7 (0..100).
_pace_refresh_usage() {
  local now age tok body
  now=$(date +%s); age=99999
  [ -s "$USAGE_CACHE" ] && age=$(( now - $(stat -c %Y "$USAGE_CACHE" 2>/dev/null || echo 0) ))
  if [ "$age" -ge "$USAGE_GATE_TTL" ]; then
    tok=$(jq -r '.claudeAiOauth.accessToken // empty' "$HOME/.claude/.credentials.json" 2>/dev/null || true)
    if [ -n "$tok" ] && body=$(curl -fsS --max-time 15 -H "Authorization: Bearer $tok" \
         -H "anthropic-beta: oauth-2025-04-20" https://api.anthropic.com/api/oauth/usage 2>/dev/null) \
       && printf '%s' "$body" | jq -e '.seven_day' >/dev/null 2>&1; then
      printf '%s' "$body" > "$USAGE_CACHE"
    elif [ "$age" -ge 1800 ]; then
      _P_BLIND=1; return 0    # zu lange blind → fail-open
    fi
  fi
  [ -s "$USAGE_CACHE" ] || { _P_BLIND=1; return 0; }
  local u5 u7 r5 r7
  u5=$(jq -r '.five_hour.utilization // 0 | floor' "$USAGE_CACHE" 2>/dev/null || echo 0)
  u7=$(jq -r '.seven_day.utilization // 0 | floor' "$USAGE_CACHE" 2>/dev/null || echo 0)
  r5=$(date -d "$(jq -r '.five_hour.resets_at // empty' "$USAGE_CACHE" 2>/dev/null)" +%s 2>/dev/null || echo 0)
  r7=$(date -d "$(jq -r '.seven_day.resets_at // empty' "$USAGE_CACHE" 2>/dev/null)" +%s 2>/dev/null || echo 0)
  # abgelaufene Fenster zählen als 0
  [ "$r5" -gt 0 ] && [ "$now" -ge "$r5" ] && u5=0
  [ "$r7" -gt 0 ] && [ "$now" -ge "$r7" ] && u7=0
  _P_U5=$u5; _P_U7=$u7; _P_R7=$r7; _P_BLIND=0
}

# Nächster Wiederanlauf-Zeitpunkt (heute HH:00 CH, sonst morgen).
# NUR noch Fallback, wenn _P_R7 (Quota-Reset) fehlt — der Normalfall rechnet
# die Tagesgrenze aus dem Quota-Anker (_pace_day_bounds).
_pace_next_resume() {
  local now t
  now=$(date +%s)
  t=$(TZ='Europe/Zurich' date -d "today ${PACE_RESUME_HOUR}:00" +%s 2>/dev/null || echo 0)
  [ "$now" -ge "$t" ] && t=$(TZ='Europe/Zurich' date -d "tomorrow ${PACE_RESUME_HOUR}:00" +%s 2>/dev/null || echo 0)
  echo "$t"
}

# Tages-Stufen-Rechnung. Setzt:
#   _P_DAY      laufender Tag im Quota-Fenster, 1..7
#   _P_ALLOWED  freigegebenes Budget in % für diesen Tag  = round(DAY * TARGET / 7)
#   _P_NEXTDAY  Unix-ts der nächsten Tagesgrenze (= Wiederanlauf, wenn gestoppt)
# Anker ist der ECHTE Quota-Reset (_P_R7 - 7d), nicht "20:00 lokal" — dadurch
# bleiben Stufen und Quota-Fenster auch über Sommer-/Winterzeit synchron.
_pace_day_bounds() { # $1=r7(reset-ts)
  local r7="$1" now ws elapsed
  now=$(date +%s)
  ws=$(( r7 - PACE_WEEK ))
  elapsed=$(( now - ws )); [ "$elapsed" -lt 0 ] && elapsed=0
  _P_DAY=$(( elapsed / 86400 + 1 )); [ "$_P_DAY" -gt 7 ] && _P_DAY=7
  # round-half-up statt Abschneiden: Tag 6 → 85.7 → 86 (nicht 85)
  _P_ALLOWED=$(( (_P_DAY * PACE_TARGET_PCT * 10 / 7 + 5) / 10 ))
  [ "$_P_ALLOWED" -gt "$PACE_TARGET_PCT" ] && _P_ALLOWED=$PACE_TARGET_PCT
  _P_NEXTDAY=$(( ws + _P_DAY * 86400 ))
  [ "$_P_NEXTDAY" -gt "$r7" ] && _P_NEXTDAY=$r7
}

pace_ok() {
  # PACE_DISABLE=1 — expliziter Override (manuelle Test-Läufe, Dani 2026-08-02):
  # ignoriert Off-Datei UND Wochen-Pacing. Bewusst NUR per Env setzbar,
  # damit kein Dauerzustand entsteht.
  [ "${PACE_DISABLE:-0}" = "1" ] && return 0
  local now off nh lim5 elapsed allowed
  now=$(date +%s)
  mkdir -p "$(dirname "$PACE_OFF_FILE")" 2>/dev/null || true

  # (1) Anti-Flatter: laufende geplante Off-Phase → pausieren, NICHT neu bewerten
  off=$(cat "$PACE_OFF_FILE" 2>/dev/null || echo 0); off=${off:-0}
  if [ "$off" -gt 0 ] 2>/dev/null && [ "$now" -lt "$off" ]; then return 1; fi
  [ "$off" -gt 0 ] 2>/dev/null && rm -f "$PACE_OFF_FILE"   # abgelaufen → frei, neu bewerten

  # (2) Usage holen (gecacht)
  _P_U5=0; _P_U7=0; _P_R7=0; _P_BLIND=0
  _pace_refresh_usage
  [ "${_P_BLIND:-0}" = 1 ] && return 0   # keine Daten → fail-open (weiter)

  # (3) 5h-Decke: transienter Rate-Limit-Schutz (kein 20:00-Lock)
  nh=$(TZ='Europe/Zurich' date +%H); nh=$((10#$nh)); lim5=$PACE_HARD5
  { [ "$nh" -ge 23 ] || [ "$nh" -lt 6 ]; } && lim5=100
  [ "${_P_U5:-0}" -ge "$lim5" ] 2>/dev/null && return 1

  # (4) Tages-Stufe → Stopp-Auslöser, dann AUS bis zur nächsten Tagesgrenze
  if [ "${_P_R7:-0}" -gt 0 ] 2>/dev/null; then
    _pace_day_bounds "${_P_R7}"
    # -ge, NICHT -gt: bei Verbrauch == Tages-Stufe ist das Tagesbudget genau
    # aufgebraucht, nicht "noch frei". Mit -gt lief die Fabrik bei 29% Verbrauch
    # gegen 29% erlaubt weiter (Tag 2/7) und stoppte erst bei 30% — eine ganze
    # Prozentstufe zu spät, und der Status meldete dabei "unter Tages-Stufe",
    # obwohl er exakt AUF der Stufe stand.
    if [ "${_P_U7:-0}" -ge "${_P_ALLOWED}" ] 2>/dev/null; then
      echo "${_P_NEXTDAY}" > "$PACE_OFF_FILE"
      return 1
    fi
  fi
  return 0
}

# Für Diagnose/CLI: kompakter Status
pace_status() {
  local now off; now=$(date +%s)
  _P_U5=0; _P_U7=0; _P_R7=0; _P_BLIND=0; _pace_refresh_usage
  off=$(cat "$PACE_OFF_FILE" 2>/dev/null || echo 0); off=${off:-0}
  local allowed="n/a" day="?" nextday=0
  if [ "${_P_R7:-0}" -gt 0 ]; then
    _pace_day_bounds "${_P_R7}"
    allowed=$_P_ALLOWED; day=$_P_DAY; nextday=$_P_NEXTDAY
  fi
  echo "5h=${_P_U5:-?}% 7d=${_P_U7:-?}% | Tag ${day}/7 → erlaubt ${allowed}% (Ziel ${PACE_TARGET_PCT}%)"
  [ "$nextday" -gt 0 ] 2>/dev/null && \
    echo "nächste Stufe: $(TZ='Europe/Zurich' date -d @"$nextday" '+%F %H:%M %Z')"
  if [ "$off" -gt 0 ] 2>/dev/null && [ "$now" -lt "$off" ]; then
    echo "PACE-PAUSE bis $(TZ='Europe/Zurich' date -d @"$off" '+%F %H:%M %Z')"
  elif [ "$allowed" != "n/a" ] && [ "${_P_U7:-0}" -ge "$allowed" ] 2>/dev/null; then
    echo "→ würde pausieren (aus bis $(TZ='Europe/Zurich' date -d @"$nextday" '+%F %H:%M %Z' 2>/dev/null))"
  else echo "→ läuft (unter Tages-Stufe, Stopp bei >=)"; fi
}

# Direktaufruf: `bash lib-pace-gate.sh status|ok`  (gesourct: nur Funktionen)
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  case "${1:-status}" in
    ok)     pace_ok && echo OK || echo PAUSE ;;
    *)      pace_status ;;
  esac
fi
