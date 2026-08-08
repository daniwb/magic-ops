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
      --max-turns 5 --permission-mode bypassPermissions \
      --disallowedTools 'Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill,NotebookEdit' \
      --append-system-prompt 'You have NO working tools — every tool call will be denied. Do not attempt any. Reply with plain text only.' \
      2>>"$LOG")
  printf '%s' "$raw" | jq -r '"tokens: in=\(.usage.input_tokens // 0) out=\(.usage.output_tokens // 0) cache_r=\(.usage.cache_read_input_tokens // 0) cache_w=\(.usage.cache_creation_input_tokens // 0)"' >> "$LOG" 2>/dev/null
  # keep last raw CLI JSON — empty replies were error_max_turns tool-spin, undiagnosable without it
  printf '%s' "$raw" > "/tmp/orch/engine-pipeline-$TICKET-raw-last.json"
  printf '%s' "$raw" | jq -r '.result // empty'
}


run_bugfix_gate() { # green -> commit+push+0
  git add -A
  if git diff --cached --diff-filter=AM origin/main -- '*_test.go' | command grep -q '^+func Test' \
     && BUILD_OUT=$(cd backend && "$GO" build ./... 2>&1) \
     && TEST_OUT=$(cd backend && timeout 600 "$GO" test ./cards/ ./game/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes|TestCombat' -count=1 2>&1) \
     && SUITE_OUT=$(bash scripts/test-cards-sharded.sh 6 2>&1); then
    log "GATE GREEN after bugfix"
    git commit -qm "reparse(engine-task-$TICKET): engine-pipeline primitive build (bugfix round)"
    [ $PUSH -eq 1 ] && git push -qf origin "HEAD:refs/heads/reparse/engine-task-$TICKET" && log "pushed reparse/engine-task-$TICKET"
    return 0
  fi
  GATE_TAIL="Gate failed:
$(printf '%s\n%s\n%s' "${BUILD_OUT:-}" "${TEST_OUT:-}" "${SUITE_OUT:-}" | command grep -vE '^ok ' | tail -c 2500)"
  log "bugfix gate: still red"
  return 1
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

  # NEED rounds: up to two per run (mirrors map-pipeline — one round was
  # consistently insufficient; second requests died as rc=5).
  if printf '%s' "$OUT" | command grep -q '^NEED:' && [ "${NEED_USED:-0}" -lt 2 ]; then
    NEED_USED=$(( ${NEED_USED:-0} + 1 ))
    log "model requested regions (round $NEED_USED): $(printf '%s' "$OUT" | command grep '^NEED:' | tr '\n' ' ')"
    ADD=$(printf '%s' "$OUT" | python3 "$OPS/scripts/pipeline-fetch-regions.py")
    NEEDF="/tmp/orch/engine-pipeline-$TICKET-need.md"
    if [ "$NEED_USED" = 1 ]; then
      { cat "$PACK"; echo; echo "## REQUESTED CODE REGIONS"; printf '%s\n' "$ADD"; } > "$NEEDF"
    else
      { echo; echo "## REQUESTED CODE REGIONS (round 2 — FINAL)"; printf '%s\n' "$ADD"
        echo; echo "No further regions will be served. Produce edit blocks or a verdict NOW."; } >> "$NEEDF"
    fi
    PROMPT_FILE="$NEEDF"
    continue
  fi

  APPLY_OUT=$(printf '%s' "$OUT" | python3 "$OPS/scripts/map-pipeline-apply.py" --allow-game); rc=$?
  if [ $rc -eq 4 ]; then log "park: $APPLY_OUT"; echo "$APPLY_OUT"; exit 4; fi
  if [ $rc -ne 0 ]; then
    log "apply failed (rc=$rc): $APPLY_OUT"
    GATE_TAIL="Your edit blocks failed to apply: $APPLY_OUT"
  else
    log "applied; gating (build + tests + new-test check + sharded suite)"
    git add -A
    if ! git diff --cached --diff-filter=AM origin/main -- '*_test.go' | command grep -q '^+func Test'; then
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
    # Bugfix rounds on the KEPT tree (step 6, ported from handler-pipeline):
    # inline the changed files + exact error, ask for corrections only.
    if [ "${GATE_TAIL#Your edit blocks}" = "$GATE_TAIL" ]; then
      bfx=1
      while [ $bfx -le "${BUGFIX_MAX:-2}" ]; do
        BFP="$PACK.bugfix-$bfx"
        {
          echo "# BUGFIX ROUND $bfx — your patch failed the gate"
          echo; echo "Current state of YOUR changed files (already applied):"
          git add -A
          for f in $(git diff --cached --name-only origin/main | head -8); do
            echo; echo "### $f"; sed -n '1,400p' "$f"
          done
          echo; echo "## GATE ERROR"; echo "$GATE_TAIL"
          M1='<<<'; M2='==='; M3='>>>'
          [ -n "${PIPE_BASE_URL:-}" ] && { M1='@@@'; M2='@@@'; M3='@@@'; }
          echo; echo "Fix the error. Output ONLY correction blocks, EXACTLY:"
          echo "${M1}FILE path"; echo "${M1}SEARCH"; echo "exact current lines"
          echo "${M2}REPLACE"; echo "corrected lines"; echo "${M3}END"
          echo "End with EXPECT: <one line>."
        } > "$BFP"
        log "bugfix call $bfx"
        BOUT=$(model_call < "$BFP")
        [ -z "$BOUT" ] && break
        BAPPLY=$(printf '%s' "$BOUT" | python3 "$OPS/scripts/map-pipeline-apply.py" --overwrite --allow-game); brc=$?
        if [ $brc -ne 0 ]; then GATE_TAIL="Correction blocks failed to apply: $BAPPLY"; bfx=$((bfx+1)); continue; fi
        if run_bugfix_gate; then exit 0; fi
        bfx=$((bfx+1))
      done
    fi
    git reset -q HEAD >/dev/null 2>&1; git checkout -q -- . && git clean -qfd
  fi
  PROMPT_FILE="/tmp/orch/engine-pipeline-$TICKET-retry.md"
  { cat "$PACK"; echo; echo "## PREVIOUS ATTEMPT FAILED — fix and resend ALL blocks (full corrected set)"; echo "$GATE_TAIL"; } > "$PROMPT_FILE"
  attempt=$((attempt + 1))
done
log "exhausted 2 calls — escalate to manual engine round"
exit 2
