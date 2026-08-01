#!/bin/bash
# Orchestrator: alterniert zwischen CARD-Phase und VOCAB-Phase.
#
#   CARD-Phase : 2 Card-Worker (dispatcher-worker-real.sh) bauen Karten-Handler.
#                Diese erzeugen VOCAB-Bedarf. Sobald offene VOCAB (?all=1) >=
#                VOCAB_HIGH (100), Card-Worker stoppen → VOCAB-Phase.
#   VOCAB-Phase: dispatcher-vocab-batch.sh baut in 5er-Batches bis VOCAB == 0
#                (oder alle Rest-VOCAB skip-gelistet = STUCK) → zurück CARD-Phase.
#
# Usage-Gate: bei Claude 5h/7d-Limit wird ALLES pausiert (auto-resume nach Reset).
# Card-Worker laufen als eigene Prozessgruppe (setsid) → sauber killbar ohne
# fremde claude-Prozesse zu treffen. Phasen sind exklusiv (nie beides gleichzeitig).
set -uo pipefail

export PATH=/usr/local/go/bin:$PATH
DISP="${DISP:-http://localhost:9999}"
CARD_WORKER="/opt/development/magic-claude/scripts/dispatcher-worker-real.sh"
VOCAB_BATCH="/opt/development/magic-claude/scripts/dispatcher-vocab-batch.sh"
VOCAB_HIGH="${VOCAB_HIGH:-100}"      # Card→Vocab Umschaltschwelle
VOCAB_LOW="${VOCAB_LOW:-0}"          # Vocab→Card Drain-Ziel
POLL="${POLL:-60}"                   # Sekunden zwischen Zähl-Checks (Card-Phase)
USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-99}"   # 95->99 (2026-07-29): 7d-Fenster lief sonst
                                           # am letzten Wochentag ungenutzt aus
STATE_DIR="/tmp/orch"; mkdir -p "$STATE_DIR"
PHASE_FILE="$STATE_DIR/phase"

log() { printf '[%s] orch: %s\n' "$(date -Is)" "$*"; }

# --- Manuelle Pause (persistent, auto-resume nach Ablauf) -------------------
PAUSE_FILE="${PAUSE_FILE:-/opt/development/magic-claude/.orch-pause-until}"
paused() { [ -f "$PAUSE_FILE" ] && [ "$(date +%s)" -lt "$(cat "$PAUSE_FILE" 2>/dev/null || echo 0)" ]; }
pause_gate() {  # blockiert (Card-Worker gestoppt) solange Pause aktiv
  paused || return 0
  log "Pause aktiv bis $(date -d @"$(cat "$PAUSE_FILE")" '+%F %T' 2>/dev/null) — stoppe Worker, warte"
  stop_cards
  while paused; do sleep 120; done
  log "Pause abgelaufen — weiter"
}

# --- VOCAB-Zähler (all=1 inkl. gescheiterte) -------------------------------
vocab_count() {
  local r; r=$(curl -fsS -m 20 "$DISP/vocab-list?all=1" 2>/dev/null) || { echo -1; return; }
  jq '(. // []) | length' <<<"$r" 2>/dev/null || echo -1
}

# --- Usage-Gate (identisch zum Builder) ------------------------------------
usage_ok() {
  [ "$USAGE_LIMIT_PCT" -le 0 ] 2>/dev/null && return 0
  local tok body u5 u7 lim5 nh
  tok=$(jq -r '.claudeAiOauth.accessToken // empty' "$HOME/.claude/.credentials.json" 2>/dev/null || true)
  [ -z "$tok" ] && return 0
  body=$(curl -fsS --max-time 15 -H "Authorization: Bearer $tok" -H "anthropic-beta: oauth-2025-04-20" \
    https://api.anthropic.com/api/oauth/usage 2>/dev/null) || return 0
  u5=$(printf '%s' "$body" | jq -r '.five_hour.utilization // 0 | floor')
  u7=$(printf '%s' "$body" | jq -r '.seven_day.utilization // 0 | floor')
  lim5="$USAGE_LIMIT_PCT"; nh=$(TZ='Europe/Zurich' date +%H); nh=$((10#$nh))
  { [ "$nh" -ge 23 ] || [ "$nh" -lt 6 ]; } && lim5=100
  [ "$u5" -ge "$lim5" ] && return 1
  [ "$u7" -ge "$USAGE_LIMIT_PCT" ] && return 1
  return 0
}
usage_gate() {  # blockiert bis Usage wieder ok
  usage_ok && return 0
  log "Usage-Limit erreicht — pausiere (Check alle 5 min)"
  stop_cards
  while ! usage_ok; do sleep 300; done
  log "Usage wieder ok — weiter"
}

# --- Card-Worker als Prozessgruppen (setsid) -------------------------------
start_card() {  # $1=slot $2=clone
  local slot=$1 clone=$2
  local pidf="$STATE_DIR/card-$slot.pgid"
  [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null && return   # läuft schon
  rm -rf "$clone"; mkdir -p "$clone"
  setsid bash -c "while true; do bash '$CARD_WORKER' 'orch-$slot' '$clone' >> '$STATE_DIR/card-$slot.log' 2>&1; echo \"[\$(date -Is)] card-$slot exit, restart 10s\" >> '$STATE_DIR/card-$slot.log'; sleep 10; done" >/dev/null 2>&1 &
  echo $! > "$pidf"
}
stop_card() {  # $1=slot
  local slot=$1
  local pidf="$STATE_DIR/card-$slot.pgid" pg
  pg=$(cat "$pidf" 2>/dev/null) || return 0
  kill -TERM -- -"$pg" 2>/dev/null || true
  sleep 3
  kill -KILL -- -"$pg" 2>/dev/null || true
  rm -f "$pidf"
}
start_cards() { start_card 1 /tmp/work/orch-card-1; start_card 2 /tmp/work/orch-card-2; log "2 Card-Worker gestartet"; }
stop_cards()  { stop_card 1; stop_card 2; log "Card-Worker gestoppt"; }

cleanup() { stop_cards; log "Orchestrator beendet"; }
trap cleanup EXIT INT TERM

# --- Hauptschleife ---------------------------------------------------------
# Resume-Fix: ein (Re-)Start (z.B. nach Reboot/Crash) landete bisher IMMER in
# CARD-Phase, auch wenn gerade eine VOCAB-Drainage lief (vc>VOCAB_LOW). Das
# feuerte unnötig neue Card-Worker (mehr VOCAB-Bedarf) mitten im Drain. Beim
# Start also: offene VOCAB > LOW → direkt in VOCAB-Phase weitermachen.
vc0=$(vocab_count)
log "Orchestrator start (VOCAB_HIGH=$VOCAB_HIGH VOCAB_LOW=$VOCAB_LOW usage_lim=${USAGE_LIMIT_PCT}%, vc0=$vc0)"
skip_card_phase=0
[ "$vc0" -gt "$VOCAB_LOW" ] 2>/dev/null && skip_card_phase=1
while true; do
  if [ "$skip_card_phase" = 1 ]; then
    skip_card_phase=0
    log "Resume: $vc0 offene VOCAB (> $VOCAB_LOW) → weiter in VOCAB-Phase statt frischer CARD-Phase"
  else
  # ===== CARD-PHASE =====
  echo card > "$PHASE_FILE"
  pause_gate
  usage_gate
  start_cards
  log "CARD-Phase: Card-Worker laufen bis VOCAB(all=1) >= $VOCAB_HIGH"
  while true; do
    sleep "$POLL"
    if paused; then pause_gate; start_cards; fi        # manuelle Pause → drain + warten
    if ! usage_ok; then usage_gate; start_cards; fi   # nach Pause Worker neu hoch
    vc=$(vocab_count)
    [ "$vc" -lt 0 ] 2>/dev/null && { log "Dispatcher nicht erreichbar — warte"; continue; }
    [ $(( $(date +%s) % 600 )) -lt "$POLL" ] && log "CARD-Phase: $vc offene VOCAB (Ziel $VOCAB_HIGH)"
    [ "$vc" -ge "$VOCAB_HIGH" ] && { log "Schwelle erreicht ($vc >= $VOCAB_HIGH) → VOCAB-Phase"; break; }
  done
  stop_cards
  fi

  # ===== VOCAB-PHASE =====
  echo vocab > "$PHASE_FILE"
  log "VOCAB-Phase: 5er-Batches bis VOCAB(all=1) <= $VOCAB_LOW"
  while true; do
    pause_gate
    usage_gate
    vc=$(vocab_count)
    [ "$vc" -lt 0 ] 2>/dev/null && { log "Dispatcher weg — warte"; sleep 30; continue; }
    if [ "$vc" -le "$VOCAB_LOW" ]; then log "VOCAB gedraint ($vc) → CARD-Phase"; break; fi
    log "VOCAB-Phase: $vc offen — starte 5er-Batch"
    bash "$VOCAB_BATCH"; rc=$?
    if [ "$rc" = 2 ]; then
      log "STUCK: nur noch nicht-baubare VOCAB übrig → zurück zur CARD-Phase (Rest bleibt liegen)"
      break
    fi
  done
done
