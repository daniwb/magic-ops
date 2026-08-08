#!/usr/bin/env bash
# handler-pipeline — staged build of ONE per-card handler (map-pipeline
# pattern, handler tier). Gate identical to the handler worker: build +
# NEW test func in diff + FULL sharded suite. backend/game/ stays guarded.
#
# Usage: handler-pipeline.sh TICKET_ID [--push]
#   PIPE_MODEL / PIPE_BASE_URL as in map-pipeline.sh (local = gpt-oss:120b
#   via the shim, $0)
# Exit: 0 green (pushed with --push), 4 park, 2 exhausted (escalate), 1 infra.
set -uo pipefail
TICKET="${1:?ticket id}"; shift || true
PUSH=0; [ "${1:-}" = "--push" ] && PUSH=1
OPS=/opt/development/magic-ops
REPO=/opt/development/test/openmagic
CLONE="${CLONE:-/tmp/work/handler-pipe-clone}"
MODEL="${PIPE_MODEL:-claude-sonnet-5}"
GO=/usr/local/go/bin/go
export GOCACHE=/opt/development/.gocache-magic
LOG="/tmp/orch/handler-pipeline-$TICKET.log"
log() { printf '[%s] hpipe-%s: %s\n' "$(date +%H:%M:%S)" "$TICKET" "$*" | tee -a "$LOG"; }

rm -rf "$CLONE"
git clone -q "file://$REPO" "$CLONE" || exit 1
cd "$CLONE" || exit 1
git remote set-url origin "$(cd "$REPO" && git remote get-url origin)"
git fetch -q origin main && git checkout -qb "hpipe-$TICKET" origin/main

PACK="/tmp/orch/handler-pipeline-$TICKET-pack.md"
if ! python3 "$OPS/scripts/handler-pipeline-pack.py" "$TICKET" --repo "$CLONE" ${PIPE_BASE_URL:+--alt-markers} > "$PACK" 2>>"$LOG"; then
  log "pack failed"; exit 1
fi
log "pack built: $(wc -c < "$PACK") bytes"

model_call() {
  # Local lane: bypass the claude CLI entirely — it always advertises
  # internal tools, and gpt-oss then answers with finish_reason=tool_calls
  # + empty content (work stuck in reasoning_content). A bare /v1/messages
  # call with NO tools forces final-channel text.
  if [ -n "${PIPE_BASE_URL:-}" ]; then
    local prompt raw
    # max_tokens computed from prompt size: the upstream llama-server
    # context-shifts when prompt+max_tokens exceeds its ~8k window, corrupting
    # the harmony stream ("peg-native format" 500, 2026-08-08). Keep the sum
    # under the window; floor 1200 so verdicts/patches still fit.
    local body
    body=$(python3 -c "
import json, sys
p = sys.stdin.read()
mt = max(1200, min(4000, 8192 - len(p)//3 - 512))
print(json.dumps({'model': '$MODEL', 'max_tokens': mt, 'messages': [{'role': 'user', 'content': p}]}))")
    raw=$(curl -s -m 1500 "$PIPE_BASE_URL/v1/messages" \
      -H 'content-type: application/json' -H "x-api-key: ${PIPE_AUTH_TOKEN:-ollama}" \
      -H 'anthropic-version: 2023-06-01' \
      -d "$body")
    # The shim always answers as SSE — reassemble the text deltas.
    printf '%s' "$raw" | command grep '^data: ' | sed 's/^data: //' \
      | jq -rs '"tokens: in=\([.[] | select(.type=="message_start") | .message.usage.input_tokens] | add // 0) out=\([.[] | .usage.output_tokens? // empty] | max // 0) cache_r=0 cache_w=0"' >> "$LOG" 2>/dev/null
    printf '%s' "$raw" | command grep '^data: ' | sed 's/^data: //' \
      | jq -rs '[.[] | select(.type=="content_block_delta") | .delta.text // empty] | join("")'
    return
  fi
  local raw
  # Local models (PIPE_BASE_URL -> shim) get NO tools and 3 turns: the shim
  # has no cross-turn prompt cache (each turn re-sends everything, 644k+
  # input observed) and gpt-oss wanders. The pack carries a full template —
  # single-shot is the right shape locally. Sonnet keeps read-only agentic.
  local turns=25 tools='Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill,NotebookEdit'
  if [ -n "${PIPE_BASE_URL:-}" ]; then
    turns=3; tools='Bash,Read,Edit,Write,Glob,Grep,WebFetch,WebSearch,Agent,Skill,NotebookEdit'
  fi
  raw=$(timeout -k 30 1800 claude -p --output-format json --model "$MODEL" \
      --max-turns "$turns" --permission-mode bypassPermissions \
      --disallowedTools "$tools" \
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
  printf '%s\n' "$OUT" > "/tmp/orch/handler-pipeline-$TICKET-reply-$attempt.md"

  APPLY_OUT=$(printf '%s' "$OUT" | python3 "$OPS/scripts/map-pipeline-apply.py"); rc=$?
  if [ $rc -eq 4 ]; then log "park: $APPLY_OUT"; echo "$APPLY_OUT"; exit 4; fi
  if [ $rc -ne 0 ]; then
    log "apply failed (rc=$rc): $APPLY_OUT"
    GATE_TAIL="Your file blocks failed to apply: $APPLY_OUT"
  else
    log "applied; gating (build + new-test check + sharded suite)"
    git add -A
    if ! git diff --cached --diff-filter=AM origin/main -- '*_test.go' | command grep -q '^+func Test'; then
      GATE_TAIL="Gate: no NEW test function (+func Test...) in your diff — the behavior test file is REQUIRED."
      log "gate: missing new test func"
    elif BUILD_OUT=$(cd backend && "$GO" build ./... 2>&1) \
       && SUITE_OUT=$(bash scripts/test-cards-sharded.sh 6 2>&1); then
      log "GATE GREEN (build + suite)"
      git commit -qm "reparse(handler-task-$TICKET): handler-pipeline card build (staged run)"
      if [ $PUSH -eq 1 ]; then
        git push -qf origin "HEAD:refs/heads/reparse/handler-task-$TICKET" && log "pushed reparse/handler-task-$TICKET"
      fi
      exit 0
    else
      GATE_TAIL="Gate failed:
$(printf '%s\n%s' "${BUILD_OUT:-}" "${SUITE_OUT:-}" | command grep -vE '^ok ' | tail -c 2500)"
      log "gate: red — entering bugfix rounds (tree kept)"
      # Bugfix-Job (Dani 2026-08-07): iterate ON the red state instead of
      # regenerating from scratch — show current files + exact error, ask
      # for corrections only. Up to BUGFIX_MAX rounds (local = \$0).
      bfx=1
      while [ $bfx -le "${BUGFIX_MAX:-3}" ]; do
        BFP="/tmp/orch/handler-pipeline-$TICKET-bugfix-$bfx.md"
        {
          echo "# BUGFIX ROUND $bfx — your handler failed the gate"
          echo
          echo "Current state of YOUR files (already applied to the tree):"
          for f in $(git diff --cached --name-only origin/main); do
            echo; echo "### $f"; cat "$f"
          done
          echo
          echo "## GATE ERROR"
          echo "$GATE_TAIL"
          echo
          M1='<<<'; M2='==='; M3='>>>'
          [ -n "${PIPE_BASE_URL:-}" ] && { M1='@@@'; M2='@@@'; M3='@@@'; }
          echo "Fix the error. Output ONLY correction blocks in EXACTLY this"
          echo "syntax (no markdown, no code fences, no bold):"
          echo "${M1}FILE path/relative/to/repo"
          echo "${M1}SEARCH"
          echo "exact lines copied verbatim from the file above"
          echo "${M2}REPLACE"
          echo "corrected lines"
          echo "${M3}END"
          echo "Or replace a whole file:"
          echo "${M1}NEWFILE path/relative/to/repo"
          echo "full corrected file content"
          echo "${M3}END"
          echo "End with EXPECT: <one line>."
        } > "$BFP"
        log "bugfix call $bfx"
        BOUT=$(model_call < "$BFP")
        [ -z "$BOUT" ] && BOUT=$(model_call < "$BFP")
        [ -z "$BOUT" ] && break
        printf '%s\n' "$BOUT" > "/tmp/orch/handler-pipeline-$TICKET-bugfix-reply-$bfx.md"
        BAPPLY=$(printf '%s' "$BOUT" | python3 "$OPS/scripts/map-pipeline-apply.py" --overwrite); brc=$?
        if [ $brc -ne 0 ]; then
          GATE_TAIL="Your correction blocks failed to apply: $BAPPLY"
          bfx=$((bfx + 1)); continue
        fi
        git add -A
        if BUILD_OUT=$(cd backend && "$GO" build ./... 2>&1) \
           && SUITE_OUT=$(bash scripts/test-cards-sharded.sh 6 2>&1); then
          log "GATE GREEN after bugfix round $bfx"
          git commit -qm "reparse(handler-task-$TICKET): handler-pipeline card build (staged run, $bfx bugfix rounds)"
          if [ $PUSH -eq 1 ]; then
            git push -qf origin "HEAD:refs/heads/reparse/handler-task-$TICKET" && log "pushed reparse/handler-task-$TICKET"
          fi
          exit 0
        fi
        GATE_TAIL="Gate failed:
$(printf '%s\n%s' "${BUILD_OUT:-}" "${SUITE_OUT:-}" | command grep -vE '^ok ' | tail -c 2500)"
        log "bugfix round $bfx: still red"
        bfx=$((bfx + 1))
      done
    fi
    git reset -q HEAD >/dev/null 2>&1; git checkout -q -- . && git clean -qfd
  fi
  PROMPT_FILE="/tmp/orch/handler-pipeline-$TICKET-retry.md"
  { cat "$PACK"; echo; echo "## PREVIOUS ATTEMPT FAILED — resend ALL corrected blocks"; echo "$GATE_TAIL"; } > "$PROMPT_FILE"
  attempt=$((attempt + 1))
done
log "exhausted 2 calls — escalate to agentic worker"
exit 2
