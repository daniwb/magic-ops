#!/bin/bash
# lib-pace-gate-codex.sh — Codex counterpart to lib-pace-gate.sh.
#
# Same Variante-C day-tranche principle (Dani 2026-07-27, see lib-pace-gate.sh
# for the full rationale) applied to Codex's account rate-limit window instead
# of Claude's: day-N of the real quota window unlocks N/7 of the budget at
# the window's own reset boundary. No public `codex` CLI flag exposes usage
# (checked 2026-08-16, codex-cli 0.147.0) — codex-usage-fetch.py gets it via
# the `codex app-server` JSON-RPC `account/rateLimits/read` method (the same
# call the interactive TUI's own status bar uses internally).
#
# Only ONE window observed live on this account's `plus` plan (`primary`,
# windowDurationMins=10080 = 7 days — no `secondary`). If a `secondary`
# window IS present on another plan, treat it as a flat hard-ceiling guard
# (no day/night relaxation — that was Claude-5h-specific tuning, not
# re-derived here); absent, skip it (fail-open on that check only).
#
# pace_ok() → 0 = keep working, 1 = pause. Same external interface as
# lib-pace-gate.sh so pipeline-lane.sh can source either by engine.
set -uo pipefail

PACE_TARGET_PCT="${PACE_TARGET_PCT:-100}"
PACE_HARD_SECONDARY="${PACE_HARD_SECONDARY:-95}"
CODEX_USAGE_CACHE="${CODEX_USAGE_CACHE:-/tmp/codex-usage-gate.json}"
CODEX_USAGE_GATE_TTL="${CODEX_USAGE_GATE_TTL:-180}"
CODEX_PACE_OFF_FILE="${CODEX_PACE_OFF_FILE:-/tmp/orch/codex-pace-off-until}"
CODEX_USAGE_FETCH="${CODEX_USAGE_FETCH:-/opt/development/magic-ops/scripts/codex-usage-fetch.py}"

_cpace_refresh_usage() {
  local now age
  now=$(date +%s); age=99999
  [ -s "$CODEX_USAGE_CACHE" ] && age=$(( now - $(stat -c %Y "$CODEX_USAGE_CACHE" 2>/dev/null || echo 0) ))
  if [ "$age" -ge "$CODEX_USAGE_GATE_TTL" ]; then
    if body=$(timeout 20 python3 "$CODEX_USAGE_FETCH" 2>/dev/null) && printf '%s' "$body" | jq -e '.used_pct' >/dev/null 2>&1; then
      printf '%s' "$body" > "$CODEX_USAGE_CACHE"
    elif [ "$age" -ge 1800 ]; then
      _CP_BLIND=1; return 0
    fi
  fi
  [ -s "$CODEX_USAGE_CACHE" ] || { _CP_BLIND=1; return 0; }
  local u r sec_u sec_r
  u=$(jq -r '.used_pct // 0 | floor' "$CODEX_USAGE_CACHE" 2>/dev/null || echo 0)
  r=$(jq -r '.resets_at // 0' "$CODEX_USAGE_CACHE" 2>/dev/null || echo 0)
  sec_u=$(jq -r '.secondary_used_pct // empty' "$CODEX_USAGE_CACHE" 2>/dev/null)
  sec_r=$(jq -r '.secondary_resets_at // empty' "$CODEX_USAGE_CACHE" 2>/dev/null)
  [ "$r" -gt 0 ] 2>/dev/null && [ "$now" -ge "$r" ] && u=0
  _CP_U=$u; _CP_R=$r; _CP_SEC_U="${sec_u:-}"; _CP_BLIND=0
}

# Window-agnostic day-tranche math (same formula as lib-pace-gate.sh's
# _pace_day_bounds, generalized off the window's OWN length instead of a
# hardcoded 7-day constant — Codex's primary window is 10080min=7d on this
# plan, but this stays correct if that ever differs).
_cpace_day_bounds() { # $1=reset-ts $2=window-seconds
  local rts="$1" wsec="$2" now ws elapsed days
  now=$(date +%s)
  ws=$(( rts - wsec ))
  elapsed=$(( now - ws )); [ "$elapsed" -lt 0 ] && elapsed=0
  days=$(( wsec / 86400 )); [ "$days" -lt 1 ] && days=1
  _CP_DAY=$(( elapsed / 86400 + 1 )); [ "$_CP_DAY" -gt "$days" ] && _CP_DAY=$days
  _CP_ALLOWED=$(( (_CP_DAY * PACE_TARGET_PCT * 10 / days + 5) / 10 ))
  [ "$_CP_ALLOWED" -gt "$PACE_TARGET_PCT" ] && _CP_ALLOWED=$PACE_TARGET_PCT
  _CP_NEXTDAY=$(( ws + _CP_DAY * 86400 ))
  [ "$_CP_NEXTDAY" -gt "$rts" ] && _CP_NEXTDAY=$rts
}

pace_ok_codex() {
  [ "${PACE_DISABLE:-0}" = "1" ] && return 0
  local now off
  now=$(date +%s)
  mkdir -p "$(dirname "$CODEX_PACE_OFF_FILE")" 2>/dev/null || true

  off=$(cat "$CODEX_PACE_OFF_FILE" 2>/dev/null || echo 0); off=${off:-0}
  if [ "$off" -gt 0 ] 2>/dev/null && [ "$now" -lt "$off" ]; then return 1; fi
  [ "$off" -gt 0 ] 2>/dev/null && rm -f "$CODEX_PACE_OFF_FILE"

  _CP_U=0; _CP_R=0; _CP_SEC_U=""; _CP_BLIND=0
  _cpace_refresh_usage
  [ "${_CP_BLIND:-0}" = 1 ] && return 0

  # flat hard ceiling on a secondary window, if this plan reports one
  if [ -n "${_CP_SEC_U:-}" ] && [ "${_CP_SEC_U}" -ge "$PACE_HARD_SECONDARY" ] 2>/dev/null; then
    return 1
  fi

  if [ "${_CP_R:-0}" -gt 0 ] 2>/dev/null; then
    local wmins wsec
    wmins=$(jq -r '.window_mins // 10080' "$CODEX_USAGE_CACHE" 2>/dev/null || echo 10080)
    wsec=$(( wmins * 60 ))
    _cpace_day_bounds "${_CP_R}" "$wsec"
    if [ "${_CP_U:-0}" -ge "${_CP_ALLOWED}" ] 2>/dev/null; then
      echo "${_CP_NEXTDAY}" > "$CODEX_PACE_OFF_FILE"
      return 1
    fi
  fi
  return 0
}

pace_status_codex() {
  local now off; now=$(date +%s)
  _CP_U=0; _CP_R=0; _CP_SEC_U=""; _CP_BLIND=0; _cpace_refresh_usage
  off=$(cat "$CODEX_PACE_OFF_FILE" 2>/dev/null || echo 0); off=${off:-0}
  local allowed="n/a" day="?" nextday=0
  if [ "${_CP_R:-0}" -gt 0 ]; then
    local wmins wsec
    wmins=$(jq -r '.window_mins // 10080' "$CODEX_USAGE_CACHE" 2>/dev/null || echo 10080)
    wsec=$(( wmins * 60 ))
    _cpace_day_bounds "${_CP_R}" "$wsec"
    allowed=$_CP_ALLOWED; day=$_CP_DAY; nextday=$_CP_NEXTDAY
  fi
  echo "primary=${_CP_U:-?}% secondary=${_CP_SEC_U:-n/a}% | Tag ${day} -> erlaubt ${allowed}% (Ziel ${PACE_TARGET_PCT}%)"
  [ "$nextday" -gt 0 ] 2>/dev/null && \
    echo "naechste Stufe: $(date -d @"$nextday" '+%F %H:%M %Z' 2>/dev/null)"
  if [ "$off" -gt 0 ] 2>/dev/null && [ "$now" -lt "$off" ]; then
    echo "PACE-PAUSE bis $(date -d @"$off" '+%F %H:%M %Z' 2>/dev/null)"
  elif [ "$allowed" != "n/a" ] && [ "${_CP_U:-0}" -ge "$allowed" ] 2>/dev/null; then
    echo "-> wuerde pausieren"
  else echo "-> laeuft"; fi
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  case "${1:-status}" in
    ok)     pace_ok_codex && echo OK || echo PAUSE ;;
    *)      pace_status_codex ;;
  esac
fi
