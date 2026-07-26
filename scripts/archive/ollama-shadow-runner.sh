#!/bin/bash
# SHADOW/KANDIDAT-Runner mit lokalem Ollama-Modell (qwen3-coder:30b auf der GPU).
# Liest N echte todo-Karten READ-ONLY aus der Dispatcher-DB (kein Claim, keine Mutation),
# generiert Handler+Test via /api/chat (getunter Worked-Example-Prompt), Gate = go build+test,
# Fix-Schleife. GRÜN -> Kandidaten-Branch ollama-cand/task-<id> + Dateien in $OUTDIR.
# Es wird NICHTS auf main gemergt, gepusht oder live deployed. Ausgabe: Trefferquoten-Report.
set -uo pipefail
OLLAMA="${OLLAMA:-http://192.168.1.15:11434}"
MODEL="${MODEL:-qwen3-coder:30b}"
DB="/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db"
SRC_CLONE=/tmp/work/disp-wh1
CLONE="${CLONE:-/tmp/work/ollama-shadow}"
GO=/usr/local/go/bin/go
NUM_CTX="${NUM_CTX:-49152}"
MAXROUNDS="${MAXROUNDS:-3}"
N="${N:-6}"
OUTDIR="${OUTDIR:-/tmp/ollama-candidates}"
REPORT="$OUTDIR/report.txt"
WORK=/tmp/ollama-shadow-work; mkdir -p "$WORK" "$OUTDIR"

log(){ printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$REPORT"; }

# --- Shadow-Clone vorbereiten (Worker-Clones nicht anfassen) ---
if [ ! -d "$CLONE/.git" ]; then
  if [ -d "$SRC_CLONE/.git" ]; then
    log "Shadow-Clone anlegen (cp aus $SRC_CLONE)…"; cp -r "$SRC_CLONE" "$CLONE"
  else
    # Worker-Clone weg (tmp-Cleanup) → frisch aus dem lokalen Mirror clonen.
    MIRROR="${MIRROR:-/opt/development/openmagic-mirror.git}"
    log "Shadow-Clone anlegen (Mirror $MIRROR)…"
    GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone --reference "$MIRROR" git@github.com:daniwb/openmagic.git "$CLONE"       || GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone git@github.com:daniwb/openmagic.git "$CLONE"
  fi
fi
git -C "$CLONE" config user.email shadow@local; git -C "$CLONE" config user.name ollama-shadow
git -C "$CLONE" fetch -q origin main 2>/dev/null || true
git -C "$CLONE" checkout -q main 2>/dev/null || git -C "$CLONE" checkout -qB main origin/main
git -C "$CLONE" reset -q --hard origin/main 2>/dev/null || true
git -C "$CLONE" clean -qfd

# --- knapper Katalog + Worked Example (einmal) ---
python3 /opt/development/magic-claude/scripts/concise-catalog.py "$CLONE/scripts/skills/primitive-catalog.md" > "$WORK/catalog.md"
bash "$(dirname "$0")/engine-reference.sh" "$CLONE" > "$WORK/engine-ref.md" 2>/dev/null
EX_H=$(cat "$CLONE/backend/cardfns/task606_trumpeting_gnarr.go")
EX_T=$(cat "$CLONE/backend/cardfns/task606_trumpeting_gnarr_test.go")

read -r -d '' INSTR <<'EOF'
You implement ONE Magic: The Gathering card handler for a Go engine (OpenMagic), plus one behavioral test.
PACKAGE/IMPORT: package cardfns ; import "magic-backend/game" ; the Go module is "magic-backend".

RULES:
- Your vocabulary is the PRIMITIVE CATALOG (composable helpers) PLUS the ENGINE REFERENCE (exact names
  of engine constants like game.Event…/game.Counter…/game.Target…/game.Type… and struct fields). Copy
  every symbol EXACTLY from one of them (Go is CASE-SENSITIVE: Draw not draw; game.TargetCreatureOrPW not
  …Planeswalker; game.Player has Index not ID; GetCard returns (*Card, error) = TWO values). If a symbol
  you need is in NEITHER the catalog NOR the engine reference, it does NOT exist → declare MISSING_PRIMITIVE.
- If NO catalog primitive can express the card's effect, DO NOT fake it. Output exactly:
    MISSING_PRIMITIVE: <short-kebab-name>
    WHY: <1-2 sentences>
  and nothing else (no code).
- Otherwise IMITATE THE WORKED EXAMPLE (a different, fully-correct card). Copy its exact structure:
    * handler: self-registering init(); subscribe to the trigger event; self-guard
      "if e.Source == nil || e.Source.ID != self.ID { return }"; then "if !gs.Battlefield.HasCard(self.ID) { return }".
    * test: build the card with a &game.Card{...} STRUCT LITERAL (fields ID, Name, Type: game.TypeCreature/…,
      Types, Controller, Owner); gs.Battlefield.AddCard(card); MANUALLY invoke game.CardHandlers["<Name>"](gs, card);
      MANUALLY fire the trigger via gs.EventBus.Publish(&game.Event{Type:<event>, Source:card, Player:0}); then assert.
      (AddCard does NOT auto-fire triggers.) intPtr already exists — never redefine it.
    * Draw/Mill/Surveil/Reveal read the LIBRARY, which starts EMPTY: seed it first, e.g.
      for i:=0;i<3;i++ { gs.Players[0].Library.AddCard(game.NewCard("Filler", game.TypeInstant, game.ManaCost{Generic:1}, 0)) }
      and assert a before/after DELTA.
- "enters the battlefield" trigger = game.EventEntersBattlefield.

OUTPUT (when you build): EXACTLY two ```go fenced blocks. START EACH BLOCK with a "// file: <path>" line, then code.
EOF

WORKED="$(printf '=== WORKED EXAMPLE (different card, fully correct — imitate its structure) ===\n```go\n// file: backend/cardfns/task606_trumpeting_gnarr.go\n%s\n```\n```go\n// file: backend/cardfns/task606_trumpeting_gnarr_test.go\n%s\n```\n=== END WORKED EXAMPLE ===\n' "$EX_H" "$EX_T")"

ask(){ # $1 prompt-file -> content.md, echo meta
  jq -n --arg m "$MODEL" --rawfile p "$1" --argjson ctx "$NUM_CTX" \
    '{model:$m, stream:false, options:{temperature:0.1, num_ctx:$ctx}, messages:[{role:"user",content:$p}]}' \
    | curl -sN -m 1800 "$OLLAMA/api/chat" -d @- > "$WORK/resp.json" 2>/dev/null
  jq -r '.message.content // empty' "$WORK/resp.json" > "$WORK/content.md"
  jq -r '(.eval_count//0)' "$WORK/resp.json" 2>/dev/null
}

slug(){ printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]//g'; }

# --- Karten read-only aus der DB ---
CARDS="${CARDS:-}" python3 - "$DB" "$N" > "$WORK/cards.tsv" <<'PY'
import sqlite3,sys,os
db,n=sys.argv[1],int(sys.argv[2])
c=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
ids=[x for x in os.environ.get("CARDS","").replace(","," ").split() if x.strip()]
if ids:  # feste Karten-IDs (reproduzierbar)
    rows=[]
    for i in ids:
        r=c.execute("SELECT id,title,descr FROM tickets WHERE id=?", (int(i),)).fetchone()
        if r: rows.append(r)
else:
    rows=c.execute("SELECT id,title,descr FROM tickets WHERE state='todo' AND type='card' AND length(descr)>20 ORDER BY RANDOM() LIMIT ?", (n,)).fetchall()
for r in rows:
    print("\t".join([str(r[0]), r[1].replace("\t"," ").replace("\n"," "), r[2].replace("\t","    ").replace("\n","\\n")]))
c.close()
PY

: > "$REPORT"
log "=== Shadow-Runner $MODEL | $N Karten | max $MAXROUNDS Runden | Semantik-Verifier AN | $(date -Is) ==="
GATE_GREEN=0; TRUST=0; REJ=0; MISS=0; FAIL=0; I=0
while IFS=$'\t' read -r TID TITLE DESC_ESC; do
  I=$((I+1))
  DESC=$(printf '%s' "$DESC_ESC" | sed 's/\\n/\n/g')
  CARD_NAME=$(printf '%s' "$DESC" | sed -n 's/.*\*\*Card:\*\* *\([^(]*\).*/\1/p' | head -1 | sed 's/ *$//')
  [ -z "$CARD_NAME" ] && CARD_NAME="$TITLE"
  SL=$(slug "$CARD_NAME"); [ -z "$SL" ] && SL="card$TID"
  BASE="backend/cardfns/task${TID}_${SL}"
  log ""; log "[$I/$N] #$TID — $CARD_NAME"
  git -C "$CLONE" checkout -q main 2>/dev/null; git -C "$CLONE" reset -q --hard origin/main; git -C "$CLONE" clean -qfd

  # Prompt (getunt) bauen
  { printf '%s\n\n%s\n\n=== PRIMITIVE CATALOG ===\n' "$INSTR" "$WORKED"; cat "$WORK/catalog.md" "$WORK/engine-ref.md"
    printf '\n\n=== TARGET CARD ===\n%s\n\nWrite files backend/cardfns/task%s_%s.go and _test.go (test func Test%s).\n' "$DESC" "$TID" "$SL" "$(printf '%s' "$SL" | sed 's/.*/\u&/')"
  } > "$WORK/prompt.txt"

  OUTCOME="fail"; ROUNDS=0; TOK=0
  for r in $(seq 1 "$MAXROUNDS"); do
    ROUNDS=$r
    e=$(ask "$WORK/prompt.txt"); TOK=$((TOK + ${e:-0}))
    if grep -q "^MISSING_PRIMITIVE:" "$WORK/content.md"; then
      OUTCOME="missing"; log "   → MISSING_PRIMITIVE: $(grep '^MISSING_PRIMITIVE:' "$WORK/content.md" | head -1 | cut -c1-70)"; break
    fi
    # Ziel-Codeblöcke platzieren (Worked Example ignorieren)
    git -C "$CLONE" checkout -q -- . 2>/dev/null; git -C "$CLONE" clean -qfd backend/cardfns/ 2>/dev/null
    python3 - "$WORK/content.md" "$CLONE" "$BASE" <<'PY'
import re,sys,os
content=open(sys.argv[1]).read(); clone=sys.argv[2]; base=sys.argv[3]
blocks=[b for b in re.findall(r'```go\s*\n(.*?)```', content, re.S) if "task606" not in b]
for b in blocks:
    b=re.sub(r'^\s*//\s*file:.*\n','',b).rstrip()+"\n"
    p=os.path.join(clone, (base+"_test.go") if "func Test" in b else (base+".go"))
    open(p,'w').write(b)
PY
    TESTNAME=$(grep -rhoE 'func (Test[A-Za-z0-9_]+)\(' "$CLONE/$BASE"_test.go 2>/dev/null | sed -E 's/func (Test[A-Za-z0-9_]+).*/\1/' | head -1)
    if [ -z "$TESTNAME" ]; then ERR="keine Testdatei/kein Test erzeugt"; else
      ( cd "$CLONE/backend"
        timeout 300 $GO test ./cardfns/ -run "^${TESTNAME}$" -count=1 -v > "$WORK/g.log" 2>&1 )
      if grep -q "no tests to run" "$WORK/g.log"; then ERR="Test lief nicht: $(grep -E 'undefined|cannot use|redeclared|no required' "$WORK/g.log" | head -4)"
      elif grep -q "^--- PASS: ${TESTNAME}" "$WORK/g.log"; then OUTCOME="green"; break
      else ERR="$(grep -E "task${TID}|undefined|cannot use|redeclared|--- FAIL|panic|Error:" "$WORK/g.log" | head -6)"; fi
    fi
    log "   Runde $r rot: $(printf '%s' "$ERR" | head -c 160)"
    # Fehler zurückfüttern
    { printf '%s\n\n%s\n\n=== PRIMITIVE CATALOG ===\n' "$INSTR" "$WORKED"; cat "$WORK/catalog.md" "$WORK/engine-ref.md"
      printf '\n\n=== TARGET CARD ===\n%s\n\n=== PREVIOUS ATTEMPT FAILED ===\n%s\n\nFix it: undefined=>wrong capitalization or not in catalog (copy exact catalog spelling); follow the WORKED EXAMPLE test idiom; seed the library for draw effects; intPtr exists. Re-output BOTH ```go files with // file: headers, nothing else.\n' "$DESC" "$ERR"
    } > "$WORK/prompt.txt"
  done

  case "$OUTCOME" in
    green)
      GATE_GREEN=$((GATE_GREEN+1)); log "   ✅ Gate-grün in Runde $ROUNDS (${TOK} tok) — Semantik-Verifier…"
      # Semantik-Check auf der GPU (3 Votes, frisch/adversarial, Oracle vs. Handler)
      VOUT=$(VOTES="${VVOTES:-3}" MODEL="$MODEL" OLLAMA="$OLLAMA" bash /opt/development/magic-claude/scripts/ollama-verify.sh "$TID" "$CLONE/$BASE.go" 2>/dev/null)
      VFIN=$(printf '%s' "$VOUT" | grep -E "^→ #" | tail -1)
      VREASON=$(printf '%s' "$VOUT" | grep -iE "REASON:|Vote 1:" | head -1 | cut -c1-120)
      if printf '%s' "$VFIN" | grep -q "MISMATCH"; then
        REJ=$((REJ+1)); log "   ⚠️  VERWORFEN (Gate-grün, aber Verifier MISMATCH): $VREASON"
      else
        TRUST=$((TRUST+1)); log "   ✅✅ VERTRAUENSWÜRDIG (Gate-grün + Verifier MATCH)"
        mkdir -p "$OUTDIR/task-$TID"; cp "$CLONE/$BASE".go "$CLONE/$BASE"_test.go "$OUTDIR/task-$TID/" 2>/dev/null
        git -C "$CLONE" checkout -qB "ollama-cand/task-$TID" 2>/dev/null
        git -C "$CLONE" add -A 2>/dev/null; git -C "$CLONE" commit -q -m "candidate(task-$TID): $CARD_NAME [qwen3-coder shadow, verified]" 2>/dev/null
        git -C "$CLONE" checkout -q main 2>/dev/null
      fi ;;
    missing) MISS=$((MISS+1)) ;;
    *) FAIL=$((FAIL+1)); log "   ❌ nach $ROUNDS Runden nicht grün (${TOK} tok)" ;;
  esac
  git -C "$CLONE" reset -q --hard origin/main 2>/dev/null; git -C "$CLONE" clean -qfd
done < "$WORK/cards.tsv"

log ""
log "=========================================="
log "Gate-grün: $((TRUST+REJ))  →  davon VERTRAUENSWÜRDIG: $TRUST | vom Verifier verworfen (silently-wrong): $REJ"
log "missing-primitive (ehrlich): $MISS | fehlgeschlagen: $FAIL   (von $I)"
[ "$((TRUST+REJ))" -gt 0 ] && log "Verifier fing $REJ/$((TRUST+REJ)) der Gate-Grünen als silently-wrong ab"
log "→ VERTRAUENSWÜRDIGE Ausbeute: $TRUST/$I"
log "Kandidaten (nur verifizierte): $OUTDIR/task-*/  | Branches: git -C $CLONE branch | grep ollama-cand"
