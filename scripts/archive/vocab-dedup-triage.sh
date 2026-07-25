#!/bin/bash
# [VOCAB]-Dedup-Triage — läuft als VORLAUF des nächtlichen Primitive-Builders.
# Worker formulieren dieselbe Engine-Lücke unterschiedlich (substring-Dedup im
# Dispatcher fängt nur wörtliche Dupes). Hier clustert Claude die offenen
# [VOCAB]-Titel semantisch; die Merge-Mechanik ist deterministisch:
#   BLOCKED_CARDS → kanonisches (ältestes) Ticket, VOCAB_REQUEUED-Marker aufs
#   Duplikat (verhindert vorzeitige Requeue durch kanboard-vocab-requeue.sh),
#   dann schließen. Befund 2026-07-19: 214 Tickets ≈ 60-80 echte Fähigkeiten.
set -uo pipefail

KB="${KB_URL:-https://kanboard.k.ezq.ch/jsonrpc.php}"
AUTH="${KB_USER:-admin}:${KB_TOKEN:-fda650985874506da62a737b9a7befc39a5873735a253de80fa2d5ee5c20}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
MODEL="${MODEL:-claude-sonnet-5}"
COL_PRIORITY=19
MIN_TICKETS="${MIN_TICKETS:-10}"   # unterhalb lohnt der Claude-Call nicht

log() { printf '[%s] vocab-triage: %s\n' "$(date -Is)" "$*"; }
kb()  { curl -fsS --max-time 60 -u "$AUTH" -H "Content-Type: application/json" -d "$1" "$KB"; }

if [ "${GLM_WORKER:-0}" != "1" ]; then
  unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
fi

# ---- Offene [VOCAB]-Titel einsammeln ----
kb '{"jsonrpc":"2.0","id":1,"method":"getAllTasks","params":{"project_id":2,"status_id":1}}' \
  > /tmp/vocab-triage-snapshot.json
jq -r --argjson col "$COL_PRIORITY" \
  '.result[] | select(.column_id==$col and (.title|startswith("[VOCAB]"))) | "\(.id)\t\(.title | sub("^\\[VOCAB\\] "; ""))"' \
  /tmp/vocab-triage-snapshot.json | sort -n > /tmp/vocab-triage-list.tsv
N=$(wc -l < /tmp/vocab-triage-list.tsv)
log "$N offene [VOCAB]-Tickets"
[ "$N" -lt "$MIN_TICKETS" ] && { log "unter MIN_TICKETS=$MIN_TICKETS — skip"; exit 0; }

# ---- Claude clustert (nur Urteil, keine Tools) ----
PROMPT=/tmp/vocab-triage-prompt.txt
{
  echo "You are deduplicating engine-capability tickets for a Magic: The Gathering engine."
  echo "Below: one ticket per line as ID<TAB>capability-slug. Different workers describe the SAME missing engine capability with different words (e.g. 'attack-trigger-event' vs 'creature-attack-trigger', 'd20-dice-roll' vs 'dice-roll-d20')."
  echo ""
  echo "TASK: find groups that are clearly the SAME capability. For each group, the CANONICAL ticket is the one with the LOWEST id; all others are duplicates."
  echo "BE CONSERVATIVE: related-but-different capabilities (e.g. 'creature-deals-damage' vs 'creature-was-dealt-damage', an event vs an action, a keyword vs granting that keyword to others) are NOT duplicates. When unsure, do NOT merge."
  echo "OUTPUT: ONLY lines of the form 'MERGE <duplicate_id> <canonical_id>' — nothing else, no explanations. If there are no duplicates, output 'NONE'."
  echo ""
  cat /tmp/vocab-triage-list.tsv
} > "$PROMPT"

RAW=$(timeout 600 "$CLAUDE_BIN" -p --model "$MODEL" --permission-mode bypassPermissions --max-turns 3 < "$PROMPT" 2>/dev/null || echo "")
printf '%s\n' "$RAW" | grep -E '^MERGE [0-9]+ [0-9]+$' > /tmp/vocab-triage-map.txt || true
M=$(wc -l < /tmp/vocab-triage-map.txt)
log "Claude schlägt $M Merges vor"
[ "$M" = 0 ] && exit 0

# ---- Validieren + mechanisch ausführen ----
MERGED=0; SKIPPED=0
while read -r _ DUPE CANON; do
  # Beide IDs müssen offen+bekannt sein, kanonisch = älter (kleinere ID)
  grep -q "^$DUPE	" /tmp/vocab-triage-list.tsv || { SKIPPED=$((SKIPPED+1)); continue; }
  grep -q "^$CANON	" /tmp/vocab-triage-list.tsv || { SKIPPED=$((SKIPPED+1)); continue; }
  [ "$CANON" -lt "$DUPE" ] || { SKIPPED=$((SKIPPED+1)); continue; }

  T=$(kb "$(jq -n --argjson t "$DUPE" '{jsonrpc:"2.0",id:1,method:"getTask",params:{task_id:$t}}')" | jq -r '.result // empty')
  [ -z "$T" ] || [ "$(printf '%s' "$T" | jq -r '.is_active')" != "1" ] && { SKIPPED=$((SKIPPED+1)); continue; }
  TITLE=$(printf '%s' "$T" | jq -r '.title')
  DESC=$(printf '%s' "$T" | jq -r '.description // ""')
  COMMENTS=$(kb "$(jq -n --argjson t "$DUPE" '{jsonrpc:"2.0",id:1,method:"getAllComments",params:{task_id:$t}}')" | jq -r '[.result[]?.comment // ""] | join("\n")')
  CARDS=$(printf '%s\n%s' "$DESC" "$COMMENTS" | grep -iE 'BLOCKED_CARDS:' \
    | sed -E 's/.*BLOCKED_CARDS:[[:space:]]*//' | tr ',' ' ' | tr -s ' ' '\n' \
    | grep -E '^[0-9]+$' | sort -un | paste -sd' ' || true)

  if [ -n "$CARDS" ]; then
    kb "$(jq -n --argjson t "$CANON" --arg c "Merged duplicate #$DUPE ($TITLE).
BLOCKED_CARDS: $CARDS" '{jsonrpc:"2.0",id:1,method:"createComment",params:{task_id:$t,user_id:1,content:$c}}')" >/dev/null \
      || { SKIPPED=$((SKIPPED+1)); log "#$DUPE: Karten-Transfer fehlgeschlagen — bleibt offen"; continue; }
  fi
  kb "$(jq -n --argjson t "$DUPE" --arg c "VOCAB_REQUEUED — semantic duplicate, merged into [VOCAB] #$CANON (nightly triage). Blocked cards transferred; they requeue when #$CANON closes." \
    '{jsonrpc:"2.0",id:1,method:"createComment",params:{task_id:$t,user_id:1,content:$c}}')" >/dev/null || true
  kb "$(jq -n --argjson t "$DUPE" '{jsonrpc:"2.0",id:1,method:"closeTask",params:{task_id:$t}}')" >/dev/null \
    && { MERGED=$((MERGED+1)); log "merge #$DUPE -> #$CANON (cards: ${CARDS:-keine})"; } \
    || { SKIPPED=$((SKIPPED+1)); log "#$DUPE: close fehlgeschlagen"; }
  sleep 0.5
done < /tmp/vocab-triage-map.txt

log "FERTIG: $MERGED merged, $SKIPPED übersprungen/validiert-raus"
