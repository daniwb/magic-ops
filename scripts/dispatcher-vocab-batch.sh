#!/bin/bash
# VOCAB-Batch-Builder — Ablauf wie die interaktiven VOCAB-Runden:
#   1. Bis zu BATCH_SIZE (5) Subagents bauen PARALLEL, je eigener /tmp-Clone
#      (direkter git clone, KEIN Worktree). Jeder testet SEINE eigene Sache
#      (focused go test der neuen Tests) in seinem Clone.
#   2. BARRIERE: warten bis alle fertig.
#   3. Wenn alle fertig: Integration in EINEN Clone (Branches nacheinander
#      gemerged, jeder Merge build-gated → isoliert einen Konflikt-Verursacher),
#      dann VOLLE Regression (go test ./... -count=1), dann push + deploy.
#   4. Erfolgreiche Tickets → vocab-close; danach kanboard-regression-check (mail-on-red).
#
# Zählt ?all=1 (inkl. gescheiterte). Skip-Liste gegen Deadlock (kein Retry-Cap in
# vocab-fail): nach MAX_ATTEMPTS Fehlschlägen wird ein VOCAB übersprungen.
# Exit-Codes: 0 = Batch gelaufen/leer, 2 = STUCK (alle Rest-VOCAB skip-gelistet).
set -uo pipefail

export PATH=/usr/local/go/bin:$PATH
unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN   # echtes Claude-Backend

DISP="${DISP:-http://localhost:9999}"
REPO_SSH="${REPO_SSH:-git@github.com:daniwb/openmagic.git}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
LIVE_REPO="/opt/development/magic-new"
GO=/usr/local/go/bin/go
MODEL="${MODEL:-claude-sonnet-5}"
BATCH_SIZE="${BATCH_SIZE:-5}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
SKIP="${SKIP:-/tmp/vocab-skip.list}"
SKIP_LOCK="/tmp/vocab-skip.lock"
WORKDIR_BASE="${WORKDIR_BASE:-/tmp/work/vbatch}"
RES_DIR="/tmp/orch/vbatch-res"

mkdir -p "$RES_DIR"; touch "$SKIP"
log() { printf '[%s] vbatch: %s\n' "$(date -Is)" "$*"; }

# --- Manuelle Pause (persistent, auto-resume nach Ablauf) -------------------
# Wirkt auf den NÄCHSTEN Batch — ein bereits laufender Batch läuft ungestört durch,
# da laufende Prozesse die Skriptänderung nicht neu lesen.
PAUSE_FILE="${PAUSE_FILE:-/opt/development/magic-claude/.orch-pause-until}"
if [ -f "$PAUSE_FILE" ] && [ "$(date +%s)" -lt "$(cat "$PAUSE_FILE" 2>/dev/null || echo 0)" ]; then
  log "Pause aktiv bis $(date -d @"$(cat "$PAUSE_FILE")" '+%F %T' 2>/dev/null) — Batch übersprungen"
  sleep 300; exit 0
fi
# Weekly-Pace-Gate (Variante B): über Pace → Batch aus bis ~20:00 CH
source /opt/development/magic-claude/scripts/lib-pace-gate.sh 2>/dev/null || true
if declare -f pace_ok >/dev/null && ! pace_ok; then
  log "weekly-pace erreicht — Batch übersprungen bis ~${PACE_RESUME_HOUR:-20}:00 CH"
  sleep 300; exit 0
fi

skip_bump() {  # $1=VID
  ( flock 7
    local vid=$1 n
    n=$(awk -v v="$vid" '$1==v{print $2}' "$SKIP" | head -1)
    n=$(( ${n:-0} + 1 ))
    grep -v "^$vid " "$SKIP" > "$SKIP.tmp" 2>/dev/null || true
    echo "$vid $n" >> "$SKIP.tmp"; mv "$SKIP.tmp" "$SKIP"
  ) 7>"$SKIP_LOCK"
}
skip_clear() {  # $1=VID
  ( flock 7
    grep -v "^$1 " "$SKIP" > "$SKIP.tmp" 2>/dev/null || true
    mv "$SKIP.tmp" "$SKIP"
  ) 7>"$SKIP_LOCK"
}

# --- Claude-Aufruf MIT Token-Erfassung (Muster: dispatcher-worker-real.sh) --
# --output-format json liefert .result (Text, damit die bestehende
# Text-Parsing-Logik unverändert bleibt) UND .modelUsage (kumulativ über alle
# Turns/Modelle). Die Summe wandert in eine Datei pro VOCAB, weil build_one in
# einer Subshell läuft und Variablen die nicht überleben.
# Ohne das blieben ALLE [VOCAB]-Tickets bei tokens=0, obwohl ein Primitive-Build
# (bis 100 Turns) deutlich teurer ist als ein Karten-Ticket (2026-07-28).
VTOK_FILE=""
vclaude() { # $1=timeout  $2=max-turns   (Prompt via stdin)
  local to="$1" turns="$2" raw txt used
  raw=$(timeout "$to" "$CLAUDE_BIN" -p --output-format json --model "$MODEL" \
        --permission-mode bypassPermissions --max-turns "$turns" 2>>/tmp/vbatch-claude.err) \
    || { echo TIMEOUT; return 0; }
  used=$(printf '%s' "$raw" | jq -r 'if (type=="object" and .modelUsage) then ([.modelUsage[] | (.inputTokens//0)+(.outputTokens//0)+(.cacheReadInputTokens//0)+(.cacheCreationInputTokens//0)] | add // 0) elif type=="object" then ((.usage.input_tokens//0)+(.usage.cache_creation_input_tokens//0)+(.usage.cache_read_input_tokens//0)+(.usage.output_tokens//0)) else 0 end' 2>/dev/null)
  [ -n "$used" ] && [ "$used" != 0 ] && [ -n "$VTOK_FILE" ] && echo "$used" >> "$VTOK_FILE"
  txt=$(printf '%s' "$raw" | jq -r '.result // empty' 2>/dev/null)
  if [ -n "$txt" ]; then printf '%s' "$txt"; else printf '%s' "$raw"; fi
}
# Bisher verbrauchte Tokens dieses VOCAB (0, wenn nichts erfasst).
vtok() { [ -n "$VTOK_FILE" ] && [ -f "$VTOK_FILE" ] && awk '{s+=$1} END{print s+0}' "$VTOK_FILE" || echo 0; }

# --- EIN VOCAB bauen + SELBST testen (parallel, KEIN Merge) ----------------
# Schreibt Ergebnis nach $RES_DIR/<slot>:  "OK<TAB>VID<TAB>BR<TAB>CLONE<TAB>TITLE<TAB>BLK"
# oder gar nichts (= Fehlschlag; vocab-fail/skip schon erledigt).
build_one() {
  local slot=$1 V=$2
  local clone="$WORKDIR_BASE-$slot"
  local res="$RES_DIR/$slot"; : > "$res"
  local VID TITLE DESC BLK BR
  VID=$(jq -r '.id'      <<<"$V")
  TITLE=$(jq -r '.title' <<<"$V")
  DESC=$(jq -r '.descr'  <<<"$V")
  BLK=$(jq -r '.blocked' <<<"$V")
  BR="prim/vbatch-$VID"
  VTOK_FILE="/tmp/vbatch-tok-$VID"; : > "$VTOK_FILE"

  sleep $(( (slot - 1) * 8 ))   # Stagger gegen gleichzeitige go-build-RAM-Peaks
  log "slot$slot baue #$VID ($BLK Karten): $TITLE"
  curl -s "$DISP/vocab-claim?id=$VID&worker=vbatch-$slot&model=$(printf '%s' "$MODEL" | jq -sRr @uri)" >/dev/null 2>&1 || true

  [ -d "$clone/.git" ] || GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone -q "$REPO_SSH" "$clone" \
    || { log "slot$slot clone failed"; curl -s "$DISP/vocab-fail?id=$VID&reason=clone-failed&tok=$(vtok)" >/dev/null; skip_bump "$VID"; return; }
  cd "$clone" || { skip_bump "$VID"; return; }
  git config user.email vbatch@magic; git config user.name vbatch
  git checkout -q main && git fetch -q origin main && git reset -q --hard origin/main && git clean -qfd
  git checkout -qB "$BR"

  local P1=/tmp/vbatch-$slot-$VID-p1.txt
  { cat scripts/skills/build-engine-primitive.md 2>/dev/null
    echo ""; echo "=== DEMAND: $TITLE ==="; printf '%s\n' "$DESC"
    echo ""; echo "=== RULES ==="
    echo "- STEP 0 (MANDATORY, FIRST): grep backend/cardfns/ and backend/game/ for an EXISTING primitive/field/method that already provides THIS capability (demand often uses different words than the real symbol). If one GENUINELY covers it (right filter/scope/duration, not merely related), print exactly one line 'ALREADY_EXISTS: <exact func or field name>' and STOP. Be STRICT: an unfiltered version when a filtered one is needed does NOT count. When in doubt, build."
    echo "- Full checkout, branch $BR. Explore backend/game+cardfns allowed."
    echo "- NEVER push. Additive-first (new backend/cardfns/lib_*.go). Engine hook in backend/game/ only if unavoidable and CERTAIN safe, else print ENGINE_HOOK_NEEDED: <slug> | <what> and STOP."
    echo "- Do NOT run full suites; iterate with focused -run tests."
  } > "$P1"
  local OUT1
  OUT1=$(vclaude 2400 100 < "$P1")

  if printf '%s' "$OUT1" | grep -q "^ENGINE_HOOK_NEEDED:"; then
    local HOOK; HOOK=$(printf '%s' "$OUT1" | grep "^ENGINE_HOOK_NEEDED:" | head -1)
    log "slot$slot #$VID engine-hook nötig"
    curl -s "$DISP/vocab-fail?id=$VID&reason=$(printf '%s' "engine-hook: $HOOK" | jq -sRr @uri)&tok=$(vtok)" >/dev/null; skip_bump "$VID"; return
  fi
  if printf '%s' "$OUT1" | grep -q "^ALREADY_EXISTS:"; then
    local EXFN; EXFN=$(printf '%s' "$OUT1" | grep "^ALREADY_EXISTS:" | head -1 | sed 's/^ALREADY_EXISTS: *//' | tr -d '`()' | awk '{print $1}')
    if [ -n "$EXFN" ] && grep -rqE "func +$EXFN\b|^[[:space:]]*$EXFN[[:space:]]+[A-Za-z\[]" "$clone/backend/cardfns/" "$clone/backend/game/" 2>/dev/null; then
      log "slot$slot #$VID bereits vorhanden ($EXFN) — schließe"
      curl -s "$DISP/vocab-close?id=$VID&tok=$(vtok)" >/dev/null; skip_clear "$VID"; return
    fi
    log "slot$slot #$VID: ALREADY_EXISTS '$EXFN' nicht verifizierbar — baue trotzdem"
  fi

  local P2=/tmp/vbatch-$slot-$VID-p2.txt
  echo "Continue on branch $BR. Ensure ONE focused behavioral test (backend/cardfns/..._test.go, core + worst edge). Iterate: cd backend && $GO test ./cardfns/ -run '<Names>' -count=1. Add primitive to scripts/skills/primitive-catalog.md (signature + [dur:]). git add+commit. NEVER push. Final: BUILT: <slug> or FAILED: <reason>." > "$P2"
  vclaude 1800 60 < "$P2" >>/tmp/vbatch-claude.err 2>&1 || true
  [ -n "$(git status --porcelain)" ] && { git add -A; git commit -qm "feat(primitive): $TITLE (vbatch)" || true; }

  local NEW_TESTS TESTS
  NEW_TESTS=$(git diff main --name-only | grep '_test\.go$' || true)
  if [ -z "$NEW_TESTS" ]; then
    log "slot$slot #$VID: kein Test — fail"; curl -s "$DISP/vocab-fail?id=$VID&reason=no-test&tok=$(vtok)" >/dev/null; skip_bump "$VID"; return
  fi
  TESTS=$(cat $NEW_TESTS 2>/dev/null | sed -n 's/^func \(Test[A-Za-z0-9_]*\).*/\1/p' | sort -u | paste -sd'|')
  # SELBST-Test: nur die neuen Tests dieses Tickets (schnell, im eigenen Clone)
  if ! (cd backend && timeout 300 "$GO" build ./... >/dev/null 2>&1 \
     && timeout 300 "$GO" test ./cardfns/ -run "^($TESTS)$" -count=1 >/tmp/vbatch-$slot-$VID-gate.log 2>&1); then
    log "slot$slot #$VID: Self-Test rot — fail"; curl -s "$DISP/vocab-fail?id=$VID&reason=gate-red&tok=$(vtok)" >/dev/null; skip_bump "$VID"; return
  fi

  log "slot$slot #$VID: gebaut + self-getestet OK (Branch $BR)"
  printf 'OK\t%s\t%s\t%s\t%s\t%s\t%s\n' "$VID" "$BR" "$clone" "$TITLE" "$BLK" "$(vtok)" > "$res"
}

# --- Auswahl: bis BATCH_SIZE, meiste-Karten-zuerst, Skip-Liste raus ---------
LIST=$(curl -fsS -m 30 "$DISP/vocab-list?all=1" 2>/dev/null || echo 'null')
TOTAL=$(jq '(. // []) | length' <<<"$LIST" 2>/dev/null || echo 0)
if [ "$TOTAL" = 0 ]; then log "0 offene VOCAB"; exit 0; fi
SKIPIDS=$(awk -v m="$MAX_ATTEMPTS" '$2>=m{print $1}' "$SKIP" | paste -sd, )
ELIG=$(jq -c --arg skip "$SKIPIDS" '
  (. // [])
  | ($skip | split(",") | map(select(length>0) | tonumber)) as $s
  | map(select(.id as $i | ($s | index($i)) | not))
  | sort_by(-.blocked) | .['"0:$BATCH_SIZE"']' <<<"$LIST")
N=$(jq 'length' <<<"$ELIG")
if [ "$N" = 0 ]; then
  log "STUCK: alle $TOTAL Rest-VOCAB skip-gelistet: $(awk -v m="$MAX_ATTEMPTS" '$2>=m{print $1}' "$SKIP" | paste -sd,)"
  exit 2
fi

# --- Phase 1+2: 5 Subagents parallel bauen + self-testen, dann Barriere -----
rm -f "$RES_DIR"/* 2>/dev/null || true
log "Batch: $N von $TOTAL offenen VOCAB — 5 Subagents bauen parallel (Slots 1-$N)"
pids=(); slot=0
while IFS= read -r V; do slot=$((slot+1)); build_one "$slot" "$V" & pids+=($!); done < <(jq -c '.[]' <<<"$ELIG")
wait "${pids[@]}" 2>/dev/null || true
log "Barriere: alle $N Subagents fertig — starte Integration"

# --- Phase 3: Integration (mergen, build-gated) in EINEN Clone --------------
INT="$WORKDIR_BASE-1"
[ -d "$INT/.git" ] || { log "Integration-Clone fehlt — Abbruch"; exit 0; }
git -C "$INT" checkout -q main && git -C "$INT" fetch -q origin main && git -C "$INT" reset -q --hard origin/main && git -C "$INT" clean -qfd

MERGED=()   # "VID BR"
while IFS=$'\t' read -r st VID BR CLONE TITLE BLK TOK; do
  [ "$st" = OK ] || continue
  [ -n "${VID:-}" ] || continue
  # Branch aus dem Slot-Clone in den Integration-Clone holen (lokaler Pfad-Fetch)
  if [ "$CLONE" != "$INT" ]; then
    git -C "$INT" fetch -q "$CLONE" "$BR:$BR" 2>/dev/null || { log "#$VID: fetch Branch fehlgeschlagen — fail"; curl -s "$DISP/vocab-fail?id=$VID&reason=fetch-branch&tok=${TOK:-0}" >/dev/null; skip_bump "$VID"; continue; }
  fi
  if ! git -C "$INT" merge -q --no-ff "$BR" -m "feat(primitive): $TITLE (vbatch, vocab #$VID)"; then
    git -C "$INT" merge --abort 2>/dev/null || true
    log "#$VID: Merge-Konflikt gegen Batch — fail"; curl -s "$DISP/vocab-fail?id=$VID&reason=merge-conflict&tok=${TOK:-0}" >/dev/null; skip_bump "$VID"; continue
  fi
  # Build-Gate nach jedem Merge → isoliert einen Verursacher, der andere bricht
  if ! (cd "$INT/backend" && timeout 300 "$GO" build ./... >/dev/null 2>&1); then
    log "#$VID: bricht Integration-Build — rückgängig, fail"; git -C "$INT" reset -q --hard HEAD~1
    curl -s "$DISP/vocab-fail?id=$VID&reason=integration-build-red&tok=${TOK:-0}" >/dev/null; skip_bump "$VID"; continue
  fi
  MERGED+=("$VID ${TOK:-0}"); log "#$VID gemerged + Build grün"
done < <(cat "$RES_DIR"/* 2>/dev/null)

if [ "${#MERGED[@]}" = 0 ]; then log "Batch: nichts erfolgreich integriert"; exit 0; fi

# --- Phase 3b: VOLLE Regression auf dem integrierten main -------------------
log "Regression: go test ./... -count=1 auf ${#MERGED[@]} integrierte Tickets"
REG_LOG=/tmp/vbatch-regression.log
if (cd "$INT/backend" && timeout 1200 "$GO" build ./... >"$REG_LOG" 2>&1 \
   && timeout 1200 "$GO" test ./... -count=1 >>"$REG_LOG" 2>&1); then
  log "Regression: GRÜN"
else
  # Baseline hat bekannte cardfns-Failures (siehe orchestrator_phase_system / vocab-session).
  # Nicht hart blocken — der post-push kanboard-regression-check (baseline-bewusst) mailt bei ECHTER Regression.
  FAILS=$(grep -c '^--- FAIL' "$REG_LOG" 2>/dev/null || echo '?')
  log "Regression: Tests mit Failures ($FAILS) — Build grün, fahre fort (baseline-check mailt bei echter Regression)"
fi

# --- Phase 4: push + deploy + vocab-close -----------------------------------
PUSHED=0
for i in 1 2 3; do git -C "$INT" push -q origin main 2>/dev/null && { PUSHED=1; break; }; git -C "$INT" pull -q --no-rebase origin main || true; done
if [ "$PUSHED" != 1 ]; then log "push fehlgeschlagen — Tickets bleiben offen (nächste Runde)"; exit 0; fi

(cd "$INT/backend" && timeout 590 "$GO" build -o "$LIVE_REPO/bin/magic-api-server" ./api) \
  && sudo -n systemctl restart magic-backend magic-frontend 2>/dev/null && log "deployed" || log "deploy skipped/failed"

for m in "${MERGED[@]}"; do
  vid="${m%% *}"; vtk="${m##* }"; log "vocab-close #$vid (requeued blockierte Karten, ${vtk} tok)"; curl -s "$DISP/vocab-close?id=$vid&tok=$vtk" >/dev/null; skip_clear "$vid"
done

# Stale-park sweep: frisch gelandete Primitives gegen ALLE fremden Parks prüfen
# (vocab-close requeued nur die eigenen Kinder). Report-only, requeue bleibt
# ein bewusster Precheck-Schritt — siehe reports/ollama-triage-summary-2026-07-27.md.
SWEEP_OUT=$("$(dirname "$0")/stale-park-sweep.sh" 2>/dev/null | tail -1) && log "Stale-park sweep: $SWEEP_OUT" || true

/opt/development/magic-new/scripts/kanboard-regression-check.sh >> /opt/development/magic-new/.bugfixer-logs/regression-cron.log 2>&1 || true
log "Regression-Status: $(cat /opt/development/magic-new/.bugfixer-logs/regression-status.txt 2>/dev/null || echo '?')"
log "Batch fertig — ${#MERGED[@]} VOCAB gebaut+gemerged"
