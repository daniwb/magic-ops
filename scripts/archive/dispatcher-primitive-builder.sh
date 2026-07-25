#!/bin/bash
# Nightly Primitive-Builder — arbeitet [VOCAB]-Tickets (col 19) im Batch ab.
# Bewiesenes 2-Lauf-Muster (2026-07-19, Sonnet): Lauf 1 baut (mit Exploration),
# Lauf 2 stellt fertig (Test + Katalog + Commit). Gate = NUR die eigenen neuen
# Tests (User-Entscheid: wie Karten; das Sicherheitsnetz ist der 2h-Regression-
# Cron). Grün → merge + push + Ticket schließen (vocab-requeue holt die
# BLOCKED_CARDS zurück). ENGINE_HOOK_NEEDED oder rot → Kommentar, Ticket bleibt.
set -uo pipefail

LOCK=/tmp/prim-builder.lock
exec 9>"$LOCK"; flock -n 9 || { echo "already running"; exit 0; }

export PATH=/usr/local/go/bin:$PATH
if [ "${GLM_WORKER:-0}" != "1" ]; then
  unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
fi

KB="${KB_URL:-https://kanboard.k.ezq.ch/jsonrpc.php}"
AUTH="${KB_USER:-admin}:${KB_TOKEN:-fda650985874506da62a737b9a7befc39a5873735a253de80fa2d5ee5c20}"
CLONE="${CLONE:-/tmp/work/prim-builder}"
REPO_SSH="${REPO_SSH:-git@github.com:daniwb/openmagic.git}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
LIVE_REPO="/opt/development/magic-new"
MAX_PRIMS="${MAX_PRIMS:-5}"          # Token-Deckel pro Nacht
MODEL="${MODEL:-claude-sonnet-5}"
COL_PRIORITY=19

log() { printf '[%s] prim-builder: %s\n' "$(date -Is)" "$*"; }
kb()  { curl -fsS -u "$AUTH" -H "Content-Type: application/json" -d "$1" "$KB"; }
comment() { # $1 tid, $2 text
  kb "$(jq -n --argjson t "$1" --arg c "$2" \
    '{jsonrpc:"2.0",id:1,method:"createComment",params:{task_id:$t,user_id:1,content:$c}}')" >/dev/null || true
}

# Usage-Gate (7d-Kappe zählt auch nachts; fail-open)
USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-95}"
usage_ok() {
  [ "$USAGE_LIMIT_PCT" -le 0 ] 2>/dev/null && return 0
  local tok body u7
  tok=$(jq -r '.claudeAiOauth.accessToken // empty' "$HOME/.claude/.credentials.json" 2>/dev/null || true)
  [ -z "$tok" ] && return 0
  body=$(curl -fsS --max-time 15 -H "Authorization: Bearer $tok" \
    -H "anthropic-beta: oauth-2025-04-20" https://api.anthropic.com/api/oauth/usage 2>/dev/null) || return 0
  u7=$(printf '%s' "$body" | jq -r '.seven_day.utilization // 0 | floor' 2>/dev/null || echo 0)
  u5=$(printf '%s' "$body" | jq -r '.five_hour.utilization // 0 | floor' 2>/dev/null || echo 0)
  # Dauerbetrieb: tagsüber auch das 5h-Fenster respektieren (Card-Worker nicht
  # aushungern); nachts (23-06 Zürich) darf das 5h-Fenster voll ausgefahren werden.
  local lim5="$USAGE_LIMIT_PCT" nh
  nh=$(TZ='Europe/Zurich' date +%H); nh=$((10#$nh))
  if [ "$nh" -ge 23 ] || [ "$nh" -lt 6 ]; then lim5=100; fi
  [ "$u5" -ge "$lim5" ] && { log "usage-gate: 5h=${u5}% (lim $lim5) — Abbruch"; return 1; }
  [ "$u7" -ge "$USAGE_LIMIT_PCT" ] && { log "usage-gate: 7d=${u7}% — Abbruch"; return 1; }
  return 0
}
usage_ok || exit 0

# ---- Clone vorbereiten ----
if [ ! -d "$CLONE/.git" ]; then
  GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone -q "$REPO_SSH" "$CLONE" || { log "clone failed"; exit 1; }
fi
cd "$CLONE"
git config user.email "prim-builder@magic"
git config user.name  "prim-builder"

# ---- VORLAUF: Dedup-Triage (Claude clustert semantische Duplikate,
#      Karten wandern aufs kanonische Ticket) — immer VOR dem Abarbeiten ----
bash /opt/development/magic-claude/scripts/vocab-dedup-triage.sh 2>&1 | sed 's/^/  /' || true

# ---- Offene [VOCAB]-Tickets (älteste zuerst) ----
TICKETS=$(kb '{"jsonrpc":"2.0","id":1,"method":"getAllTasks","params":{"project_id":2,"status_id":1}}' \
  | jq -c --argjson col "$COL_PRIORITY" \
    '[.result[] | select(.column_id==$col) | select(.title|startswith("[VOCAB]"))] | sort_by(.id) | .[]' )

BUILT=0
while IFS= read -r T; do
  [ -z "$T" ] && continue
  [ "$BUILT" -ge "$MAX_PRIMS" ] && break
  TID=$(printf '%s' "$T" | jq -r '.id')
  TITLE=$(printf '%s' "$T" | jq -r '.title')
  DESC=$(printf '%s' "$T" | jq -r '.description // ""')

  # Schon mal gescheitert? Dann nicht jede Nacht Tokens verbrennen — Mensch
  # löscht den Kommentar oder setzt RETRY_FAILED=1 für einen neuen Versuch.
  if [ "${RETRY_FAILED:-0}" != "1" ]; then
    PRIOR_FAIL=$(kb "$(jq -n --argjson t "$TID" '{jsonrpc:"2.0",id:1,method:"getAllComments",params:{task_id:$t}}')" \
      | jq -r '[.result[]? | .comment | select(test("PRIM-BUILDER: (failed|engine-hook)"))] | length')
    [ "${PRIOR_FAIL:-0}" -gt 0 ] && { log "#$TID übersprungen (früherer Fehlschlag)"; continue; }
  fi

  # Usage-Gate PRO TICKET: ein Batch kann 2h laufen — nur am Start prüfen
  # ließ ihn am 2026-07-20 über die 95%-Weekly-Bremse hinaus bauen
  usage_ok || { log "usage-gate mitten im Batch — Abbruch"; break; }

  # Liste kann in langen Batches veraltet sein (Triage/andere schließen parallel):
  # vor dem Bauen prüfen, ob das Ticket noch offen ist (#8561-Vorfall 2026-07-19)
  STILL_OPEN=$(kb "$(jq -n --argjson t "$TID" '{jsonrpc:"2.0",id:1,method:"getTask",params:{task_id:$t}}')" | jq -r '.result.is_active // "0"')
  [ "$STILL_OPEN" != "1" ] && { log "#$TID inzwischen geschlossen — skip"; continue; }

  log "baue #$TID: $TITLE"
  git checkout -q main && git fetch -q origin main && git reset -q --hard origin/main && git clean -qfd
  BR="prim/vocab-$TID"
  git checkout -qB "$BR"

  # ---- Lauf 1: bauen ----
  P1=/tmp/prim-$TID-p1.txt
  {
    cat scripts/skills/build-engine-primitive.md
    echo ""; echo "=== DEMAND: [VOCAB] ticket #$TID ==="; printf '%s\n' "$TITLE"; printf '%s\n' "$DESC"
    echo ""; echo "=== SESSION RULES ==="
    echo "- Full checkout, local branch $BR. You MAY explore backend/game and backend/cardfns."
    echo "- NEVER push, never touch git remotes."
    echo "- Additive-first (new backend/cardfns/lib_*.go). If a real engine hook in backend/game/ is unavoidable and you are not CERTAIN it is safe: print ENGINE_HOOK_NEEDED: <slug> | <what a human must add> and STOP."
    echo "- Do NOT run the full test suites (the 2h regression cron covers that). Iterate only with focused -run tests."
  } > "$P1"
  OUT1=$(timeout 2400 "$CLAUDE_BIN" -p --model "$MODEL" --permission-mode bypassPermissions --max-turns 100 < "$P1" 2>>/tmp/prim-builder-claude.err || echo TIMEOUT)

  if printf '%s' "$OUT1" | grep -q "^ENGINE_HOOK_NEEDED:"; then
    HOOK=$(printf '%s' "$OUT1" | grep "^ENGINE_HOOK_NEEDED:" | head -1)
    log "#$TID braucht Engine-Hook — bleibt für Mensch"
    comment "$TID" "PRIM-BUILDER: engine-hook nötig, nicht automatisch gebaut. $HOOK"
    continue
  fi

  # ---- Lauf 2: fertigstellen (Test + Katalog + Commit) ----
  P2=/tmp/prim-$TID-p2.txt
  {
    echo "Continue the primitive job on branch $BR. The implementation may already exist — do not rewrite working code."
    echo "1. Ensure ONE focused behavioral test file (backend/cardfns/..._test.go) covering the core behavior + the most dangerous edge case."
    echo "2. Iterate ONLY with: cd backend && /usr/local/go/bin/go test ./cardfns/ -run '<YourTestNames>' -count=1"
    echo "3. Add the primitive to scripts/skills/primitive-catalog.md (signature + [dur:] tag) — MANDATORY."
    echo "4. git add + git commit on this branch. NEVER push."
    echo "5. Final line: BUILT: <slug> | thin-wrapper   (or FAILED: <reason>)"
  } > "$P2"
  timeout 1800 "$CLAUDE_BIN" -p --model "$MODEL" --permission-mode bypassPermissions --max-turns 60 < "$P2" >>/tmp/prim-builder-claude.err 2>&1 || true
  # Falls uncommitted Arbeit liegt: selbst committen (Claude vergisst das gern)
  if [ -n "$(git status --porcelain)" ]; then
    git add -A && git commit -qm "feat(primitive): $TITLE (nightly builder)" || true
  fi

  # ---- Gate: NUR die eigenen neuen Tests ----
  NEW_TEST_FILES=$(git diff main --name-only | grep '_test\.go$' || true)
  if [ -z "$NEW_TEST_FILES" ]; then
    log "#$TID: keine Tests entstanden — failed"
    comment "$TID" "PRIM-BUILDER: failed — kein Test entstanden (Branch $BR lokal auf $(hostname))."
    continue
  fi
  TESTS=$(cat $NEW_TEST_FILES 2>/dev/null | sed -n 's/^func \(Test[A-Za-z0-9_]*\).*/\1/p' | sort -u | paste -sd'|')
  if ! (cd backend && timeout 300 /usr/local/go/bin/go build ./... >/dev/null 2>&1 \
     && timeout 300 /usr/local/go/bin/go test ./cardfns/ -run "^($TESTS)$" -count=1 >/tmp/prim-$TID-gate.log 2>&1); then
    log "#$TID: Gate rot — failed"
    comment "$TID" "PRIM-BUILDER: failed — eigener Test rot: $(tail -c 400 /tmp/prim-$TID-gate.log 2>/dev/null). Branch $BR lokal."
    continue
  fi

  # ---- Merge + Push (Retry gegen parallele Card-Worker) ----
  git checkout -q main && git pull -q --no-rebase origin main
  if ! git merge -q --no-ff "$BR" -m "feat(primitive): $TITLE (nightly builder, [VOCAB] #$TID)"; then
    git merge --abort 2>/dev/null || true
    comment "$TID" "PRIM-BUILDER: failed — Merge-Konflikt mit main. Branch $BR lokal."
    continue
  fi
  PUSHED=0
  for i in 1 2 3; do
    git push -q origin main 2>/dev/null && { PUSHED=1; break; }
    git pull -q --no-rebase origin main || true
  done
  if [ "$PUSHED" != 1 ]; then
    comment "$TID" "PRIM-BUILDER: failed — push nach 3 Versuchen abgelehnt."
    continue
  fi

  SHA=$(git rev-parse --short HEAD)
  log "#$TID gebaut + gemerged ($SHA)"
  comment "$TID" "PRIM-BUILDER: gebaut + gemerged ($SHA). Tests: $TESTS grün. Katalog aktualisiert. Closing → requeue der BLOCKED_CARDS."
  kb "$(jq -n --argjson t "$TID" '{jsonrpc:"2.0",id:1,method:"closeTask",params:{task_id:$t}}')" >/dev/null || true
  BUILT=$((BUILT + 1))
done <<< "$TICKETS"

# ---- Deploy einmal am Batch-Ende ----
if [ "$BUILT" -gt 0 ]; then
  git checkout -q main && git pull -q --no-rebase origin main || true
  if (cd backend && timeout 590 /usr/local/go/bin/go build -o "$LIVE_REPO/bin/magic-api-server" ./api); then
    sudo -n systemctl restart magic-backend magic-frontend 2>/dev/null \
      && log "deployed + restarted" || log "Build ok, restart failed"
  else
    log "WARN: Server-Build rot — Binary NICHT ersetzt"
  fi
fi
# ---- Voll-Regression EINMAL am Batch-Ende (nicht pro Primitiv; eigener flock) ----
if [ "$BUILT" -gt 0 ]; then
  log "starte Voll-Regression (einmalig am Batch-Ende)…"
  /opt/development/magic-new/scripts/kanboard-regression-check.sh \
    >> /opt/development/magic-new/.bugfixer-logs/regression-cron.log 2>&1 || true
  log "Regression: $(cat /opt/development/magic-new/.bugfixer-logs/regression-status.txt 2>/dev/null || echo 'kein Status')"
fi
log "Nacht-Batch fertig: $BUILT Primitiv(e) gebaut"
