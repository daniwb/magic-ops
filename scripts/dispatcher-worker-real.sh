#!/bin/bash
# Dispatcher-Worker v3 — echte Claude-Fixes nach dem bewiesenen 2-Phasen-Muster:
#   Phase 1: Ein-Schuss-Generierung aus Primitive-Katalog (Claude schreibt die
#            Dateien SELBST im Clone; keine Repo-Exploration; ~36k Token)
#   Phase 2: Fast-Gate (go build + go test -run auf die neuen Tests; Sekunden)
#   Phase 3: bounded Fix-Loop (max 3 Versuche gesamt), dann Merge+Push+Deploy
# Meldet fixed / parked(missing_primitive|max_retry_reached) an den Dispatcher.
set -uo pipefail

WORKER_ID="${1:-w1}"
CLONE_PATH="${2:-/tmp/work/disp-$WORKER_ID}"
DISPATCHER="${DISPATCHER:-http://localhost:9999}"
REPO_SSH="${REPO_SSH:-git@github.com:daniwb/openmagic.git}"
LIVE_REPO="/opt/development/magic-new"
CATALOG="$LIVE_REPO/scripts/skills/primitive-catalog.md"
GO=/usr/local/go/bin/go
export PATH="/usr/local/go/bin:$PATH"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"

MODEL_SONNET="${MODEL_SONNET:-claude-sonnet-5}"
MODEL_HAIKU="${MODEL_HAIKU:-claude-haiku-4-5-20251001}"
WORKER_MAX_TURNS="${WORKER_MAX_TURNS:-20}"
# Mechaniken, die Haiku auf Erstversuch zuverlässig schafft (aus Bugfixer)
HAIKU_MECHS=" create_token draw gain_life mill add_mana pump_boost destroy_target exile_target scry each_opponent put_counter reanimate_gy_to_bf "
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
CLAUDE_TIMEOUT="${CLAUDE_TIMEOUT:-900}"
ONE_SHOT="${ONE_SHOT:-0}"   # 1 = genau ein Ticket bearbeiten, dann exit (für E2E-Tests)
DEPLOY="${DEPLOY:-1}"       # 0 = kein Build/Restart des Backends nach Merge

# Usage-Gate (portiert aus kanboard-bugfixer.sh, fail-open)
USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-95}"
USAGE_GATE_TTL="${USAGE_GATE_TTL:-180}"
USAGE_CACHE="${USAGE_CACHE:-/tmp/claude-usage-gate.json}"
PAUSE_FILE="${PAUSE_FILE:-/opt/development/magic-claude/.orch-pause-until}"
source /opt/development/magic-claude/scripts/lib-pace-gate.sh 2>/dev/null || true

# ---- env hygiene: geerbtes Ollama-Routing zerlegt jeden Claude-Call ----
if [ "${GLM_WORKER:-0}" != "1" ]; then
  unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
fi

log() { printf '[%s] %s: %s\n' "$(date '+%H:%M:%S')" "$WORKER_ID" "$*" >&2; }

# Peak-Gate: manche APIs (DeepSeek) kosten in Stoßzeiten doppelt. PEAK_PAUSE=1
# aktiviert; PEAK_HOURS (UTC-Stunden) default = DeepSeek-Peak (1-4h + 6-10h).
peak_gate() {
  [ "${PEAK_PAUSE:-0}" = "1" ] || return 0
  local h; h=$(date -u +%H); h=$((10#$h))
  case " ${PEAK_HOURS:-1 2 3 6 7 8 9} " in *" $h "*) return 1;; esac
  return 0
}

# ---- Usage-Gate: 0 = ok, 1 = pausieren ----
usage_gate() {
  [ "$USAGE_LIMIT_PCT" -le 0 ] 2>/dev/null && return 0
  local lim5="$USAGE_LIMIT_PCT" lim7="$USAGE_LIMIT_PCT" nh now age tok body u5 u7 r5 r7
  nh=$(TZ='Europe/Zurich' date +%H); nh=$((10#$nh))
  # Nachtfenster: 5h-Fenster voll ausfahren, 7d-Kappe bleibt
  if [ "$nh" -ge 23 ] || [ "$nh" -lt 6 ]; then lim5=100; fi
  now=$(date +%s); age=99999
  [ -s "$USAGE_CACHE" ] && age=$(( now - $(stat -c %Y "$USAGE_CACHE" 2>/dev/null || echo 0) ))
  if [ "$age" -ge "$USAGE_GATE_TTL" ]; then
    tok=$(jq -r '.claudeAiOauth.accessToken // empty' "$HOME/.claude/.credentials.json" 2>/dev/null || true)
    [ -z "$tok" ] && return 0  # fail-open
    if body=$(curl -fsS --max-time 15 -H "Authorization: Bearer $tok" \
         -H "anthropic-beta: oauth-2025-04-20" \
         https://api.anthropic.com/api/oauth/usage 2>/dev/null) \
       && printf '%s' "$body" | jq -e '.five_hour' >/dev/null 2>&1; then
      printf '%s' "$body" > "$USAGE_CACHE"
    elif [ "$age" -ge 1800 ]; then
      return 0  # blind → fail-open
    else
      touch "$USAGE_CACHE" 2>/dev/null || true  # backoff gegen 429-Spirale
    fi
  fi
  u5=$(jq -r '.five_hour.utilization // 0 | floor' "$USAGE_CACHE" 2>/dev/null || echo 0)
  u7=$(jq -r '.seven_day.utilization // 0 | floor' "$USAGE_CACHE" 2>/dev/null || echo 0)
  # abgelaufene Fenster zählen als 0 (sonst hängt der Gate an stalem Wert fest)
  now=$(date +%s)
  r5=$(date -d "$(jq -r '.five_hour.resets_at // empty' "$USAGE_CACHE" 2>/dev/null)" +%s 2>/dev/null || echo 0)
  r7=$(date -d "$(jq -r '.seven_day.resets_at // empty' "$USAGE_CACHE" 2>/dev/null)" +%s 2>/dev/null || echo 0)
  [ "$r5" -gt 0 ] && [ "$now" -ge "$r5" ] && u5=0
  [ "$r7" -gt 0 ] && [ "$now" -ge "$r7" ] && u7=0
  if [ "$u5" -ge "$lim5" ] || [ "$u7" -ge "$lim7" ]; then
    log "usage-gate: 5h=${u5}% 7d=${u7}% — pausiere"
    return 1
  fi
  return 0
}

# ---- Difficulty-Router: Haiku für einfache Bundle-Mechaniken im Erstversuch ----
pick_model() {
  local title="$1" attempt="$2" retries="$3" mech
  [ "$attempt" -gt 1 ] && { echo "$MODEL_SONNET"; return; }
  [ "$retries" != "0" ] && { echo "$MODEL_SONNET"; return; }
  # CHEAP_FIRST=1 (z.B. DeepSeek flash→pro): billiges Modell für JEDEN
  # Erstversuch, nicht nur für einfache Bundle-Mechaniken
  [ "${CHEAP_FIRST:-0}" = "1" ] && { echo "$MODEL_HAIKU"; return; }
  mech=$(printf '%s' "$title" | sed -n 's/^DSL-BUNDLE: \[\([a-z_]*\)\].*/\1/p')
  if [ -n "$mech" ] && [[ "$HAIKU_MECHS" == *" $mech "* ]]; then
    echo "$MODEL_HAIKU"
  else
    echo "$MODEL_SONNET"
  fi
}

# ---- Report an den Dispatcher (jq übernimmt sauberes JSON-Escaping) ----
report() { # $1 status  $2 reason  $3 missing_primitive  $4 why  $5 note  [$6 skipped-json-array]
  local tok=0; [ -f "/tmp/disp-$WORKER_ID-tokens" ] && tok=$(awk '{s+=$1} END{print s+0}' "/tmp/disp-$WORKER_ID-tokens")
  jq -n --arg t "$TICKET_ID" --arg w "$WORKER_ID" --arg s "$1" --arg r "$2" \
        --arg p "$3" --arg y "$4" --arg n "$5" --arg b "${TICKET_TITLE:-}" \
        --argjson tok "$tok" --argjson k "${6:-[]}" \
    '{ticket_id:$t, worker_id:$w, status:$s, reason:$r,
      missing_primitive:$p, primitive_why:$y, note:$n, blocked_card_title:$b, tokens:$tok, skipped:$k}' \
  | curl -s -X POST "$DISPATCHER/report" -H 'Content-Type: application/json' -d @- >/dev/null 2>&1 || true
}

# ---- claude-Aufruf mit Token-Erfassung ----
# Läuft claude mit --output-format json, gibt den Text (.result) zurück (damit die
# bestehende Text-Parsing-Logik unverändert weiterläuft) und ADDIERT die Usage
# (input+cache_create+cache_read+output) in eine Akkumulator-Datei pro Ticket.
# Die Datei überlebt die $(...)-Subshells der Aufrufer (Variablen täten das nicht).
TOK_FILE="/tmp/disp-$WORKER_ID-tokens"
claude_run() { # claude-Flags (ohne --output-format); Prompt via stdin
  local raw txt used
  raw=$(cd "$CLONE_PATH" && timeout "${CJ_TIMEOUT:-$CLAUDE_TIMEOUT}" "$CLAUDE_BIN" -p \
        --output-format json "$@" 2>>"/tmp/disp-$WORKER_ID-claude.err") \
    || { echo "CLAUDE_TIMEOUT_OR_ERROR"; return 0; }
  used=$(printf '%s' "$raw" | jq -r 'if type=="object" then ((.usage.input_tokens//0)+(.usage.cache_creation_input_tokens//0)+(.usage.cache_read_input_tokens//0)+(.usage.output_tokens//0)) else 0 end' 2>/dev/null)
  [ -n "$used" ] && [ "$used" != 0 ] && echo "$used" >> "$TOK_FILE"
  txt=$(printf '%s' "$raw" | jq -r '.result // empty' 2>/dev/null)
  if [ -n "$txt" ]; then printf '%s' "$txt"; else printf '%s' "$raw"; fi
}

# Geskippte Bundle-Karten aus dem Claude-Output einsammeln (Karte + Primitiv +
# WHY + ihr Oracle-Block aus der Ticket-Beschreibung) als JSON-Array.
collect_skips() { # $1 = claude output, nutzt $TICKET_DESC; echo JSON-Array
  local out="$1" skips='[]' i card prim why block
  local -a cards prims whys
  mapfile -t cards < <(printf '%s' "$out" | grep "^SKIPPED_CARD:" | sed 's/^SKIPPED_CARD: *//' | awk '!seen[$0]++')
  mapfile -t prims < <(printf '%s' "$out" | grep "^MISSING_PRIMITIVE:" | sed 's/^MISSING_PRIMITIVE: *//')
  mapfile -t whys  < <(printf '%s' "$out" | grep "^WHY:" | sed 's/^WHY: *//')
  for i in "${!cards[@]}"; do
    card="${cards[$i]}"
    prim="${prims[$i]:-${prims[0]:-unknown}}"
    why="${whys[$i]:-${whys[0]:-}}"
    block=$(printf '%s\n' "$TICKET_DESC" | awk -v n="$card" 'BEGIN{p=0} /^### /{p=(index($0,n)>0)} p')
    [ -z "$block" ] && block="(card section not found in bundle description — see original ticket)"
    skips=$(jq -n --argjson a "$skips" --arg c "$card" --arg p "$prim" --arg y "$why" --arg d "$block" \
      '$a + [{card:$c, primitive:$p, why:$y, desc:$d}]')
  done
  printf '%s' "$skips"
}

stop_heartbeat() {
  if [ -n "${HB_PID:-}" ]; then
    pkill -P "$HB_PID" 2>/dev/null || true
    kill "$HB_PID" 2>/dev/null || true
    wait "$HB_PID" 2>/dev/null || true
    HB_PID=""
  fi
}
trap stop_heartbeat EXIT

# ---- Setup: eigener Clone via SSH (NIE der Live-Checkout) ----
if [ ! -d "$CLONE_PATH/.git" ]; then
  log "clone $REPO_SSH -> $CLONE_PATH"
  GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone "$REPO_SSH" "$CLONE_PATH" || { log "FATAL: clone failed"; exit 1; }
fi
cd "$CLONE_PATH"
git config user.email "dispatcher-worker@magic"
git config user.name  "dispatcher-$WORKER_ID"

# ---- Hauptschleife ----
while true; do
  if [ -f "$PAUSE_FILE" ] && [ "$(date +%s)" -lt "$(cat "$PAUSE_FILE" 2>/dev/null || echo 0)" ]; then
    log "Pause aktiv bis $(date -d @"$(cat "$PAUSE_FILE")" '+%F %T' 2>/dev/null) — kein neues Ticket"; sleep 300; continue
  fi
  if declare -f pace_ok >/dev/null && ! pace_ok; then log "weekly-pace erreicht — pausiere bis ~${PACE_RESUME_HOUR:-20}:00 CH"; sleep 300; continue; fi
  if ! peak_gate; then log "Peak-Stunde (UTC $(date -u +%H)) — pausiere 20min (API teurer)"; sleep 1200; continue; fi
  if ! usage_gate; then sleep 120; continue; fi

  CLAIM=$(curl -s -m 30 "$DISPATCHER/claim?worker=$WORKER_ID" 2>/dev/null || echo '{}')
  TICKET_ID=$(printf '%s' "$CLAIM" | jq -r '.id // empty' 2>/dev/null || true)
  if [ -z "$TICKET_ID" ]; then
    log "queue leer — warte 30s"
    sleep 30
    continue
  fi
  TICKET_TITLE=$(printf '%s' "$CLAIM" | jq -r '.title // ""')
  TICKET_DESC=$(printf '%s' "$CLAIM" | jq -r '.desc // ""')
  RETRIES=$(printf '%s' "$CLAIM" | jq -r '.retry_count // 0')
  log "ticket #$TICKET_ID (retry $RETRIES): $TICKET_TITLE"
  [ "${GLM_WORKER:-0}" = "1" ] && echo working > /tmp/w3-status

  # Heartbeat alle 60s (Lease 180s); fd-sauber in den Hintergrund
  ( while sleep 60; do curl -s "$DISPATCHER/heartbeat?ticket=$TICKET_ID" >/dev/null 2>&1; done ) >/dev/null 2>&1 &
  HB_PID=$!

  # Clone hart auf origin/main setzen (eigener Clone — reset ist hier ok)
  git checkout -q main 2>/dev/null || git checkout -qb main
  if ! git fetch -q origin main || ! git reset -q --hard origin/main; then
    log "git sync failed — Ticket zurückgeben"
    report retry "" "" "" "git fetch/reset failed on worker $WORKER_ID"
    stop_heartbeat
    sleep 30
    continue
  fi
  git clean -qfd

  # ---- Prompt bauen (eine Datei, kein Nesting) ----
  # Knappen Katalog ableiten (0 Modell-Token; volle Quelle bleibt im Repo).
  # Halbiert die Kosten pro Karte: voll ~109k Token, knapp ~52k (gemessen).
  SRC_CAT="$CLONE_PATH/scripts/skills/primitive-catalog.md"; [ -f "$SRC_CAT" ] || SRC_CAT="$CATALOG"
  CONCISE_CAT="/tmp/disp-$WORKER_ID-catalog.md"
  GEN_PY="/opt/development/magic-claude/scripts/concise-catalog.py"
  if [ -f "$GEN_PY" ]; then python3 "$GEN_PY" "$SRC_CAT" > "$CONCISE_CAT" 2>/dev/null && [ -s "$CONCISE_CAT" ] || cp "$SRC_CAT" "$CONCISE_CAT"; else cp "$SRC_CAT" "$CONCISE_CAT"; fi

  PROMPT_FILE="/tmp/disp-$WORKER_ID-prompt.txt"
  {
    cat <<'INSTR'
You are working inside a checked-out Go repository (OpenMagic, a Magic: The Gathering engine). Your job: implement the ticket's card(s) — as a DATA RECORD when possible, as a card handler otherwise — plus one behavioral test per card, WRITING THE FILES YOURSELF with your file tools.

STEP 0 — RECORD FIRST (cheapest tier wins):
If EVERY ability of a card is expressible as an AbilityDSL record (see the SHAPE
CATALOG below: trigger x effect vocabulary), do NOT write a handler for it.
Instead: (a) edit the card's entry in backend/data/carddb/<first-letter>.json —
set "abilities" to the record list and "status" to "manual"; (b) write the
behavioral test as backend/cards/taskTICKETID_<cardslug>_record_test.go using the
record harness from the shape catalog (LoadFromDir + CreateCard + RegisterCardAbilities
+ event + resolve). A card that is only stats + printed keywords needs NO abilities
at all — just verify/fix its record. Cards with any ability BEYOND the shape
vocabulary get a full HANDLER as before (a handler overrides the record, so always
implement the COMPLETE card in that case). A standard-looking ability the shape
vocabulary can't express: declare it like rule 5 but with SHAPE_DEMAND instead of
MISSING_PRIMITIVE.

STRICT RULES:
1. Do NOT explore the repository. No grep, no reading backend/cardfns/lib_*.go, no reading other handlers or tests. Your ONLY vocabulary is the SHAPE CATALOG and the PRIMITIVE CATALOG above the ticket. (Budget target: this whole task in well under 100k tokens.)
2. Per card create ONE new handler file: backend/cardfns/taskTICKETID_<cardslug>.go
   - self-registering, NO edits to any register file:
     func init() { game.CardHandlers["<Exact Card Name>"] = handleFn }
   - for instants/sorceries register in game.SpellHandlers instead (fires on resolution).
3. Per card create ONE test file: backend/cardfns/taskTICKETID_<cardslug>_test.go
   with ONE behavioral test named Test<CardSlugInCamelCase> that exercises the card's core effect.
4. BUNDLE tickets list 2-3 cards: implement EVERY card (own handler+test each). If ONE card needs a primitive the catalog does not have, SKIP exactly that card (no files for it) and declare the gap (rule 5); still implement the others.
5. NEVER fake or approximate a missing engine capability. If the catalog has no primitive for a needed effect, print these lines (one block per missing capability):
   MISSING_PRIMITIVE: <short kebab-case capability name>
   WHY: <2-4 sentences: which engine capability is missing and why the card cannot work without it>
   SKIPPED_CARD: <exact card name that you skipped because of this>   (only when you skipped a bundle card)
6. Compile-check mentally against the catalog signatures; do not invent functions or fields.
7. Your FINAL output lines must be exactly:
   TESTS: TestName1,TestName2   (comma-separated, empty if none)
   RESULT: FIXED                (or: RESULT: PARKED  if no card could be built)
INSTR
    # Kataloge VOR die (variable) Karte: statischer Prefix, cachebar; knappe Form.
    # Shape-Katalog zuerst (Record-Tier, Step 0), dann Primitive-Katalog.
    SHAPE_CAT="$CLONE_PATH/scripts/skills/shape-catalog.md"; [ -f "$SHAPE_CAT" ] || SHAPE_CAT="$LIVE_REPO/scripts/skills/shape-catalog.md"
    if [ -f "$SHAPE_CAT" ]; then
      echo ""
      echo "=== SHAPE CATALOG (data-record tier — check FIRST, see STEP 0) ==="
      cat "$SHAPE_CAT"
    fi
    echo ""
    echo "=== PRIMITIVE CATALOG (concise: signature + [dur] + short desc; ALL primitives listed) ==="
    cat "$CONCISE_CAT"
    echo ""
    echo "TICKET #$TICKET_ID: $TICKET_TITLE"
    echo ""
    printf '%s\n' "$TICKET_DESC"
  } > "$PROMPT_FILE"
  # TICKETID im Instruktionstext ersetzen
  sed -i "s/taskTICKETID_/task${TICKET_ID}_/g" "$PROMPT_FILE"

  # ---- Phase 1-3: Generieren → Fast-Gate → bounded Fix-Loop ----
  OUTCOME=""  # fixed | parked_prim | parked_fail
  PRIM=""; PRIM_WHY=""; GATE_TAIL=""
  : > "$TOK_FILE"   # Token-Zähler für dieses Ticket zurücksetzen
  attempt=1
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    MODEL=$(pick_model "$TICKET_TITLE" "$attempt" "$RETRIES")
    log "attempt $attempt/$MAX_ATTEMPTS (model $MODEL)"

    CLAUDE_OUT=$(claude_run --model "$MODEL" --permission-mode bypassPermissions \
      --max-turns "$WORKER_MAX_TURNS" < "$PROMPT_FILE")

    # Modell-Flakiness (Timeout/"model may not exist") ist meist TRANSIENT →
    # EINMAL mit DEMSELBEN (billigen) Modell neu, statt teuer auf pro zu springen.
    # Nur echte Gate-Fehler eskalieren via attempt-2 auf pro. Spart pro-Budget
    # (2026-07-21: ~30 flakes sprangen unnötig auf pro).
    if printf '%s' "$CLAUDE_OUT" | grep -qi "model.*not exist\|CLAUDE_TIMEOUT_OR_ERROR"; then
      log "flake on $MODEL — retry mit demselben Modell (transient)"
      CLAUDE_OUT=$(claude_run --model "$MODEL" --permission-mode bypassPermissions \
        --max-turns "$WORKER_MAX_TURNS" < "$PROMPT_FILE")
    fi

    # Infra-/Quota-Ausfall: Call scheiterte, KEINE Dateien entstanden → nicht
    # dem Ticket anlasten. Ticket ohne Fail-Zähler zurückgeben und pausieren,
    # bis eine Probe wieder antwortet (z.B. Ollama-Quota erschöpft; Resume beim
    # Reset automatisch). Verhindert stundenweises Fluten der wait-triage.
    if [ -z "$(git status --porcelain)" ] && printf '%s' "$CLAUDE_OUT" | grep -qiE "CLAUDE_TIMEOUT_OR_ERROR|quota|rate.?limit|too many requests|429|overloaded|insufficient|exhausted|billing"; then
      log "⚠️ API/Quota-Problem erkannt — Ticket #$TICKET_ID zurückgeben (infra), pausiere"
      [ "${GLM_WORKER:-0}" = "1" ] && echo paused > /tmp/w3-status
      report retry infra "" "" "api/quota outage on $WORKER_ID: $(printf '%s' "$CLAUDE_OUT" | tail -c 150 | tr '\n' ' ')"
      stop_heartbeat
      until PROBE=$(timeout 180 "$CLAUDE_BIN" -p --model "$MODEL_SONNET" --permission-mode bypassPermissions --max-turns 1 <<< "Reply with exactly: OK" 2>&1) && printf '%s' "$PROBE" | grep -q "OK"; do
        log "Probe negativ — nächster Versuch in 15 min"
        sleep 900
      done
      log "✅ API wieder erreichbar — weiter"
      continue 2
    fi

    # Missing primitive deklariert?
    if printf '%s' "$CLAUDE_OUT" | grep -q "^MISSING_PRIMITIVE:"; then
      PRIM=$(printf '%s' "$CLAUDE_OUT" | grep "^MISSING_PRIMITIVE:" | head -1 | sed 's/^MISSING_PRIMITIVE: *//')
      PRIM_WHY=$(printf '%s' "$CLAUDE_OUT" | grep "^WHY:" | head -1 | sed 's/^WHY: *//')
      # PARKED ohne gebaute Karten → ganzes Ticket parken. FIXED mit skip → weiter (Bundle-Teilfix).
      if printf '%s' "$CLAUDE_OUT" | grep -q "^RESULT: PARKED"; then
        OUTCOME="parked_prim"
        break
      fi
    fi

    # Hat Claude überhaupt Dateien geschrieben?
    if [ -z "$(git status --porcelain)" ]; then
      log "attempt $attempt: keine Dateien geschrieben"
      GATE_TAIL="Claude wrote no files (output tail: $(printf '%s' "$CLAUDE_OUT" | tail -c 300))"
      attempt=$((attempt + 1))
      continue
    fi

    # ---- Phase 2: Fast-Gate ----
    # Testnamen DETERMINISTISCH aus den neu angelegten/geänderten *_test.go
    # ableiten (nicht aus Claudes TESTS:-Zeile) — sonst läuft im Fallback die
    # ganze Suite und fremde flaky Tests killen den Fix (TestMasterWarcraft-
    # Vorfall 2026-07-19). Cross-Card-Schutz bleibt der 2h-Regression-Cron.
    NEW_TEST_FILES=$(cd "$CLONE_PATH" && git status --porcelain | awk '{print $2}' | grep '_test\.go$' || true)
    TESTS=""
    if [ -n "$NEW_TEST_FILES" ]; then
      TESTS=$(cd "$CLONE_PATH" && cat $NEW_TEST_FILES 2>/dev/null \
        | sed -n 's/^func \(Test[A-Za-z0-9_]*\).*/\1/p' | sort -u | paste -sd'|')
    fi
    if [ -z "$TESTS" ]; then
      # Fallback: Claudes TESTS:-Zeile (aber nie die ganze Suite)
      TESTS=$(printf '%s' "$CLAUDE_OUT" | grep "^TESTS:" | head -1 | sed 's/^TESTS: *//; s/ //g; s/,/|/g')
    fi
    if [ -z "$TESTS" ]; then
      log "❌ keine Tests geschrieben (attempt $attempt)"
      GATE_TAIL="No *_test.go written and no TESTS: line — a behavioral test per card is required."
      {
        echo ""
        echo "=== YOUR PREVIOUS ATTEMPT FAILED — fix the existing files, do not start over ==="
        echo "$GATE_TAIL"
      } >> "$PROMPT_FILE"
      attempt=$((attempt + 1))
      continue
    fi
    RUN_RE="^($TESTS)$"
    if BUILD_OUT=$(cd "$CLONE_PATH/backend" && "$GO" build ./... 2>&1); then
      # ./cards/ zusätzlich: Record-Tier-Tests (STEP 0) leben in backend/cards/
      if TEST_OUT=$(cd "$CLONE_PATH/backend" && timeout 300 "$GO" test ./cardfns/ ./cards/ -run "$RUN_RE" -count=1 2>&1); then
        # Vollständigkeits-Gate: jede Bundle-Karte braucht einen Handler ODER
        # eine SKIPPED_CARD-Deklaration. Ohne das verschwinden Karten still im
        # finished-Ticket (#8245: nur 1 von 3 gebaut, 2 verloren).
        CARD_COUNT=$(printf '%s\n' "$TICKET_DESC" | grep -c '^### ' || true)
        HANDLER_COUNT=$(cd "$CLONE_PATH" && git status --porcelain | awk '{print $2}' | grep 'backend/cardfns/.*\.go$' | grep -vc '_test\.go$' || true)
        # Record-Tier (STEP 0): eine Karte kann statt eines Handlers als
        # Datensatz gefixt sein — zählt ein carddb-Shard-Edit + Record-Test.
        RECORD_COUNT=$(cd "$CLONE_PATH" && git status --porcelain | awk '{print $2}' | grep -c 'backend/cards/.*_record_test\.go$' || true)
        SKIP_COUNT=$(printf '%s' "$CLAUDE_OUT" | grep -c '^SKIPPED_CARD:' || true)
        if [ "$CARD_COUNT" -gt 0 ] && [ $((HANDLER_COUNT + RECORD_COUNT + SKIP_COUNT)) -lt "$CARD_COUNT" ]; then
          log "❌ unvollständig: $CARD_COUNT Karten, aber nur $HANDLER_COUNT Handler + $RECORD_COUNT Records + $SKIP_COUNT Skips (attempt $attempt)"
          GATE_TAIL="INCOMPLETE BUNDLE: the ticket lists $CARD_COUNT cards but you wrote only $HANDLER_COUNT handler file(s), $RECORD_COUNT record test(s), and declared $SKIP_COUNT SKIPPED_CARD line(s). Implement EVERY card (record or handler), or declare each skipped card with MISSING_PRIMITIVE/WHY/SKIPPED_CARD lines."
          {
            echo ""
            echo "=== YOUR PREVIOUS ATTEMPT FAILED — fix the existing files, do not start over ==="
            echo "$GATE_TAIL"
          } >> "$PROMPT_FILE"
          attempt=$((attempt + 1))
          continue
        fi
        log "✅ fast-gate grün (tests: ${TESTS:-cardfns}, $HANDLER_COUNT Handler + $RECORD_COUNT Records / $CARD_COUNT Karten, $SKIP_COUNT Skips)"
        OUTCOME="gate_green"
        break
      else
        GATE_TAIL=$(printf '%s' "$TEST_OUT" | tail -c 2000)
        log "❌ tests rot (attempt $attempt)"
      fi
    else
      GATE_TAIL=$(printf '%s' "$BUILD_OUT" | tail -c 2000)
      log "❌ build rot (attempt $attempt)"
    fi

    # Fehlerkontext für den nächsten Versuch anhängen (bounded fix)
    {
      echo ""
      echo "=== YOUR PREVIOUS ATTEMPT FAILED — fix the existing files, do not start over ==="
      echo "$GATE_TAIL"
    } >> "$PROMPT_FILE"
    attempt=$((attempt + 1))
  done

  # ---- Ergebnis behandeln ----
  if [ "$OUTCOME" = "parked_prim" ]; then
    log "parked: missing primitive '$PRIM'"
    git reset -q --hard origin/main; git clean -qfd
    report parked missing_primitive "$PRIM" "$PRIM_WHY" ""
  elif [ "$OUTCOME" = "gate_green" ]; then
    # ---- Merge + Push (ff wenn möglich; Konflikte löst Claude) ----
    git add -A
    git commit -qm "fix(task-$TICKET_ID): $TICKET_TITLE (dispatcher-$WORKER_ID)" || true
    PUSHED=0
    for ptry in 1 2 3; do
      if git push -q origin main 2>/dev/null; then PUSHED=1; break; fi
      log "push rejected (try $ptry) — pull + ggf. Konflikt-Fix"
      if ! git pull -q --no-rebase origin main 2>/dev/null; then
        CONFLICTS=$(git diff --name-only --diff-filter=U | head -20)
        if [ -n "$CONFLICTS" ]; then
          printf 'Resolve the git merge conflicts in these files (conflict markers <<<<<<< ======= >>>>>>>), keep BOTH sides where compatible, then leave the files clean. Files:\n%s\n' "$CONFLICTS" \
            | CJ_TIMEOUT=300 claude_run --model "$MODEL_SONNET" \
               --permission-mode bypassPermissions --max-turns 10 >/dev/null 2>&1 || true
          git add -A
          git commit -qm "merge: resolve conflicts (task-$TICKET_ID)" || true
        else
          git merge --abort 2>/dev/null || true
        fi
      fi
    done
    if [ "$PUSHED" = 1 ]; then
      log "✅ pushed to origin/main"
      DEPLOY_NOTE="deploy skipped"
      if [ "$DEPLOY" = 1 ]; then
        if (cd "$CLONE_PATH/backend" && "$GO" build -o "$LIVE_REPO/bin/magic-api-server" ./api) 2>/dev/null; then
          (cd "$CLONE_PATH/backend" && "$GO" build -o "$LIVE_REPO/bin/dsl-check" ./tools/dsl_check/) 2>/dev/null || true
          if sudo -n systemctl restart magic-backend magic-frontend 2>/dev/null; then
            DEPLOY_NOTE="deployed + restarted"
          else
            DEPLOY_NOTE="binary built, restart failed (sudoers?)"
          fi
        else
          DEPLOY_NOTE="server build failed — binary NOT replaced"
        fi
      fi
      log "deploy: $DEPLOY_NOTE"
      SKIPS=$(collect_skips "$CLAUDE_OUT")
      [ "$SKIPS" != "[]" ] && log "bundle: $(printf '%s' "$SKIPS" | jq length) Karte(n) geskippt -> Dispatcher splittet"
      report fixed "" "" "" "$DEPLOY_NOTE (model attempts: $attempt)" "$SKIPS"
    else
      log "❌ push failed 3x — Ticket zurückgeben"
      git reset -q --hard origin/main; git clean -qfd
      report retry "" "" "" "push to origin/main failed 3x"
    fi
  else
    log "❌ $MAX_ATTEMPTS Versuche gescheitert — wait-triage"
    git reset -q --hard origin/main; git clean -qfd
    report parked max_retry_reached "" "" "gate tail: $(printf '%s' "$GATE_TAIL" | head -c 500)"
  fi

  stop_heartbeat
  log "cycle done"
  [ "$ONE_SHOT" = 1 ] && { log "ONE_SHOT — exit"; exit 0; }
done
