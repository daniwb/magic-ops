#!/usr/bin/env bash
# map-pipeline — staged (non-agentic) processing of one REPARSE-MAP ticket.
#
# Dani 2026-08-07: "less thinking, more doing" — the map workflow is
# stereotyped, so the harness does the deterministic stages and the model
# gets ONE focused patch call (plus at most one retry with the failure).
# ~5-10x cheaper than the agentic loop; escalate to the agentic worker only
# when this exits nonzero.
#
# Usage: map-pipeline.sh TICKET_ID [--push]
#   PIPE_MODEL   model for the patch call (default claude-sonnet-5;
#                gpt-oss:120b + PIPE_BASE_URL=http://127.0.0.1:4102 = local)
#   PIPE_BASE_URL optional ANTHROPIC_BASE_URL override (shim for local)
#   CLONE        working clone (default /tmp/work/pipe-clone, created fresh)
# Exit: 0 gate-green (branch pushed with --push), 4 park verdict,
#       2 gate red after retry (escalate), other = infra error.
set -uo pipefail
TICKET="${1:?ticket id}"; shift || true
PUSH=0; [ "${1:-}" = "--push" ] && PUSH=1
OPS="${OPS:-/opt/development/magic-ops}"
REPO="${REPO:-/opt/development/test/openmagic}"
CLONE="${CLONE:-/tmp/work/pipe-clone}"
MODEL="${PIPE_MODEL:-claude-sonnet-5}"
GO=/usr/local/go/bin/go
export GOCACHE=/opt/development/.gocache-magic
LOG="/tmp/orch/pipeline-$TICKET.log"
: > "$LOG"
log() { printf '[%s] pipe-%s: %s\n' "$(date +%H:%M:%S)" "$TICKET" "$*" | tee -a "$LOG"; }
ATTEMPT_ID=""
finish_attempt() {
  local rc="$1" outcome failure tok verdict reply
  [ -z "$ATTEMPT_ID" ] && return 0
  case "$rc" in
    0) outcome=green; failure="";;
    4)
      outcome=parked
      reply=$(ls -1t "/tmp/orch/pipeline-$TICKET-reply-"*.md 2>/dev/null | head -1)
      verdict=$(command grep -ahom1 'VERDICT: [A-Z_]*' "$reply" 2>/dev/null | awk '{print tolower($2)}')
      failure="verdict_${verdict:-unknown}"
      ;;
    2) outcome=failed; failure=gate_exhausted;;
    *) outcome=failed; failure=infra;;
  esac
  tok=$(command grep -a 'tokens:' "$LOG" 2>/dev/null | python3 -c '
import re,sys
s={"in":0,"out":0,"cache_r":0,"cache_w":0}
for line in sys.stdin:
  for k,v in re.findall(r"(in|out|cache_r|cache_w)=(\d+)",line): s[k]+=int(v)
print("%d %d %d %d"%(s["in"],s["out"],s["cache_r"],s["cache_w"]))' 2>/dev/null)
  read -r tin tout tcr tcw <<<"${tok:-0 0 0 0}"
  jq -n --argjson id "$ATTEMPT_ID" --arg outcome "$outcome" --arg failure "$failure" \
    --argjson tin "${tin:-0}" --argjson tout "${tout:-0}" --argjson cr "${tcr:-0}" --argjson cw "${tcw:-0}" \
    --argjson before "${BASE_SHAPE:-0}" --argjson after "${NEW_SHAPE:-${BASE_SHAPE:-0}}" \
    '{id:$id,outcome:$outcome,failure_kind:$failure,input_tokens:$tin,output_tokens:$tout,cache_read:$cr,cache_write:$cw,metrics:{miss_before:$before,miss_after:$after}}' \
    | curl -s -m 10 -X POST "${DISPATCHER:-http://127.0.0.1:9999}/attempt/finish" -H 'Content-Type: application/json' -d @- >/dev/null 2>&1 || true
}
trap 'rc=$?; finish_attempt "$rc"' EXIT

# ---- Stage 0: fresh clone on a task branch ----
rm -rf "$CLONE"
git clone -q "file://$REPO" "$CLONE" || exit 1
cd "$CLONE" || exit 1
git remote set-url origin "$(cd "$REPO" && git remote get-url origin)"
git fetch -q origin main && git checkout -qb "pipe-$TICKET" origin/main

# ---- Stage A: deterministic context pack ----
PACK="/tmp/orch/pipeline-$TICKET-pack.md"
if ! python3 "$OPS/scripts/map-pipeline-pack.py" "$TICKET" --repo "$CLONE" > "$PACK" 2>>"$LOG"; then
  log "pack failed (not a map ticket?)"; exit 1
fi
log "pack built: $(wc -c < "$PACK") bytes"

SHAPE=$(command grep -oP 'Miss shape: `\K[^`]+' "$PACK" | head -1)
# --review-pile prints only the TOP-40 demand shapes, so a small shape
# (e.g. 15 misses) is invisible there — grep would report 0 and the gate
# would be blind. Fall back to total-misses: this clone is isolated, so a
# total drop can only come from our patch.
shape_count() {
  local pile n
  pile=$(python3 scripts/paragraph/reparse.py --review-pile 2>/dev/null)
  n=$(printf '%s' "$pile" | command grep -F " $SHAPE " | awk '{print $1; exit}')
  if [ -n "$n" ]; then printf '%s' "$n"; else
    printf '%s' "$pile" | command grep -oP 'total-misses: \K\d+'
  fi
}
BASE_SHAPE=$(shape_count); BASE_SHAPE=${BASE_SHAPE:-0}
log "baseline: shape-or-total '$SHAPE' = $BASE_SHAPE"
OPS_SHA=$(git -C "$OPS" rev-parse HEAD 2>/dev/null || true)
REPO_SHA=$(git rev-parse HEAD 2>/dev/null || true)
PACK_SHA=$(sha256sum "$PACK" | awk '{print $1}')
ATTEMPT_ID=$(jq -n --argjson ticket "$TICKET" --arg worker "${PIPE_WORKER_ID:-}" --arg model "$MODEL" \
  --arg ops "$OPS_SHA" --arg repo "$REPO_SHA" --arg pack "$PACK_SHA" \
  '{ticket_id:$ticket,worker_id:$worker,pipeline:"map",model:$model,ops_sha:$ops,repo_sha:$repo,pack_sha:$pack}' \
  | curl -s -m 10 -X POST "${DISPATCHER:-http://127.0.0.1:9999}/attempt/start" -H 'Content-Type: application/json' -d @- \
  | jq -r '.id // empty' 2>/dev/null)

# ---- Stage B/C loop: model call -> apply -> gate (max 2 calls) ----
model_call() { # stdin: prompt -> stdout: model text
  # Codex lane (PIPE_ENGINE=codex): same staged single-shot contract as the
  # claude branch below (pack in on stdin, edit-blocks/verdict/NEED text
  # out), via `codex exec --json` instead of `claude -p`. --sandbox
  # read-only is a soft guard, not a hard tool-block like claude's
  # --disallowedTools — codex is inherently agentic and MAY explore the
  # clone with read-only shell commands despite the pack's "no exploration
  # budget" framing; that's a real cost-model difference from the claude
  # branch, not a bug. `codex exec --json` streams JSONL events; the reply
  # is the LAST `agent_message` item (codex's own commentary/final channel
  # split — earlier agent_message items are intermediate commentary, per
  # codex's own system prompt), and per-call usage comes off the trailing
  # `turn.completed` event. Verified live 2026-08-16 against a real pack
  # (ticket #3452): correctly emitted a NEED: line, same as claude.
  if [ "${PIPE_ENGINE:-}" = codex ]; then
    local raw
    raw=$(timeout -k 30 900 codex exec --json --sandbox read-only -m "$MODEL" 2>>"$LOG")
    printf '%s' "$raw" > "/tmp/orch/pipeline-$TICKET-raw-last.json"
    printf '%s' "$raw" | python3 -c "
import json, sys
text, tin, tout, cr, cw = '', 0, 0, 0, 0
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except Exception:
        continue
    if ev.get('type') == 'item.completed' and ev.get('item', {}).get('type') == 'agent_message':
        text = ev['item'].get('text', '')
    elif ev.get('type') == 'turn.completed':
        u = ev.get('usage', {})
        tin, cr, cw = u.get('input_tokens', 0), u.get('cached_input_tokens', 0), u.get('cache_write_input_tokens', 0)
        tout = u.get('output_tokens', 0) + u.get('reasoning_output_tokens', 0)
print('tokens: in=%d out=%d cache_r=%d cache_w=%d' % (tin, tout, cr, cw), file=sys.stderr)
sys.stdout.write(text)
" 2>>"$LOG"
    return
  fi
  # Local lane (PIPE_BASE_URL): bypass the claude CLI — it always advertises
  # internal tools, and gpt-oss answers with finish_reason=tool_calls + empty
  # content. Bare /v1/messages with NO tools forces final-channel text
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
mt = max(1500, min(4000, 10000 - len(p)//3))  # 2026-08-09 pm: measured window today: in+out 10.3k ok, 14.5k peg-native 500 -> budget 12k; overshoot aborts clean, ticket returns
print(json.dumps({'model': '$MODEL', 'max_tokens': mt, 'messages': [{'role': 'user', 'content': p}]}))")
    raw=$(curl -s -m 1500 "$PIPE_BASE_URL/v1/messages" \
      -H 'content-type: application/json' -H "x-api-key: ${PIPE_AUTH_TOKEN:-ollama}" \
      -H 'anthropic-version: 2023-06-01' \
      -d "$body")
    printf '%s' "$raw" > "/tmp/orch/pipeline-$TICKET-raw-last.json"
    printf '%s' "$raw" | command grep '^data: ' | sed 's/^data: //' \
      | jq -rs '"tokens: in=\([.[] | select(.type=="message_start") | .message.usage.input_tokens] | add // 0) out=\([.[] | .usage.output_tokens? // empty] | max // 0) cache_r=0 cache_w=0"' >> "$LOG" 2>/dev/null
    printf '%s' "$raw" | command grep '^data: ' | sed 's/^data: //' \
      | jq -rs '[.[] | select(.type=="content_block_delta") | .delta.text // empty] | join("")'
    return
  fi
  local raw
  raw=$(timeout -k 30 900 claude -p --output-format json --model "$MODEL" \
      --max-turns "${PIPE_MAX_TURNS:-5}" --permission-mode bypassPermissions \
      --disallowedTools 'Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill,NotebookEdit' \
      --append-system-prompt 'You have NO working tools — every tool call will be denied. Do not attempt any. Reply with plain text only; if you need more code regions, use the NEED: mechanism described in the prompt.' \
      2>>"$LOG")
  printf '%s' "$raw" | jq -r '"tokens: in=\(.usage.input_tokens // 0) out=\(.usage.output_tokens // 0) cache_r=\(.usage.cache_read_input_tokens // 0) cache_w=\(.usage.cache_creation_input_tokens // 0)"' >> "$LOG" 2>/dev/null
  # always keep the last raw CLI JSON — "empty reply" was undiagnosable without it
  printf '%s' "$raw" > "/tmp/orch/pipeline-$TICKET-raw-last.json"
  printf '%s' "$raw" | jq -r '.result // empty'
}


# flip_wave_gate: run the same flip-batch the integrator will run, THEN the
# vocab lint — an eligibility-overreaching patch (e.g. suddenly claiming
# morph, 2597/2598/2601 on 2026-08-08) passes plain tests locally but flips
# unregistered-effect cards at the integrator and reddens the whole wave.
# carddb is reverted afterwards so the branch never carries flips.
flip_wave_gate() {
  python3 scripts/paragraph/reparse.py --flip-batch 300 --tag pipe-gate >> "$LOG" 2>&1
  local rc=0
  (cd backend && timeout 600 "$GO" test ./cards/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes' -count=1 2>&1) || rc=1
  git checkout -q -- backend/data/carddb 2>/dev/null
  return $rc
}

run_bugfix_gate() { # green -> commit+push+0
  if BUILD_OUT=$(cd backend && "$GO" build ./... 2>&1) \
     && TEST_OUT=$(cd backend && timeout 600 "$GO" test ./cards/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes' -count=1 2>&1) \
     && WAVE_OUT=$(flip_wave_gate); then
    NEW_SHAPE=$(shape_count); NEW_SHAPE=${NEW_SHAPE:-$BASE_SHAPE}
    if [ "$NEW_SHAPE" -lt "$BASE_SHAPE" ]; then
      log "GATE GREEN after bugfix: shape $BASE_SHAPE -> $NEW_SHAPE"
      git add -A; git commit -qm "reparse(task-$TICKET): map-pipeline patch (bugfix round) — $SHAPE $BASE_SHAPE->$NEW_SHAPE"
      [ $PUSH -eq 1 ] && git push -qf origin "HEAD:refs/heads/reparse/task-$TICKET" && log "pushed reparse/task-$TICKET"
      return 0
    fi
    GATE_TAIL="Build+tests green but shape '$SHAPE' unchanged ($BASE_SHAPE -> $NEW_SHAPE)."
  else
    GATE_TAIL="Gate failed:
$(printf '%s\n%s\n%s' "${BUILD_OUT:-}" "${TEST_OUT:-}" "${WAVE_OUT:-}" | tail -c 2500)"
  fi
  log "bugfix gate: still red"
  return 1
}

attempt=1
PROMPT_FILE="$PACK"
while [ $attempt -le 2 ]; do
  log "model call $attempt (model $MODEL)"
  OUT=$(model_call < "$PROMPT_FILE")
  if [ -z "$OUT" ]; then
    ST=$(jq -r '.subtype // "?"' "/tmp/orch/pipeline-$TICKET-raw-last.json" 2>/dev/null)
    log "empty model reply (subtype=$ST, raw saved) — retrying once"
    OUT=$(model_call < "$PROMPT_FILE")
    [ -z "$OUT" ] && { log "empty twice — abort"; exit 1; }
  fi
  printf '%s\n' "$OUT" > "/tmp/orch/pipeline-$TICKET-reply-$attempt.md"

  # NEED rounds: the model may request missing code regions up to twice per
  # run (one round was consistently not enough on tail-end tickets — models
  # re-asked and the reply died as rc=5; a NEED continue costs no attempt).
  if printf '%s' "$OUT" | command grep -q '^NEED:' && [ "${NEED_USED:-0}" -lt 2 ]; then
    NEED_USED=$(( ${NEED_USED:-0} + 1 ))
    log "model requested regions (round $NEED_USED): $(printf '%s' "$OUT" | command grep '^NEED:' | tr '\n' ' ')"
    ADD=$(printf '%s' "$OUT" | python3 "$OPS/scripts/pipeline-fetch-regions.py")
    NEEDF="/tmp/orch/pipeline-$TICKET-need.md"
    if [ "$NEED_USED" = 1 ]; then
      { cat "$PACK"; echo; echo "## REQUESTED CODE REGIONS"; printf '%s\n' "$ADD"; } > "$NEEDF"
    else
      { echo; echo "## REQUESTED CODE REGIONS (round 2 — FINAL)"; printf '%s\n' "$ADD"
        echo; echo "No further regions will be served. Produce edit blocks or a verdict NOW."; } >> "$NEEDF"
    fi
    PROMPT_FILE="$NEEDF"
    continue
  fi

  APPLY_OUT=$(printf '%s' "$OUT" | python3 "$OPS/scripts/map-pipeline-apply.py"); rc=$?
  if [ $rc -eq 4 ]; then log "park: $APPLY_OUT"; echo "$APPLY_OUT"; exit 4; fi
  if [ $rc -ne 0 ]; then
    log "apply failed (rc=$rc): $APPLY_OUT"
    GATE_TAIL="Your edit blocks failed to apply: $APPLY_OUT"
  else
    log "applied; gating"
    if BUILD_OUT=$(cd backend && "$GO" build ./... 2>&1) \
       && TEST_OUT=$(cd backend && timeout 600 "$GO" test ./cards/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes' -count=1 2>&1) \
       && WAVE_OUT=$(flip_wave_gate); then
      NEW_SHAPE=$(shape_count); NEW_SHAPE=${NEW_SHAPE:-$BASE_SHAPE}
      if [ "$NEW_SHAPE" -lt "$BASE_SHAPE" ]; then
        log "GATE GREEN: shape $BASE_SHAPE -> $NEW_SHAPE"
        git add -A
        git commit -qm "reparse(task-$TICKET): map-pipeline patch — $SHAPE $BASE_SHAPE->$NEW_SHAPE (staged non-agentic run)"
        if [ $PUSH -eq 1 ]; then
          git push -qf origin "HEAD:refs/heads/reparse/task-$TICKET" && log "pushed reparse/task-$TICKET"
        fi
        exit 0
      fi
      GATE_TAIL="Build+tests green but shape '$SHAPE' unchanged ($BASE_SHAPE -> $NEW_SHAPE). Your mapping did not fire on the review pile."
      log "gate: no shape delta"
    else
      GATE_TAIL="Gate failed:
$(printf '%s\n%s\n%s' "${BUILD_OUT:-}" "${TEST_OUT:-}" "${WAVE_OUT:-}" | tail -c 2500)"
      log "gate: build/tests/flip-wave red"
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
        BAPPLY=$(printf '%s' "$BOUT" | python3 "$OPS/scripts/map-pipeline-apply.py" --overwrite); brc=$?
        if [ $brc -ne 0 ]; then GATE_TAIL="Correction blocks failed to apply: $BAPPLY"; bfx=$((bfx+1)); continue; fi
        if run_bugfix_gate; then exit 0; fi
        bfx=$((bfx+1))
      done
    fi
    git reset -q HEAD >/dev/null 2>&1; git checkout -q -- . && git clean -qfd
  fi
  # retry prompt = original pack + failure
  PROMPT_FILE="/tmp/orch/pipeline-$TICKET-retry.md"
  { cat "$PACK"; echo; echo "## PREVIOUS ATTEMPT FAILED — fix and resend the FULL corrected blocks"; echo "$GATE_TAIL"; } > "$PROMPT_FILE"
  attempt=$((attempt + 1))
done
log "exhausted 2 calls — escalate to agentic worker"
exit 2
