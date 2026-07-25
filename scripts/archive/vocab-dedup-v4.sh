#!/bin/bash
# v4-native [VOCAB]-Dedup: Modell clustert offene VOCAB-Titel semantisch,
# Dubletten werden per /vocab-merge aufs kanonische (kleinste id) zusammengeführt
# (blockierte Karten wandern mit). Läuft standardmäßig auf DeepSeek (Claude-Budget
# schonen). Konservativ: Event≠Action, Keyword≠Granting sind KEINE Dubletten.
set -uo pipefail

DISP="${DISP:-http://localhost:9999}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
# PROVIDER=claude → normale Claude-Auth (Sonnet, tiefer Pass);
# PROVIDER=deepseek (default) → DeepSeek-Endpoint (Budget-schonend, konservativ)
if [ "${PROVIDER:-deepseek}" = "claude" ]; then
  unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_API_KEY
  MODEL="${MODEL:-claude-sonnet-5}"
else
  unset ANTHROPIC_AUTH_TOKEN
  export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic}"
  export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-$(cat /opt/development/deepseek-sandbox/.deepseek_key)}"
  MODEL="${MODEL:-deepseek-v4-pro}"
fi

log() { printf '[%s] vocab-dedup: %s\n' "$(date -Is)" "$*"; }

LIST=$(curl -fsS -m 30 "$DISP/vocab-list?all=1" 2>/dev/null || echo '[]')
N=$(printf '%s' "$LIST" | jq 'length')
log "$N offene [VOCAB]"
[ "$N" -lt 10 ] && { log "zu wenige — skip"; exit 0; }

# id<TAB>slug für das Modell
printf '%s' "$LIST" | jq -r '.[] | "\(.id)\t\(.title | sub("^\\[VOCAB\\] ";""))"' | sort -n > /tmp/vocab-dedup-list.tsv

PROMPT=/tmp/vocab-dedup-prompt.txt
{
  echo "You are deduplicating engine-capability tickets for a Magic: The Gathering engine."
  echo "Below: one per line as ID<TAB>capability-slug. Different tickets often describe the SAME missing engine capability with different words."
  echo "Find groups that are clearly the SAME capability. In each group the CANONICAL is the LOWEST id; all others are duplicates of it."
  echo "BE CONSERVATIVE: an event vs an action, a keyword vs granting that keyword, 'from graveyard' vs 'from hand' are DIFFERENT — do NOT merge when unsure."
  echo "OUTPUT: ONLY lines 'MERGE <duplicate_id> <canonical_id>', nothing else. If none, output 'NONE'."
  echo ""
  cat /tmp/vocab-dedup-list.tsv
} > "$PROMPT"

RAW=$(timeout 600 "$CLAUDE_BIN" -p --model "$MODEL" --permission-mode bypassPermissions --max-turns 3 < "$PROMPT" 2>/dev/null || echo "")
printf '%s\n' "$RAW" | grep -E '^MERGE [0-9]+ [0-9]+$' > /tmp/vocab-dedup-map.txt || true
M=$(wc -l < /tmp/vocab-dedup-map.txt)
log "Modell schlägt $M Merges vor"
[ "$M" = 0 ] && exit 0

MERGED=0; SKIP=0
while read -r _ DUPE CANON; do
  # Validierung: beide in der aktuellen Liste, kanonisch = kleinere id
  grep -q "^$DUPE	" /tmp/vocab-dedup-list.tsv || { SKIP=$((SKIP+1)); continue; }
  grep -q "^$CANON	" /tmp/vocab-dedup-list.tsv || { SKIP=$((SKIP+1)); continue; }
  [ "$CANON" -lt "$DUPE" ] || { SKIP=$((SKIP+1)); continue; }
  R=$(curl -s -m 15 "$DISP/vocab-merge?from=$DUPE&to=$CANON" 2>/dev/null || echo '{}')
  if printf '%s' "$R" | jq -e '.ok==true' >/dev/null 2>&1; then
    MOVED=$(printf '%s' "$R" | jq -r '.moved')
    log "merge #$DUPE -> #$CANON ($MOVED Karten)"
    MERGED=$((MERGED+1))
  else
    SKIP=$((SKIP+1))
  fi
done < /tmp/vocab-dedup-map.txt

log "FERTIG: $MERGED merged, $SKIP übersprungen"
