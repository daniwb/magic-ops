#!/bin/bash
# Dispatcher-Worker REPARSE-Ära (2026-08-01) — arbeitet REPARSE-MAP-Tickets ab:
# ein Ticket = eine Miss-Shape aus der Demand-Table, Erfolg = Eligibility-Delta.
# Ersetzt dispatcher-worker-real.sh (Karten-Handler-Ära) für die neue Fabrik.
#
#   Phase 1: Claude erweitert scripts/paragraph/reparse.py (o. slotparse) nach
#            dem Worker-Contract (scripts/skills/reparse-worker-contract.md).
#   Phase 2: Harness-Gate = go build + Vocab/Shape-Tests + Eligibility-Delta>0
#            (reparse.py --review-pile, ~5s).
#   Phase 3: bounded Fix-Loop (MAX_ATTEMPTS), dann Branch-Push reparse/task-<id>.
#            KEIN Push auf main, KEIN Deploy — der Integrator merged, flippt
#            Batches, fährt die volle Suite und deployed (reparse-plan.md).
# Verdicts (Contract): DONE | NEEDS_PRIMITIVE | SEMANTIC_GAP | AMBIGUOUS | NOT_A_SHAPE
#   DONE            -> report fixed (Note: Delta + Branch)
#   NEEDS_PRIMITIVE -> report parked/missing_primitive (Dispatcher filed Demand-Ticket)
#   sonstige Parks  -> report parked/max_retry_reached -> wait-triage (Mensch)
set -uo pipefail

WORKER_ID="${1:-r1}"
CLONE_PATH="${2:-/tmp/work/disp-$WORKER_ID}"
DISPATCHER="${DISPATCHER:-http://localhost:9999}"
REPO_SSH="${REPO_SSH:-git@github.com:daniwb/openmagic.git}"
GO=/usr/local/go/bin/go
export PATH="/usr/local/go/bin:$PATH"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
export GOCACHE="${GOCACHE:-/opt/development/.gocache-magic}"
mkdir -p "$GOCACHE" 2>/dev/null || true
MIRROR="${MIRROR:-/opt/development/openmagic-mirror.git}"

# TIER=engine (Fable-Worker): claimt NUR REPARSE-ENGINE-Tickets, Modell Fable,
# großes Budget, Branch-Präfix reparse/engine-task-* (integrator-lite landet
# diese nach VOLLER Suite automatisch). Default: map (Sonnet-Fleet).
TIER="${TIER:-map}"
if [ "$TIER" = "engine" ]; then
  # 2026-08-03 (Dani: 10% usage for ~500 cards is too little): engine tier
  # runs SONNET first — Fable only on attempt 2 (MODEL_ESCALATE). Fable-priced
  # infrastructure rounds were the night's cost driver.
  MODEL="${MODEL:-claude-sonnet-5}"
  WORKER_MAX_TURNS="${WORKER_MAX_TURNS:-250}"
  CLAUDE_TIMEOUT="${CLAUDE_TIMEOUT:-7200}"
fi
MODEL="${MODEL:-claude-sonnet-5}"
# Eskalation: Versuch 2 (nach Gate-Fail) läuft auf Fable statt Sonnet-Retry —
# Sonnet ist bisher 3/3 im Erstversuch, Eskalation bleibt der seltene Pfad.
MODEL_ESCALATE="${MODEL_ESCALATE:-claude-fable-5}"
# Parser-Engineering braucht mehr Turns als eine Karte (reproduce -> mappen ->
# --card-Verify gegen Oracle-Text -> Tests). 20 wäre sicher zu wenig.
WORKER_MAX_TURNS="${WORKER_MAX_TURNS:-140}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-2}"
CLAUDE_TIMEOUT="${CLAUDE_TIMEOUT:-1800}"
ONE_SHOT="${ONE_SHOT:-0}"

USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-99}"
USAGE_GATE_TTL="${USAGE_GATE_TTL:-180}"
USAGE_CACHE="${USAGE_CACHE:-/tmp/claude-usage-gate.json}"
PAUSE_FILE="${PAUSE_FILE:-/opt/development/magic-claude/.orch-pause-until}"
source /opt/development/magic-claude/scripts/lib-pace-gate.sh 2>/dev/null || true

# env hygiene: geerbtes Ollama-Routing zerlegt jeden Claude-Call — AUSSER der
# Worker läuft absichtlich auf Ollama Cloud (OLLAMA_WORKER=1, eigene Quota,
# keine Usage-/Pace-Gates; Modell via OLLAMA_MODEL, Test 2026-08-03:
# deepseek-v4-flash:0731-cloud). Qualität sichern die Gates + Integrator.
if [ "${OLLAMA_WORKER:-0}" = "1" ]; then
  # OLLAMA_URL: default = local ollama (cloud routing). Set to the 395+ box
  # (http://192.168.1.251:8080) for the fully-local $0 lane (2026-08-03).
  export ANTHROPIC_BASE_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
  export ANTHROPIC_AUTH_TOKEN=ollama
  unset ANTHROPIC_API_KEY
  MODEL="${OLLAMA_MODEL:-deepseek-v4-flash:0731-cloud}"
  MODEL_ESCALATE="$MODEL"   # kein Fable auf der Gratis-Schiene — same-model retry
  USAGE_LIMIT_PCT=0
  # Claude CLI fires auxiliary requests (conversation-title generation etc.)
  # alongside the main run; on a single-slot local server the answers got
  # CROSSED — the worker's "result" was literally the title response
  # ("Create Magic Enchantment", 2026-08-03) and the run died at turns=1.
  export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
  # llama.cpp's json-schema->grammar converter tips over on the COMBINED
  # WebFetch+WebSearch schemas ("failed to parse grammar", 2026-08-03,
  # gpt-oss on the 395+; either one alone is fine). Local/free lanes don't
  # need web tools — drop both.
  # Minimal toolset (2026-08-04): a finished qwen run invoked Skill twice
  # "for fun" — each injects a full skill doc; context blew 267k/131k and
  # the run died AT THE FINISH LINE. Workers get exactly what the job
  # needs: Bash, Read, Edit, Write, Agent.
  EXTRA_CLAUDE_FLAGS="${EXTRA_CLAUDE_FLAGS:---disallowedTools WebFetch,WebSearch,Skill,ReportFindings,TaskCreate,TaskUpdate,TaskList,TaskGet,TaskOutput,TaskStop,CronCreate,CronDelete,CronList,DesignSync,PushNotification,ScheduleWakeup,SendMessage,Monitor,EnterWorktree,ExitWorktree,Workflow,NotebookEdit}"
else
  unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
fi

log() { printf '[%s] %s: %s\n' "$(date '+%H:%M:%S')" "$WORKER_ID" "$*" >&2; }

usage_gate() {
  [ "$USAGE_LIMIT_PCT" -le 0 ] 2>/dev/null && return 0
  local lim5="$USAGE_LIMIT_PCT" lim7="$USAGE_LIMIT_PCT" nh now age tok body u5 u7 r5 r7
  nh=$(TZ='Europe/Zurich' date +%H); nh=$((10#$nh))
  if [ "$nh" -ge 23 ] || [ "$nh" -lt 6 ]; then lim5=100; fi
  now=$(date +%s); age=99999
  [ -s "$USAGE_CACHE" ] && age=$(( now - $(stat -c %Y "$USAGE_CACHE" 2>/dev/null || echo 0) ))
  if [ "$age" -ge "$USAGE_GATE_TTL" ]; then
    tok=$(jq -r '.claudeAiOauth.accessToken // empty' "$HOME/.claude/.credentials.json" 2>/dev/null || true)
    [ -z "$tok" ] && return 0
    if body=$(curl -fsS --max-time 15 -H "Authorization: Bearer $tok" \
         -H "anthropic-beta: oauth-2025-04-20" \
         https://api.anthropic.com/api/oauth/usage 2>/dev/null) \
       && printf '%s' "$body" | jq -e '.five_hour' >/dev/null 2>&1; then
      printf '%s' "$body" > "$USAGE_CACHE"
    elif [ "$age" -ge 1800 ]; then
      return 0
    else
      touch "$USAGE_CACHE" 2>/dev/null || true
    fi
  fi
  u5=$(jq -r '.five_hour.utilization // 0 | floor' "$USAGE_CACHE" 2>/dev/null || echo 0)
  u7=$(jq -r '.seven_day.utilization // 0 | floor' "$USAGE_CACHE" 2>/dev/null || echo 0)
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

report() { # $1 status  $2 reason  $3 missing_primitive  $4 why  $5 note
  local tok=0; [ -f "/tmp/disp-$WORKER_ID-tokens" ] && tok=$(awk '{s+=$1} END{print s+0}' "/tmp/disp-$WORKER_ID-tokens")
  jq -n --arg t "$TICKET_ID" --arg w "$WORKER_ID" --arg s "$1" --arg r "$2" \
        --arg p "$3" --arg y "$4" --arg n "$5" --argjson tok "$tok" \
    '{ticket_id:$t, worker_id:$w, status:$s, reason:$r,
      missing_primitive:$p, primitive_why:$y, note:$n, tokens:$tok, skipped:[]}' \
  | curl -s -X POST "$DISPATCHER/report" -H 'Content-Type: application/json' -d @- >/dev/null 2>&1 || true
}

TOK_FILE="/tmp/disp-$WORKER_ID-tokens"
claude_run() { # claude-Flags; Prompt via stdin
  local raw txt used
  raw=$(cd "$CLONE_PATH" && timeout "${CJ_TIMEOUT:-$CLAUDE_TIMEOUT}" "$CLAUDE_BIN" -p \
        --output-format json "$@" 2>>"/tmp/disp-$WORKER_ID-claude.err") \
    || { echo "CLAUDE_TIMEOUT_OR_ERROR"; return 0; }
  used=$(printf '%s' "$raw" | jq -r 'if (type=="object" and .modelUsage) then ([.modelUsage[] | (.inputTokens//0)+(.outputTokens//0)+(.cacheReadInputTokens//0)+(.cacheCreationInputTokens//0)] | add // 0) elif type=="object" then ((.usage.input_tokens//0)+(.usage.cache_creation_input_tokens//0)+(.usage.cache_read_input_tokens//0)+(.usage.output_tokens//0)) else 0 end' 2>/dev/null)
  [ -n "$used" ] && [ "$used" != 0 ] && echo "$used" >> "$TOK_FILE"
  printf '%s turns=%s tok=%s\n' "$(date +%H:%M:%S)" \
    "$(printf '%s' "$raw" | jq -r '.num_turns // "?"' 2>/dev/null)" "${used:-0}" \
    >> "/tmp/disp-$WORKER_ID-turns.log" 2>/dev/null || true
  txt=$(printf '%s' "$raw" | jq -r '.result // empty' 2>/dev/null)
  if [ -n "$txt" ]; then printf '%s' "$txt"; else printf '%s' "$raw"; fi
}

# Eligibility-Zähler: "flip-ELIGIBLE (...): N (x%)" -> N. Leer bei Fehler.
eligible_count() {
  (cd "$CLONE_PATH" && timeout 120 python3 scripts/paragraph/reparse.py --review-pile 2>/dev/null) \
    | sed -n 's/^flip-ELIGIBLE[^:]*: \([0-9]\+\).*/\1/p' | head -1
}
# Untruncierter Gesamt-Miss-Zähler (SWEEP-Gate, Option B 2026-08-02).
total_misses() {
  (cd "$CLONE_PATH" && timeout 120 python3 scripts/paragraph/reparse.py --review-pile 2>/dev/null) \
    | sed -n 's/^total-misses: \([0-9]\+\).*/\1/p' | head -1
}
# Instanzen der Task-Shape in der Demand-Table ("  1234  <shape>  ..."). 0 wenn
# die Shape ganz verschwunden ist (auch ein Erfolg). Leer bei Pipeline-Fehler.
shape_count() { # $1 = shape
  local out n
  out=$( (cd "$CLONE_PATH" && timeout 120 python3 scripts/paragraph/reparse.py --review-pile 2>/dev/null) ) || { echo ""; return; }
  printf '%s' "$out" | grep -q '^flip-ELIGIBLE' || { echo ""; return; }
  n=$(printf '%s\n' "$out" | awk -v s="$1" '$2 == s {print $1; exit}')
  echo "${n:-0}"
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

# ---- Setup: eigener Clone via SSH (NIE der Live-Checkout, NIE stashen) ----
if [ ! -d "$CLONE_PATH/.git" ]; then
  if [ ! -d "$MIRROR" ]; then
    log "mirror anlegen: $MIRROR"
    GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone --mirror "$REPO_SSH" "$MIRROR" 2>/dev/null || true
  fi
  log "clone $REPO_SSH -> $CLONE_PATH"
  if [ -d "$MIRROR" ]; then
    GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git -C "$MIRROR" fetch -q 2>/dev/null || true
    GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone --reference "$MIRROR" "$REPO_SSH" "$CLONE_PATH" \
      || GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone "$REPO_SSH" "$CLONE_PATH" \
      || { log "FATAL: clone failed"; exit 1; }
  else
    GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone "$REPO_SSH" "$CLONE_PATH" || { log "FATAL: clone failed"; exit 1; }
  fi
fi
cd "$CLONE_PATH"
git config user.email "dispatcher-worker@magic"
git config user.name  "dispatcher-$WORKER_ID"

# ---- Hauptschleife ----
while true; do
  if [ -f "$PAUSE_FILE" ] && [ "$(date +%s)" -lt "$(cat "$PAUSE_FILE" 2>/dev/null || echo 0)" ]; then
    log "Pause aktiv bis $(date -d @"$(cat "$PAUSE_FILE")" '+%F %T' 2>/dev/null) — kein neues Ticket"; sleep 300; continue
  fi
  if [ "${OLLAMA_WORKER:-0}" != "1" ] && declare -f pace_ok >/dev/null && ! pace_ok; then log "weekly-pace erreicht — pausiere"; sleep 300; continue; fi
  if ! usage_gate; then sleep 120; continue; fi

  CLAIM=$(curl -s -m 30 "$DISPATCHER/claim?worker=$WORKER_ID&tier=$TIER" 2>/dev/null || echo '{}')
  TICKET_ID=$(printf '%s' "$CLAIM" | jq -r '.id // empty' 2>/dev/null || true)
  if [ -z "$TICKET_ID" ]; then
    log "queue leer — warte 60s"
    sleep 60
    continue
  fi
  TICKET_TITLE=$(printf '%s' "$CLAIM" | jq -r '.title // ""')
  TICKET_DESC=$(printf '%s' "$CLAIM" | jq -r '.desc // ""')
  RETRIES=$(printf '%s' "$CLAIM" | jq -r '.retry_count // 0')
  log "ticket #$TICKET_ID (retry $RETRIES): $TICKET_TITLE"

  ( while sleep 60; do curl -s "$DISPATCHER/heartbeat?ticket=$TICKET_ID" >/dev/null 2>&1; done ) >/dev/null 2>&1 &
  HB_PID=$!

  # Clone hart auf origin/main + Task-Branch (eigener Clone — reset ok, stash NIE)
  if ! git fetch -q origin main || ! git checkout -qB "reparse/task-$TICKET_ID" origin/main; then
    log "git sync failed — Ticket zurückgeben"
    report retry infra "" "" "git fetch/checkout failed on worker $WORKER_ID"
    stop_heartbeat; sleep 30; continue
  fi
  git clean -qfd

  # Task-Shape aus dem Titel: "REPARSE-MAP: <shape> (..."; SWEEP-Tickets
  # (Option B) haben keine Einzel-Shape — Gate läuft über total-misses,
  # Budget deutlich größer (ein Run = ganze Demand-Table top-down).
  TASK_SHAPE=$(printf '%s' "$TICKET_TITLE" | sed -n 's/^REPARSE-MAP: \([^ ]*\) .*/\1/p')
  # ENGINE tickets carry their plan item in the title too — gate them on the
  # SAME shape-drain metric so machinery-only rounds don't count as done
  # (breadth must materialize the predicted yield in the same ticket).
  [ -z "$TASK_SHAPE" ] && TASK_SHAPE=$(printf '%s' "$TICKET_TITLE" | sed -n 's/^REPARSE-ENGINE: \([^ ]*\) .*/\1/p')
  SWEEP=0; RUN_TURNS="$WORKER_MAX_TURNS"; RUN_TIMEOUT="$CLAUDE_TIMEOUT"
  if printf '%s' "$TICKET_TITLE" | grep -q '^REPARSE-SWEEP'; then
    SWEEP=1; RUN_TURNS=250; RUN_TIMEOUT=5400
  fi
  BASE_ELIG=$(eligible_count)
  if [ -z "$BASE_ELIG" ]; then
    log "reparse.py --review-pile liefert keine Baseline — infra"
    report retry infra "" "" "review-pile baseline failed on $WORKER_ID"
    stop_heartbeat; sleep 60; continue
  fi
  BASE_SHAPE=$(shape_count "$TASK_SHAPE")
  BASE_TOTAL=""
  [ "$SWEEP" = 1 ] && BASE_TOTAL=$(total_misses)
  # UNCLASSIFIED je Job messen (Dani 2026-08-02): steigt sie, hat der Job
  # Klassifikations-Leaks erzeugt; als Engine-Round-Trigger im Report.
  BASE_UNCLASS=$(shape_count "kind_unsupported:UNCLASSIFIED")
  log "baseline eligibility: $BASE_ELIG, shape '$TASK_SHAPE': ${BASE_SHAPE:-?} instances${BASE_TOTAL:+, total-misses: $BASE_TOTAL}"

  # ---- Prompt: statischer Block = Contract + Harness-Protokoll (cachebar) ----
  STATIC_FILE="/tmp/disp-$WORKER_ID-static.md"
  PROMPT_FILE="/tmp/disp-$WORKER_ID-prompt.txt"
  ACTION_NUDGE=""
  if [ "${OLLAMA_WORKER:-0}" = "1" ]; then
    # gpt-oss (395+ lane, 2026-08-03): with a big briefing + a complex ticket
    # the model answers with a PLAN as plain text and never calls a tool
    # (turns=1 no-ops). An explicit action-forcing opener fixes it (proven:
    # "First action: use the Bash tool..." -> clean multi-turn run).
    ACTION_NUDGE="IMPORTANT: You are an AGENT with tools, not a chat assistant. Your FIRST response MUST be a tool call (e.g. Bash or Read) — NEVER a prose answer or a plan. Work step by step with tools until the task is done.
"
  fi
  {
    # MISSION BRIEFING FIRST (Dani 2026-08-03: cold starts were the root
    # inefficiency — every run re-derived what the project knows). The
    # auto-generated state doc replaces exploration turns; byte-stable
    # between landings -> prompt-cache friendly.
    [ -f "$CLONE_PATH/scripts/skills/mission-state.md" ] && cat "$CLONE_PATH/scripts/skills/mission-state.md"
    cat "$CLONE_PATH/scripts/skills/reparse-worker-contract.md"
    if [ "$TIER" = "handler" ]; then
      # Handler-Tier: Karten aus Doku statt Code bauen. DIGEST, nicht der
      # volle Katalog — 489KB sprengen ein 128k-Kontextfenster (rl1 bekam
      # stillschweigend truncierte Requests, 1-Turn-No-Ops, 2026-08-03).
      # one-shot worked example FIRST (Dani 2026-08-04) — local models
      # follow a complete concrete example far better than rules alone.
      [ -f "$CLONE_PATH/scripts/skills/handler-worked-example.md" ] && cat "$CLONE_PATH/scripts/skills/handler-worked-example.md"
      if [ -f "$CLONE_PATH/scripts/skills/primitive-catalog-digest.md" ]; then
        cat "$CLONE_PATH/scripts/skills/primitive-catalog-digest.md"
      elif [ -f "$CLONE_PATH/scripts/skills/primitive-catalog.md" ]; then
        cat "$CLONE_PATH/scripts/skills/primitive-catalog.md"
      fi
    fi
    cat <<'HARNESS'

## Harness protocol (this run)

- You are already on your task branch in your own clone; the repo root is your
  working directory. Work HERE (this checkout), not in any other path.
- Commit your work yourself (the contract's commit-message rules apply).
  Do NOT push — the harness pushes your branch. NEVER touch main, NEVER stash.
- Run all commands in the FOREGROUND and wait for them; no backgrounding.
- The harness gate afterwards runs: go build ./... (in backend/),
  go test ./cards/ -run 'TestVocabulary|TestV2|TestShape_' -count=1,
  and reparse.py --review-pile: DONE requires eligibility to rise OR your task's
  miss-shape to lose instances in the demand table (both count as progress).
  Do not run the full suite yourself.
- Your FINAL output must contain exactly one verdict block:
    VERDICT: DONE|NEEDS_PRIMITIVE|SEMANTIC_GAP|AMBIGUOUS|NOT_A_SHAPE
    DELTA: <eligibility delta as integer, 0 if none>
    REASON: <one line: DONE = mapping rule summary; NEEDS_PRIMITIVE = kebab-case
            primitive name + one-paragraph proposal; SEMANTIC_GAP = the
            mismatch; AMBIGUOUS = both readings; NOT_A_SHAPE = why junk>
- A park verdict (anything but DONE) means: leave the tree CLEAN (git checkout
  -- . && git clean -fd) so no half-mapping ships.
HARNESS
    if [ "$TIER" = "handler" ]; then
      cat <<'HGATE'

## HANDLER-TIER OVERRIDE of the gate description above
Your gate is DIFFERENT: build green + at least one NEW Go test function
(+func Test...) in your diff + the FULL sharded cards suite green
(bash scripts/test-cards-sharded.sh 6 — the harness runs it). Eligibility /
miss-shape deltas do NOT apply to handler tickets; ignore that part.
Write the handler in backend/cards/cardfns/, register it per the existing
per-card conventions, and put the behavior test in a NEW test file.

## Knowledge service (USE THIS FIRST — do not spelunk the engine)
A local search service indexes every primitive, helper, and existing card
handler. Query it with Bash BEFORE reading any engine file:
  curl -s 'http://127.0.0.1:4103/similar' --get --data-urlencode 'text=<the card text>'
  curl -s 'http://127.0.0.1:4103/find' --get --data-urlencode 'q=<capability you need>' --data-urlencode 'kind=primitive'
  (kind can be primitive, helper, or handler; omit it to search everything)
Start with /similar: the nearest existing handlers are your best template —
copy their structure. Open engine files only to PROVE a symbol exists, never
to discover; if /find returns NO MATCH for a needed capability, the engine
almost certainly lacks it.

## Discipline rules (hard requirements)
- PARK EARLY: within your first 5 tool calls, decide buildable vs park. If
  the card changes combat/attack/blocking/targeting/casting RULES and neither
  /find nor /similar shows a matching primitive or handler pattern, output
  VERDICT: NEEDS_PRIMITIVE immediately. A fast, well-named park is a SUCCESS.
- NEVER repeat a tool call that just failed or returned the same result.
  Same command + same answer twice = STOP, change approach or park.
- go test: ALWAYS pass "timeout": 300000 or more in the Bash tool call. If
  the harness says a command was "moved to background", READ the output file
  it names to get the result — do NOT run the command again.
HGATE
    fi
  } > "$STATIC_FILE"
  {
    printf '%s\n' "$ACTION_NUDGE"
    echo "=== THE TICKET ==="
    echo "TICKET #$TICKET_ID: $TICKET_TITLE"
    echo ""
    printf '%s\n' "$TICKET_DESC"
  } > "$PROMPT_FILE"
  # Pre-pack (2026-08-04): inject nearest handlers + primitive hits for THIS
  # card from the knowledge service (:4103) — saves the model its own search
  # turns. Fail-open: skipped silently when the service is down.
  if [ "$TIER" = "handler" ] && curl -s -m 3 -o /dev/null http://127.0.0.1:4103/health 2>/dev/null; then
    {
      echo ""
      echo "=== PRE-SELECTED KNOWLEDGE (auto-generated for this card; verify, then reuse) ==="
      echo "--- Nearest existing handlers (use as templates): ---"
      curl -s -m 15 'http://127.0.0.1:4103/similar' --get --data-urlencode "text=$TICKET_DESC" --data-urlencode 'n=2' 2>/dev/null
      echo "--- Possibly relevant primitives/helpers/handlers: ---"
      curl -s -m 15 'http://127.0.0.1:4103/find' --get --data-urlencode "q=$TICKET_DESC" --data-urlencode 'n=5' 2>/dev/null
    } >> "$PROMPT_FILE"
  fi

  OUTCOME=""; VERDICT=""; V_REASON=""; GATE_TAIL=""
  : > "$TOK_FILE"
  attempt=1
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    RUN_MODEL="$MODEL"; [ "$attempt" -ge 2 ] && RUN_MODEL="$MODEL_ESCALATE"
    log "attempt $attempt/$MAX_ATTEMPTS (model $RUN_MODEL)"
    CLAUDE_OUT=$(CJ_TIMEOUT="$RUN_TIMEOUT" claude_run --model "$RUN_MODEL" --permission-mode bypassPermissions ${EXTRA_CLAUDE_FLAGS:-} \
      --max-turns "$RUN_TURNS" \
      --append-system-prompt-file "$STATIC_FILE" < "$PROMPT_FILE")

    printf '%s' "$CLAUDE_OUT" | tail -c 4000 > "/tmp/disp-$WORKER_ID-last-result.txt" 2>/dev/null || true
    if printf '%s' "$CLAUDE_OUT" | grep -qi "model.*not exist\|CLAUDE_TIMEOUT_OR_ERROR"; then
      # --continue (2026-08-04, Dani): resume the SAME session after a
      # mid-work flake — files survived anyway, now the model's reasoning
      # state survives too instead of re-discovering its own work.
      log "flake — retry mit --continue (Session-Resume)"
      CLAUDE_OUT=$(printf '%s' "Your previous session was interrupted mid-work. Continue EXACTLY where you left off — your files are still in the working tree. Finish the task per the original instructions." | CJ_TIMEOUT="$RUN_TIMEOUT" claude_run --model "$RUN_MODEL" --permission-mode bypassPermissions ${EXTRA_CLAUDE_FLAGS:-} \
        --max-turns "$RUN_TURNS" --continue --append-system-prompt-file "$STATIC_FILE")
    fi

    # Infra-/Quota-Ausfall ohne geschriebene Dateien -> Ticket zurück, Probe-Loop
    if [ -z "$(git status --porcelain)" ] \
       && [ "$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)" -eq 0 ] \
       && printf '%s' "$CLAUDE_OUT" | grep -qiE "CLAUDE_TIMEOUT_OR_ERROR|quota|rate.?limit|too many requests|429|overloaded|insufficient|exhausted|billing"; then
      log "⚠️ API/Quota-Problem — Ticket #$TICKET_ID zurückgeben (infra), pausiere"
      report retry infra "" "" "api/quota outage on $WORKER_ID: $(printf '%s' "$CLAUDE_OUT" | tail -c 150 | tr '\n' ' ')"
      stop_heartbeat
      until PROBE=$(timeout 180 "$CLAUDE_BIN" -p --model "$MODEL" --permission-mode bypassPermissions --max-turns 1 <<< "Reply with exactly: OK" 2>&1) && printf '%s' "$PROBE" | grep -q "OK"; do
        log "Probe negativ — nächster Versuch in 15 min"
        sleep 900
      done
      log "✅ API wieder erreichbar — weiter"
      continue 2
    fi

    VERDICT=$(printf '%s' "$CLAUDE_OUT" | grep -E '^VERDICT: *[A-Z_]+' | tail -1 | sed 's/^VERDICT: *//; s/ .*//')
    V_REASON=$(printf '%s' "$CLAUDE_OUT" | grep '^REASON:' | tail -1 | sed 's/^REASON: *//')

    # Park-Verdicts sind terminale Ausgänge — kein Gate nötig
    case "$VERDICT" in
      NEEDS_PRIMITIVE|SEMANTIC_GAP|AMBIGUOUS|NOT_A_SHAPE)
        OUTCOME="parked"; break;;
    esac

    # Auto-commit (2026-08-04, Unbounded-Potential lesson): qwen did 41
    # turns of real handler work but never committed — the gate greps the
    # COMMITTED diff and failed on an empty one. Local models can't be
    # trusted to remember the commit step; the harness does it.
    if [ -n "$(git status --porcelain)" ]; then
      git add -A >/dev/null 2>&1
      git commit -qm "wip(auto-commit): task-$TICKET_ID $TICKET_TITLE" >/dev/null 2>&1 || true
    fi
    # ---- Gate: build + Vocab/Shape-Tests + Eligibility-Delta ----
    if BUILD_OUT=$(cd "$CLONE_PATH/backend" && "$GO" build ./... 2>&1); then
      if TEST_OUT=$(cd "$CLONE_PATH/backend" && timeout 600 "$GO" test ./cards/ -run 'TestVocabulary|TestV2|TestShape_' -count=1 2>&1); then
        NEW_ELIG=$(eligible_count)
        NEW_SHAPE=$(shape_count "$TASK_SHAPE")
        # Erfolg = Eligibility steigt ODER die Task-Shape verliert Instanzen.
        # Seit die Single-Blocker-Karten gedraint sind, ist ein korrektes
        # Mapping mit Elig-Delta 0 der NORMALFALL (jede Karte hat noch andere
        # Misses) — die Shape-Instanzen sind die ehrliche Task-Metrik.
        ELIG_OK=0; SHAPE_OK=0
        [ -n "$NEW_ELIG" ] && [ "$NEW_ELIG" -gt "$BASE_ELIG" ] && ELIG_OK=1
        if [ "$SWEEP" = 1 ]; then
          NEW_TOTAL=$(total_misses)
          [ -n "$NEW_TOTAL" ] && [ -n "$BASE_TOTAL" ] && [ "$NEW_TOTAL" -lt "$BASE_TOTAL" ] && SHAPE_OK=1
          NEW_SHAPE="$NEW_TOTAL"; BASE_SHAPE="$BASE_TOTAL"
        else
          [ -n "$NEW_SHAPE" ] && [ -n "$BASE_SHAPE" ] && [ "$NEW_SHAPE" -lt "$BASE_SHAPE" ] && SHAPE_OK=1
        fi
        ENGINE_OK=0
        if [ "$TIER" = "handler" ]; then
          # Handler-Tier: Ziel sind cardfns-Handler + Behavior-Tests, nicht
          # Parser-Deltas. Erfolg = neue Test-Funktion(en) + VOLLE Suite grün.
          if git diff origin/main...HEAD 2>/dev/null | grep -q '^+func Test' \
             && (cd "$CLONE_PATH" && bash scripts/test-cards-sharded.sh 6 >/dev/null 2>&1); then
            ENGINE_OK=1
          fi
        fi
        if [ "$TIER" = "engine" ] && git diff origin/main...HEAD 2>/dev/null | grep -q '^+func TestShape_'; then
          # Engine-Runden liefern oft +0 Eligibility (Infrastruktur) — neue
          # Shape-Tests + grüne Gates zählen als Erfolg (Modal-Runden-Muster).
          ENGINE_OK=1
        fi
        if [ "$ELIG_OK" = 1 ] || [ "$SHAPE_OK" = 1 ] || [ "$ENGINE_OK" = 1 ]; then
          DELTA=$(( ${NEW_ELIG:-$BASE_ELIG} - BASE_ELIG ))
          SDELTA=$(( ${BASE_SHAPE:-0} - ${NEW_SHAPE:-${BASE_SHAPE:-0}} ))
          NEW_UNCLASS=$(shape_count "kind_unsupported:UNCLASSIFIED")
          UDELTA=$(( ${NEW_UNCLASS:-0} - ${BASE_UNCLASS:-0} ))
          log "✅ gate grün: eligibility $BASE_ELIG -> ${NEW_ELIG:-?} (+$DELTA), shape $TASK_SHAPE ${BASE_SHAPE:-?} -> ${NEW_SHAPE:-?} (-$SDELTA), unclassified Δ$UDELTA"
          OUTCOME="gate_green"
          break
        else
          GATE_TAIL="Gate: build+tests green, but neither review-pile eligibility rose (before=$BASE_ELIG after=${NEW_ELIG:-parse-failed}) nor did the task shape '$TASK_SHAPE' lose instances (before=${BASE_SHAPE:-?} after=${NEW_SHAPE:-?}). Your mapping did not fire on the review pile — reproduce with --review-pile and --card on the ticket's examples."
          log "❌ weder eligibility- noch shape-delta (attempt $attempt)"
        fi
      else
        GATE_TAIL=$(printf '%s' "$TEST_OUT" | tail -c 2000)
        log "❌ tests rot (attempt $attempt)"
      fi
    else
      GATE_TAIL=$(printf '%s' "$BUILD_OUT" | tail -c 2000)
      log "❌ build rot (attempt $attempt)"
    fi

    {
      echo ""
      echo "=== YOUR PREVIOUS ATTEMPT FAILED THE GATE — fix your existing work, do not start over ==="
      echo "$GATE_TAIL"
    } >> "$PROMPT_FILE"
    attempt=$((attempt + 1))
  done

  # ---- Ergebnis behandeln ----
  if [ "$OUTCOME" = "parked" ]; then
    log "parked: $VERDICT — $V_REASON"
    git checkout -q -- . 2>/dev/null; git clean -qfd
    if [ "$VERDICT" = "NEEDS_PRIMITIVE" ]; then
      PRIM=$(printf '%s' "$V_REASON" | grep -oE '^[a-z0-9_-]+' | head -1)
      report parked missing_primitive "${PRIM:-unnamed-primitive}" "$V_REASON" "reparse verdict NEEDS_PRIMITIVE"
    else
      report parked max_retry_reached "" "" "reparse verdict $VERDICT: $V_REASON"
    fi
  elif [ "$OUTCOME" = "gate_green" ]; then
    git add -A
    git commit -qm "reparse(task-$TICKET_ID): $TICKET_TITLE (+$DELTA eligible, -${SDELTA:-0} $TASK_SHAPE, $WORKER_ID)" || true
    BRANCH_PREFIX="reparse/task"; [ "$TIER" = "engine" ] && BRANCH_PREFIX="reparse/engine-task"
    [ "$TIER" = "handler" ] && BRANCH_PREFIX="reparse/handler-task"
    if git push -qf origin "HEAD:refs/heads/$BRANCH_PREFIX-$TICKET_ID" 2>/dev/null; then
      log "✅ branch $BRANCH_PREFIX-$TICKET_ID gepusht (+$DELTA elig, -${SDELTA:-0} shape) — Integrator merged"
      report fixed "" "" "" "elig +$DELTA ($BASE_ELIG->${NEW_ELIG:-?}), shape $TASK_SHAPE -${SDELTA:-0} (${BASE_SHAPE:-?}->${NEW_SHAPE:-?}), unclassified Δ${UDELTA:-?}; branch $BRANCH_PREFIX-$TICKET_ID; VERDICT: ${VERDICT:-DONE}; $V_REASON"
    else
      log "❌ branch push failed — Ticket zurückgeben"
      report retry "" "" "" "branch push failed on $WORKER_ID"
    fi
  else
    log "❌ $MAX_ATTEMPTS Versuche gescheitert — retry/wait"
    git checkout -q -- . 2>/dev/null; git clean -qfd
    report retry "" "" "" "gate tail: $(printf '%s' "$GATE_TAIL" | head -c 500)"
  fi

  stop_heartbeat
  log "cycle done"
  [ "$ONE_SHOT" = 1 ] && { log "ONE_SHOT — exit"; exit 0; }
done
