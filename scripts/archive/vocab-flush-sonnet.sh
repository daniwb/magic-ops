#!/bin/bash
# Wöchentlicher VOCAB-Flush mit Sonnet, direkt nach dem Claude-Weekly-Reset
# (18:00 UTC = 20:00 Zürich). Schritt 1: tiefe Dedup (Sonnet clustert
# aggressiver als DeepSeek). Schritt 2: alle offenen [VOCAB] mit Sonnet abbauen,
# bis die Queue leer ist ODER das Usage-Gate (95%) stoppt.
#
# Cron: 0 18 * * 3  (Mittwoch 18:00 UTC — Reset-Tag)
set -uo pipefail

LOCK=/tmp/vocab-flush.lock
exec 9>"$LOCK"; flock -n 9 || { echo "already running"; exit 0; }

export PATH=/usr/local/go/bin:$PATH
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_API_KEY  # saubere Claude-Auth

DISP="${DISP:-http://localhost:9999}"
LOG=/tmp/vocab-flush.log
log() { printf '[%s] flush: %s\n' "$(date -Is)" "$*" | tee -a "$LOG"; }

# Frische-Guard: nur laufen, wenn das 7d-Budget wirklich frisch ist (<50%).
# Verhindert, dass der Job an einem falschen Tag das Budget verheizt.
tok=$(jq -r '.claudeAiOauth.accessToken // empty' "$HOME/.claude/.credentials.json" 2>/dev/null || true)
if [ -n "$tok" ]; then
  u7=$(curl -fsS --max-time 15 -H "Authorization: Bearer $tok" -H "anthropic-beta: oauth-2025-04-20" \
       https://api.anthropic.com/api/oauth/usage 2>/dev/null | jq -r '.seven_day.utilization // 100 | floor' 2>/dev/null || echo 100)
  if [ "${FORCE:-0}" != "1" ] && [ "$u7" -ge 50 ]; then
    log "7d-Budget bei ${u7}% — noch nicht frisch resettet, überspringe (FORCE=1 erzwingt)"
    exit 0
  fi
  log "7d-Budget ${u7}% — frisch, starte Flush"
fi

# ---- Schritt 1: tiefe Dedup mit Sonnet ----
log "Schritt 1: VOCAB-Dedup (Sonnet)"
PROVIDER=claude MODEL=claude-sonnet-5 bash /opt/development/magic-claude/scripts/vocab-dedup-v4.sh 2>&1 | sed 's/^/  /' | tee -a "$LOG" || true

# ---- Schritt 2: alle Primitive mit Sonnet abbauen ----
# Sonnet-Builder in Schleife bis /vocab-list leer ODER Usage-Gate stoppt.
# Der Builder (dispatcher-primitive-builder-v4.sh) hat eigenes Usage-Gate (95%)
# und flock → sauber. MAX_PRIMS gross, damit ein Lauf viele schafft.
log "Schritt 2: Primitive abbauen (Sonnet, bis leer oder Budget)"
DRY=0
while true; do
  OPEN=$(curl -fsS -m 15 "$DISP/vocab-list" 2>/dev/null | jq 'length' 2>/dev/null || echo 0)
  log "  offene [VOCAB]: $OPEN"
  [ "$OPEN" = 0 ] && { log "Queue leer — fertig"; break; }

  BUILDER_ID=flush MAX_PRIMS=50 MODEL=claude-sonnet-5 USAGE_LIMIT_PCT=95 \
    bash /opt/development/magic-claude/scripts/dispatcher-primitive-builder-v4.sh 2>&1 | sed 's/^/  /' | tee -a "$LOG" || true

  # Fortschritt? sonst abbrechen (Budget erschöpft / alles gescheitert)
  OPEN2=$(curl -fsS -m 15 "$DISP/vocab-list" 2>/dev/null | jq 'length' 2>/dev/null || echo 0)
  if [ "$OPEN2" -ge "$OPEN" ]; then
    DRY=$((DRY+1))
    log "  kein Fortschritt ($OPEN→$OPEN2), dry=$DRY"
    [ "$DRY" -ge 2 ] && { log "2× kein Fortschritt (Budget erschöpft oder Rest = ENGINE_HOOK_NEEDED) — Stopp"; break; }
  else
    DRY=0
  fi
done
log "Flush fertig"
