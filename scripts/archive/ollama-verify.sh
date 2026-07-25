#!/bin/bash
# Semantischer Verifier auf der GPU: prüft, ob ein generierter Handler den Oracle-Text
# der Karte getreu umsetzt. Unabhängiger, frischer Call (kein Generierungs-Kontext),
# adversarial ("nimm an, es GIBT einen Bug"). Optional VOTES>1 für Mehrheitsentscheid.
# Usage: ollama-verify.sh <ticket_id> <handler.go>
set -uo pipefail
OLLAMA="${OLLAMA:-http://192.168.1.15:11434}"
MODEL="${MODEL:-qwen3-coder:30b}"
DB="/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db"
VOTES="${VOTES:-1}"
TID="${1:?ticket_id}"; HFILE="${2:?handler.go}"
W=/tmp/ollama-verify; mkdir -p "$W"

ORACLE=$(python3 - "$TID" <<'PY'
import sqlite3,sys,re
c=sqlite3.connect("file:/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db?mode=ro",uri=True)
r=c.execute("SELECT descr FROM tickets WHERE id=?", (int(sys.argv[1]),)).fetchone()
m=re.search(r'\*\*Oracle text:\*\*\s*```(.*?)```', r[0], re.S) if r else None
print((m.group(1).strip() if m else (r[0] if r else "")))
PY
)
CODE=$(cat "$HFILE")

read -r -d '' HDR <<'EOF'
You are a STRICT reviewer for a Magic: The Gathering rules engine. You are given a card's official
ORACLE TEXT and a Go HANDLER implementation. Decide if the handler FAITHFULLY implements the oracle.
Assume there IS a bug and hunt for it. Check specifically:
- TRIGGER / timing: does it fire on exactly the event/condition the oracle describes?
- EFFECT: does it do what the oracle says?
- FILTERS / CONDITIONS: correct restrictions (card types, "you control", "instant or sorcery only", opponents, etc.)?
- VALUES / TARGETS / AMOUNTS: correct numbers and who/what is affected?
A wrong trigger, a missing type filter, or a wrong amount is a MISMATCH.
Output EXACTLY two lines and nothing else:
VERDICT: MATCH        (or)   VERDICT: MISMATCH
REASON: <one concise line; if MISMATCH, name the specific discrepancy>
EOF

verify_once(){
  printf '%s\n\nORACLE TEXT:\n%s\n\nHANDLER:\n```go\n%s\n```\n' "$HDR" "$ORACLE" "$CODE" > "$W/p.txt"
  jq -n --arg m "$MODEL" --rawfile p "$W/p.txt" \
    '{model:$m, stream:false, options:{temperature:0.0, num_ctx:8192}, messages:[{role:"user",content:$p}]}' \
    | curl -sN -m 600 "$OLLAMA/api/chat" -d @- 2>/dev/null | jq -r '.message.content // empty'
}

MATCH=0; MIS=0
for v in $(seq 1 "$VOTES"); do
  OUT=$(verify_once)
  V=$(printf '%s' "$OUT" | grep -oiE "VERDICT: *(MATCH|MISMATCH)" | grep -oiE "MATCH|MISMATCH" | head -1 | tr a-z A-Z)
  R=$(printf '%s' "$OUT" | grep -iE "^REASON:" | head -1 | cut -c1-140)
  echo "  Vote $v: ${V:-?}  |  $R"
  [ "$V" = "MATCH" ] && MATCH=$((MATCH+1)); [ "$V" = "MISMATCH" ] && MIS=$((MIS+1))
done
if [ "$MIS" -ge "$MATCH" ] && [ "$MIS" -gt 0 ]; then echo "→ #$TID: MISMATCH ($MIS/$VOTES)"; else echo "→ #$TID: MATCH ($MATCH/$VOTES)"; fi
