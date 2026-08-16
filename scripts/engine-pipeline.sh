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
OPS="${OPS:-/opt/development/magic-ops}"
REPO="${REPO:-/opt/development/test/openmagic}"
CAPABILITY_ID="${CAPABILITY_ID:-0}"
BRANCH="reparse/engine-task-$TICKET"
[ "$CAPABILITY_ID" != 0 ] && BRANCH="reparse/capability-$CAPABILITY_ID"
CLONE="${CLONE:-/tmp/work/engine-pipe-clone}"
MODEL="${PIPE_MODEL:-claude-sonnet-5}"
GO=/usr/local/go/bin/go
export GOCACHE=/opt/development/.gocache-magic
LOG="/tmp/orch/engine-pipeline-$TICKET.log"
: > "$LOG"
log() { printf '[%s] epipe-%s: %s\n' "$(date +%H:%M:%S)" "$TICKET" "$*" | tee -a "$LOG"; }
ATTEMPT_ID=""
finish_attempt() {
  local rc="$1" outcome failure tok
  [ -z "$ATTEMPT_ID" ] && return 0
  case "$rc" in
    0) outcome=green; failure="";; 4) outcome=parked; failure=framework_or_ambiguous;;
    2) outcome=failed; failure=gate_exhausted;; *) outcome=failed; failure=infra;; esac
  tok=$(command grep -a 'tokens:' "$LOG" 2>/dev/null | python3 -c '
import re,sys
s={"in":0,"out":0,"cache_r":0,"cache_w":0}
for line in sys.stdin:
  for k,v in re.findall(r"(in|out|cache_r|cache_w)=(\d+)",line): s[k]+=int(v)
print("%d %d %d %d"%(s["in"],s["out"],s["cache_r"],s["cache_w"]))' 2>/dev/null)
  read -r tin tout tcr tcw <<<"${tok:-0 0 0 0}"
  jq -n --argjson id "$ATTEMPT_ID" --arg outcome "$outcome" --arg failure "$failure" \
    --argjson tin "${tin:-0}" --argjson tout "${tout:-0}" --argjson cr "${tcr:-0}" --argjson cw "${tcw:-0}" \
    '{id:$id,outcome:$outcome,failure_kind:$failure,input_tokens:$tin,output_tokens:$tout,cache_read:$cr,cache_write:$cw}' \
    | curl -s -m 10 -X POST "${DISPATCHER:-http://127.0.0.1:9999}/attempt/finish" -H 'Content-Type: application/json' -d @- >/dev/null 2>&1 || true
}
trap 'rc=$?; finish_attempt "$rc"' EXIT

rm -rf "$CLONE"
git clone -q "file://$REPO" "$CLONE" || exit 1
cd "$CLONE" || exit 1
git remote set-url origin "$(cd "$REPO" && git remote get-url origin)"
git fetch -q origin main && git checkout -qb "epipe-$TICKET" origin/main

PACK="/tmp/orch/engine-pipeline-$TICKET-pack.md"
PACK_ARGS=("$TICKET" --repo "$CLONE")
[ "$CAPABILITY_ID" != 0 ] && PACK_ARGS+=(--capability "$CAPABILITY_ID")
if ! python3 "$OPS/scripts/engine-pipeline-pack.py" "${PACK_ARGS[@]}" > "$PACK" 2>>"$LOG"; then
  log "pack failed (ticket has no missing_prim?)"; exit 1
fi
log "pack built: $(wc -c < "$PACK") bytes"
OPS_SHA=$(git -C "$OPS" rev-parse HEAD 2>/dev/null || true)
REPO_SHA=$(git rev-parse HEAD 2>/dev/null || true)
PACK_SHA=$(sha256sum "$PACK" | awk '{print $1}')
ATTEMPT_ID=$(jq -n --argjson ticket "$TICKET" --argjson capability "$CAPABILITY_ID" \
  --arg worker "${PIPE_WORKER_ID:-}" --arg model "$MODEL" --arg ops "$OPS_SHA" --arg repo "$REPO_SHA" --arg pack "$PACK_SHA" \
  '{ticket_id:$ticket,capability_id:$capability,worker_id:$worker,pipeline:"engine",model:$model,ops_sha:$ops,repo_sha:$repo,pack_sha:$pack}' \
  | curl -s -m 10 -X POST "${DISPATCHER:-http://127.0.0.1:9999}/attempt/start" -H 'Content-Type: application/json' -d @- \
  | jq -r '.id // empty' 2>/dev/null)

model_call() {
  # Local lane (PIPE_BASE_URL): bare /v1/messages curl, no tools — the claude
  # CLI's advertised tools make gpt-oss emit tool_calls with empty content
  # (ported from handler-pipeline.sh, validated green 2026-08-07).
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
# 2026-08-09 le1: engine packs (~30kB = 9k prompt tokens) bottomed the old
# 6900-budget out at the 1600 floor; gpt-oss spent it all on the analysis
# channel and never reached the final channel (empty reply). Box accepted
# in=8710+out=1600 fine today, so the effective window is far above the old
# under-load 6.9k measurement. Failure mode on overshoot is a clean abort.
# NOTE: this comment lives inside a bash double-quoted python -c string —
# no double quotes in here, they truncate the script.
mt = max(1500, min(4000, 10000 - len(p)//3))
print(json.dumps({'model': '$MODEL', 'max_tokens': mt, 'messages': [{'role': 'user', 'content': p}]}))")
    raw=$(curl -s -m 1500 "$PIPE_BASE_URL/v1/messages" \
      -H 'content-type: application/json' -H "x-api-key: ${PIPE_AUTH_TOKEN:-ollama}" \
      -H 'anthropic-version: 2023-06-01' \
      -d "$body")
    printf '%s' "$raw" > "/tmp/orch/engine-pipeline-$TICKET-raw-last.json"
    printf '%s' "$raw" | command grep '^data: ' | sed 's/^data: //' \
      | jq -rs '"tokens: in=\([.[] | select(.type=="message_start") | .message.usage.input_tokens] | add // 0) out=\([.[] | .usage.output_tokens? // empty] | max // 0) cache_r=0 cache_w=0"' >> "$LOG" 2>/dev/null
    printf '%s' "$raw" | command grep '^data: ' | sed 's/^data: //' \
      | jq -rs '[.[] | select(.type=="content_block_delta") | .delta.text // empty] | join("")'
    return
  fi
  local raw
  raw=$(timeout -k 30 1200 claude -p --output-format json --model "$MODEL" \
      --max-turns "${PIPE_MAX_TURNS:-10}" --permission-mode bypassPermissions \
      --disallowedTools 'Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill,NotebookEdit' \
      --append-system-prompt 'You have NO working tools — every tool call will be denied. Do not attempt any. Reply with plain text only.' \
      2>>"$LOG")
  printf '%s' "$raw" | jq -r '"tokens: in=\(.usage.input_tokens // 0) out=\(.usage.output_tokens // 0) cache_r=\(.usage.cache_read_input_tokens // 0) cache_w=\(.usage.cache_creation_input_tokens // 0)"' >> "$LOG" 2>/dev/null
  # keep last raw CLI JSON — empty replies were error_max_turns tool-spin, undiagnosable without it
  printf '%s' "$raw" > "/tmp/orch/engine-pipeline-$TICKET-raw-last.json"
  printf '%s' "$raw" | jq -r '.result // empty'
}


# has_nontest_code: the diff must change at least one NON-test file — a
# test-only "primitive" passes every gate trivially (fresh test asserting
# current behavior) and lands phantom capability (lp1 2593/2602/2616,
# 2026-08-08: three test-only commits landed as "primitives", every
# circle-close then failed because nothing new existed to map).
has_nontest_code() {
  git diff --cached --name-only origin/main | command grep -v '_test\.go$' | command grep -q '\.\(go\|py\)$'
}

run_bugfix_gate() { # green -> commit+push+0
  git add -A
  if git diff --cached --diff-filter=AM origin/main -- '*_test.go' | command grep -q '^+func Test' \
     && has_nontest_code \
     && BUILD_OUT=$(cd backend && "$GO" build ./... 2>&1) \
     && TEST_OUT=$(cd backend && timeout 600 "$GO" test ./cards/ ./game/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes|TestCombat' -count=1 2>&1) \
     && SUITE_OUT=$(bash scripts/test-cards-sharded.sh 6 2>&1); then
    log "GATE GREEN after bugfix"
    git commit -qm "reparse(capability-$CAPABILITY_ID task-$TICKET): engine-pipeline primitive build (bugfix round)"
    [ $PUSH -eq 1 ] && git push -qf origin "HEAD:refs/heads/$BRANCH" && log "pushed $BRANCH"
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
    elif ! has_nontest_code; then
      GATE_TAIL="Gate: your diff contains ONLY test files — a primitive needs real engine/emitter code (registry entry, executor, emitter), not just a test asserting current behavior."
      log "gate: test-only diff rejected"
    elif BUILD_OUT=$(cd backend && "$GO" build ./... 2>&1) \
       && TEST_OUT=$(cd backend && timeout 600 "$GO" test ./cards/ ./game/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes|TestCombat' -count=1 2>&1) \
       && SUITE_OUT=$(bash scripts/test-cards-sharded.sh 6 2>&1); then
      log "GATE GREEN (build + tests + full suite)"
      git add -A
      git commit -qm "reparse(capability-$CAPABILITY_ID task-$TICKET): engine-pipeline primitive build (staged non-agentic run)"
      if [ $PUSH -eq 1 ]; then
        git push -qf origin "HEAD:refs/heads/$BRANCH" && log "pushed $BRANCH"
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
