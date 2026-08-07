#!/usr/bin/env bash
# engine-pipeline — staged (non-agentic) build of ONE small primitive demand.
#
# Same shape as map-pipeline.sh but engine-tier: backend/game/ edits allowed,
# gate = build + vocab/shape tests + NEW test func in diff + FULL sharded
# suite. FRAMEWORK-sized demands park for a manual engine round.
#
# Usage: engine-pipeline.sh TICKET_ID [--push]
#   PIPE_MODEL / PIPE_BASE_URL as in map-pipeline.sh
# Exit: 0 gate-green (pushed with --push), 4 park (FRAMEWORK/AMBIGUOUS),
#       2 exhausted (escalate to manual round), other = infra error.
set -uo pipefail
TICKET="${1:?ticket id}"; shift || true
PUSH=0; [ "${1:-}" = "--push" ] && PUSH=1
OPS=/opt/development/magic-ops
REPO=/opt/development/test/openmagic
CLONE="${CLONE:-/tmp/work/engine-pipe-clone}"
MODEL="${PIPE_MODEL:-claude-sonnet-5}"
GO=/usr/local/go/bin/go
export GOCACHE=/opt/development/.gocache-magic
LOG="/tmp/orch/engine-pipeline-$TICKET.log"
log() { printf '[%s] epipe-%s: %s\n' "$(date +%H:%M:%S)" "$TICKET" "$*" | tee -a "$LOG"; }

rm -rf "$CLONE"
git clone -q "file://$REPO" "$CLONE" || exit 1
cd "$CLONE" || exit 1
git remote set-url origin "$(cd "$REPO" && git remote get-url origin)"
git fetch -q origin main && git checkout -qb "epipe-$TICKET" origin/main

PACK="/tmp/orch/engine-pipeline-$TICKET-pack.md"
if ! python3 "$OPS/scripts/engine-pipeline-pack.py" "$TICKET" --repo "$CLONE" > "$PACK" 2>>"$LOG"; then
  log "pack failed (ticket has no missing_prim?)"; exit 1
fi
log "pack built: $(wc -c < "$PACK") bytes"

model_call() {
  [ -n "${PIPE_BASE_URL:-}" ] && export ANTHROPIC_BASE_URL="$PIPE_BASE_URL" ANTHROPIC_AUTH_TOKEN="${PIPE_AUTH_TOKEN:-ollama}"
  local raw
  raw=$(timeout -k 30 1200 claude -p --output-format json --model "$MODEL" \
      --max-turns 3 --permission-mode bypassPermissions \
      --disallowedTools 'Bash,Read,Edit,Write,Glob,Grep,WebFetch,WebSearch,Agent,Skill' \
      2>>"$LOG")
  printf '%s' "$raw" | jq -r '"tokens: in=\(.usage.input_tokens // 0) out=\(.usage.output_tokens // 0) cache_r=\(.usage.cache_read_input_tokens // 0) cache_w=\(.usage.cache_creation_input_tokens // 0)"' >> "$LOG" 2>/dev/null
  printf '%s' "$raw" | jq -r '.result // empty'
}

attempt=1
PROMPT_FILE="$PACK"
while [ $attempt -le 2 ]; do
  log "model call $attempt (model $MODEL)"
  OUT=$(model_call < "$PROMPT_FILE")
  if [ -z "$OUT" ]; then
    log "empty model reply — one retry"
    OUT=$(model_call < "$PROMPT_FILE")
    [ -z "$OUT" ] && { log "empty twice — abort"; exit 1; }
  fi
  printf '%s\n' "$OUT" > "/tmp/orch/engine-pipeline-$TICKET-reply-$attempt.md"

  # NEED round: the model may request missing code regions once per run.
  if printf '%s' "$OUT" | command grep -q '^NEED:' && [ "${NEED_USED:-0}" = 0 ]; then
    NEED_USED=1
    log "model requested regions: $(printf '%s' "$OUT" | command grep '^NEED:' | tr '\n' ' ')"
    ADD=$(printf '%s' "$OUT" | python3 "$OPS/scripts/pipeline-fetch-regions.py")
    PROMPT_FILE="/tmp/orch/engine-pipeline-$TICKET-need.md"
    { cat "$PACK"; echo; echo "## REQUESTED CODE REGIONS"; printf '%s\n' "$ADD"; } > "$PROMPT_FILE"
    continue
  fi

  APPLY_OUT=$(printf '%s' "$OUT" | python3 "$OPS/scripts/map-pipeline-apply.py" --allow-game); rc=$?
  if [ $rc -eq 4 ]; then log "park: $APPLY_OUT"; echo "$APPLY_OUT"; exit 4; fi
  if [ $rc -ne 0 ]; then
    log "apply failed (rc=$rc): $APPLY_OUT"
    GATE_TAIL="Your edit blocks failed to apply: $APPLY_OUT"
  else
    log "applied; gating (build + tests + new-test check + sharded suite)"
    if ! git diff --diff-filter=AM origin/main -- '*_test.go' | command grep -q '^+func Test'; then
      GATE_TAIL="Gate: no NEW test function (+func Test...) in your diff — a behavior test in a new _test.go file is REQUIRED."
      log "gate: missing new test func"
    elif BUILD_OUT=$(cd backend && "$GO" build ./... 2>&1) \
       && TEST_OUT=$(cd backend && timeout 600 "$GO" test ./cards/ ./game/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes|TestCombat' -count=1 2>&1) \
       && SUITE_OUT=$(bash scripts/test-cards-sharded.sh 6 2>&1); then
      log "GATE GREEN (build + tests + full suite)"
      git add -A
      git commit -qm "reparse(engine-task-$TICKET): engine-pipeline primitive build (staged non-agentic run)"
      if [ $PUSH -eq 1 ]; then
        git push -qf origin "HEAD:refs/heads/reparse/engine-task-$TICKET" && log "pushed reparse/engine-task-$TICKET"
      fi
      exit 0
    else
      GATE_TAIL="Gate failed:
$(printf '%s\n%s\n%s' "${BUILD_OUT:-}" "${TEST_OUT:-}" "${SUITE_OUT:-}" | command grep -vE '^ok ' | tail -c 2500)"
      log "gate: red"
    fi
    git checkout -q -- . && git clean -qfd
  fi
  PROMPT_FILE="/tmp/orch/engine-pipeline-$TICKET-retry.md"
  { cat "$PACK"; echo; echo "## PREVIOUS ATTEMPT FAILED — fix and resend ALL blocks (full corrected set)"; echo "$GATE_TAIL"; } > "$PROMPT_FILE"
  attempt=$((attempt + 1))
done
log "exhausted 2 calls — escalate to manual engine round"
exit 2
