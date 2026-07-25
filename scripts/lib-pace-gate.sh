#!/bin/bash
# lib-pace-gate.sh — gemeinsame Weekly-Pace-Gate-Logik für Worker + VOCAB-Batch.
# Sourcen: source /opt/development/magic-claude/scripts/lib-pace-gate.sh
#
# pace_ok()  →  Rückgabe 0 = weiterarbeiten, 1 = pausieren.
#
# Prinzip (Variante B):
#   - Pace-Linie = "verstrichener Wochenanteil × PACE_TARGET_PCT". Liegt die
#     7d-Nutzung DARÜBER → Stopp-Auslöser.
#   - Anti-Flatter: einmal ausgelöst, bleibt es AUS bis zum nächsten 20:00
#     (Europe/Zurich) — KEINE Minutentakt-Neubewertung an der Linie.
#   - 5h-Fenster: harte Decke (Rate-Limit-Schutz), nur TRANSIENTER Pause (kein
#     20:00-Lock), weil das 5h-Fenster sich schnell wieder leert.
#   - fail-open: keine Usage-Daten erreichbar → weiterarbeiten (kein Blockieren
#     wegen API-Ausfall).
set -uo pipefail

PACE_TARGET_PCT="${PACE_TARGET_PCT:-90}"      # Wochen-Ziel-Ceiling (Puffer bis 100)
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
_pace_next_resume() {
  local now t
  now=$(date +%s)
  t=$(TZ='Europe/Zurich' date -d "today ${PACE_RESUME_HOUR}:00" +%s 2>/dev/null || echo 0)
  [ "$now" -ge "$t" ] && t=$(TZ='Europe/Zurich' date -d "tomorrow ${PACE_RESUME_HOUR}:00" +%s 2>/dev/null || echo 0)
  echo "$t"
}

pace_ok() {
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

  # (4) Wochen-Pace-Linie → Stopp-Auslöser, dann AUS bis 20:00
  if [ "${_P_R7:-0}" -gt 0 ] 2>/dev/null; then
    elapsed=$(( now - (_P_R7 - PACE_WEEK) ))
    [ "$elapsed" -lt 0 ] && elapsed=0
    [ "$elapsed" -gt "$PACE_WEEK" ] && elapsed=$PACE_WEEK
    allowed=$(( elapsed * PACE_TARGET_PCT / PACE_WEEK ))
    if [ "${_P_U7:-0}" -gt "$allowed" ] 2>/dev/null; then
      _pace_next_resume > "$PACE_OFF_FILE"
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
  local elapsed allowed="n/a"
  if [ "${_P_R7:-0}" -gt 0 ]; then
    elapsed=$(( now - (_P_R7 - PACE_WEEK) )); [ "$elapsed" -lt 0 ] && elapsed=0; [ "$elapsed" -gt "$PACE_WEEK" ] && elapsed=$PACE_WEEK
    allowed=$(( elapsed * PACE_TARGET_PCT / PACE_WEEK ))
  fi
  echo "5h=${_P_U5:-?}% 7d=${_P_U7:-?}% | Pace-erlaubt=${allowed}% (Ziel ${PACE_TARGET_PCT}%)"
  if [ "$off" -gt 0 ] 2>/dev/null && [ "$now" -lt "$off" ]; then
    echo "PACE-PAUSE bis $(TZ='Europe/Zurich' date -d @"$off" '+%F %H:%M %Z')"
  elif [ "$allowed" != "n/a" ] && [ "${_P_U7:-0}" -gt "$allowed" ] 2>/dev/null; then
    echo "→ würde pausieren (aus bis $(TZ='Europe/Zurich' date -d "today ${PACE_RESUME_HOUR}:00" +'%H:%M %Z' 2>/dev/null) CH)"
  else echo "→ läuft (unter Pace)"; fi
}

# Direktaufruf: `bash lib-pace-gate.sh status|ok`  (gesourct: nur Funktionen)
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  case "${1:-status}" in
    ok)     pace_ok && echo OK || echo PAUSE ;;
    *)      pace_status ;;
  esac
fi
