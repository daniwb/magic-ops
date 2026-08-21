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
    5) outcome=failed; failure=context_exhausted;;
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
  # 2026-08-21: consolidated into scripts/model_call.py — one Python
  # entrypoint for every engine (codex/claude/openrouter/openrouter-
  # agentic/qwen-agentic) instead of per-branch bash with JSON built via
  # `python3 -c "..."` heredocs interpolated into bash strings (the direct
  # cause of the ARG_MAX curl bug on large pipe-ox tickets). Same contract
  # as before: prompt on stdin, answer text on stdout, "tokens: ..." to
  # $LOG. TICKET exported so model_call.py can still save the raw response
  # to /tmp/orch/pipeline-$TICKET-raw-last.json for post-mortem debugging.
  TICKET="$TICKET" python3 "$OPS/scripts/model_call.py" \
    --engine "${PIPE_ENGINE:-claude}" --model "$MODEL" --tier map \
    2>>"$LOG"
  return
  # --- superseded bash implementation kept below, dead code, for reference
  # only during the migration; delete once model_call.py has run cleanly in
  # production for a while. ---
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
  # pipe-ox lane (PIPE_ENGINE=openrouter): staged single-shot, same contract
  # as the claude/codex branches above — pack in on stdin, edit-blocks/
  # verdict/NEED text out. Model is a free OpenRouter reasoning model
  # (stealth/ox-alpha, 2026-08-21) via the standard OpenAI-compatible
  # /chat/completions endpoint. Two lessons carried over from the qwen3.8
  # saga earlier this session, applied from day one instead of rediscovered:
  #   1. "No tools" system override — the pack's TOOL BUDGET/NEED boilerplate
  #      is written for claude/codex which DO have real tool access; without
  #      this override an unfamiliar model can hallucinate tool-call syntax
  #      and burn its whole reply on that instead of answering (confirmed
  #      live on qwen3.8, ticket #3790).
  #   2. Reasoning cap — OpenRouter's own docs confirm ox-alpha is a
  #      reasoning model; qwen3.8 burned its ENTIRE token budget on
  #      unbounded internal reasoning with zero output before that was
  #      capped. OpenRouter exposes a first-class `reasoning.max_tokens`
  #      dial (not a blind on/off switch) — use it, plus `exclude:true` so
  #      the reasoning text itself doesn't pollute the visible content the
  #      edit-block/verdict regexes parse.
  # API key: OPENROUTER_API_KEY, sourced from $OPS/.env by pipeline-lane.sh
  # (gitignored, never commit it) — fails loudly if unset rather than
  # silently sending an unauthenticated request.
  if [ "${PIPE_ENGINE:-}" = openrouter ]; then
    : "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY not set — put it in $OPS/.env}"
    local body raw http_code
    body=$(python3 -c "
import json, sys
p = sys.stdin.read()
body = {
    'model': '$MODEL',
    'max_tokens': ${PIPE_MAX_TOKENS_CAP:-8000},
    'stream': False,
    'reasoning': {'max_tokens': ${PIPE_REASONING_TOKENS:-3000}, 'exclude': True},
    'messages': [
        {'role': 'system', 'content': 'You have NO tools available for this request — no function/tool-calling capability exists on this API call. Do not attempt any tool or function call, including Read/Grep/Glob mentioned elsewhere in the prompt; that instruction does not apply here. Answer directly in plain text using only the code/context already given, following the OUTPUT FORMAT exactly.'},
        {'role': 'user', 'content': p},
    ],
}
print(json.dumps(body))")
    # Body goes through a temp file, not -d "$body" — a large ticket (many
    # NEED-round-expanded code regions) can push the JSON well past the
    # shell's ARG_MAX, which failed hard as "curl: Argument list too long"
    # (confirmed live 2026-08-21, ticket #3891/#3914) instead of the normal
    # empty-reply/retry path — a silent-looking crash, not a model failure.
    local bodyfile
    bodyfile=$(mktemp)
    printf '%s' "$body" > "$bodyfile"
    raw=$(curl -s -m "${PIPE_LOCAL_TIMEOUT:-300}" -w '\n%{http_code}' \
      https://openrouter.ai/api/v1/chat/completions \
      -H "Authorization: Bearer $OPENROUTER_API_KEY" \
      -H 'content-type: application/json' \
      -H 'HTTP-Referer: https://github.com/daniwb/magic-ops' \
      -H 'X-Title: pipe-ox' \
      --data-binary "@$bodyfile")
    rm -f "$bodyfile"
    http_code=$(printf '%s' "$raw" | tail -1)
    raw=$(printf '%s' "$raw" | sed '$d')
    printf '%s' "$raw" > "/tmp/orch/pipeline-$TICKET-raw-last.json"
    if [ "$http_code" = 429 ]; then
      echo "openrouter: HTTP 429 rate limited" >>"$LOG"
      return
    fi
    if [ "$http_code" != 200 ]; then
      echo "openrouter: HTTP $http_code — $(printf '%s' "$raw" | head -c 300)" >>"$LOG"
      return
    fi
    printf '%s' "$raw" | jq -r '"tokens: in=\(.usage.prompt_tokens // 0) out=\(.usage.completion_tokens // 0) cache_r=\(.usage.prompt_tokens_details.cached_tokens // 0) cache_w=0"' >>"$LOG" 2>/dev/null
    printf '%s' "$raw" | jq -r '.choices[0].message.content // empty'
    return
  fi
  # pipe-ox agentic lane (PIPE_ENGINE=openrouter-agentic): built 2026-08-21
  # after the staged branch above repeatedly hit its NEED-round cap (3 of
  # ~18 tickets in the first live hour) — the same symptom that drove
  # qwen-agentic-call.py's creation. Real read_file/grep/list_dir tools
  # instead of the pre-packed context + bounded NEED protocol.
  if [ "${PIPE_ENGINE:-}" = openrouter-agentic ]; then
    python3 "$OPS/scripts/openrouter-agentic-call.py" --repo "$PWD" \
      --base-url "${PIPE_BASE_URL:-https://openrouter.ai/api/v1}" --model "$MODEL" \
      --max-turns "${PIPE_AGENTIC_MAX_TURNS:-25}" --max-tokens "${PIPE_MAX_TOKENS_CAP:-8000}" \
      --reasoning-tokens "${PIPE_REASONING_TOKENS:-3000}" \
      2>>"$LOG"
    return
  fi
  # pipe-qwen agentic lane (PIPE_ENGINE=qwen-agentic): unlike the PIPE_BASE_URL
  # branch below (single completion call, no real tools), this genuinely
  # explores the clone via real tool-calling (read_file/grep/list_dir) —
  # confirmed live 2026-08-17 to work dramatically better than either the
  # staged single-shot approach OR the same agentic loop with the model's
  # default sampling: a ticket that took 3.5hr and never succeeded staged
  # completed correctly in 12.5 minutes once thinking was suppressed
  # (qwen-agentic-call.py handles the temperature/enable_thinking fix
  # internally). model_call()'s contract (stdin pack in, stdout text out,
  # "tokens: ..." to $LOG) is honored exactly, so the surrounding gate/
  # bugfix/commit/push machinery below needs zero changes — the agentic
  # loop just runs INSIDE what looks like one model_call() from the
  # caller's perspective. Runs from $CLONE (already the cwd here).
  if [ "${PIPE_ENGINE:-}" = qwen-agentic ]; then
    python3 "$OPS/scripts/qwen-agentic-call.py" --repo "$PWD" \
      --base-url "${PIPE_BASE_URL:-http://192.168.1.251:8080}" --model "$MODEL" \
      --max-turns "${PIPE_AGENTIC_MAX_TURNS:-25}" --max-tokens "${PIPE_MAX_TOKENS_CAP:-8000}" \
      2>>"$LOG"
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
    # Budget floor/cap/context-window are configurable (PIPE_MIN_TOKENS/
    # PIPE_MAX_TOKENS_CAP/PIPE_CTX_BUDGET) — defaults below are UNCHANGED
    # from the original 2026-08-09 gpt-oss tuning (that server context-
    # shifted and corrupted its own stream past an ~8-12k combined window,
    # "peg-native format" 500, 2026-08-08). qwen3.8/llama-server on
    # 192.168.1.251:8080 reports n_ctx=131072 (confirmed via /v1/models,
    # 2026-08-16/17) — none of that applies there; launch-pipe-qwen.sh
    # overrides these to much larger values. Backward-compatible: any lane
    # not setting these envs gets the exact old numbers.
    local body
    body=$(python3 -c "
import json, sys
p = sys.stdin.read()
mt = max(${PIPE_MIN_TOKENS:-1500}, min(${PIPE_MAX_TOKENS_CAP:-4000}, ${PIPE_CTX_BUDGET:-10000} - len(p)//3))
# stream explicit (2026-08-16, qwen3.8/llama-server on 192.168.1.251:8080):
# without it this server returns a plain JSON object, not SSE — the 'data: '
# grep below would match nothing and every call would silently come back
# empty. Explicit stream:true is a superset of whatever the earlier local
# servers (gpt-oss) defaulted to, so this is backward-compatible.
# system override (2026-08-17, qwen3.8): the pack's own '## TOOL BUDGET'
# section ('You may Read/Grep/Glob...') is boilerplate written for the
# claude/codex branches, which DO have real tool access there (claude's
# CLI would otherwise advertise tools; codex genuinely can read its own
# sandbox). This branch sends a bare completion call with NO 'tools' array
# at all — gpt-oss handled that mismatch fine (fell back to plain text),
# but qwen3.8 instead emits its own trained '<tool_call><function=Grep>...'
# text syntax and burns its entire budget on that, never answering
# (confirmed live, ticket #3790: two full calls, zero edit blocks, zero
# verdict — 100% consumed by hallucinated tool-call text). Mirrors the
# claude branch's --append-system-prompt override below.
# ROOT CAUSE of the empty-reply/no-shape-delta pattern (2026-08-17): this
# call never set temperature (server default 1.0 — ABOVE either of Qwen3's
# own documented presets) and never suppressed "thinking", which turned
# out unbounded: live testing found 5 consecutive full-budget calls (up to
# 24000 tokens) burned ENTIRELY on reasoning with zero actual answer, in
# BOTH this staged mode and a real agentic tool-loop test. Suppressing
# thinking via chat_template_kwargs.enable_thinking:false (llama-server's
# vLLM-compatible convention — the Qwen-native '/no_think' suffix did NOT
# work against this template, confirmed live) is a dramatic, verified fix:
# a control call dropped from 55 completion tokens (with a full
# reasoning_content block) to 4 (direct answer only). Paired with Qwen3's
# documented non-thinking-mode sampling preset (temp 0.7/top_p 0.8/top_k
# 20/min_p 0 vs. thinking-mode's 0.6/0.95/20/0). Overridable via
# PIPE_DISABLE_THINKING=0 if a future non-Qwen local server chokes on
# these fields.
disable_thinking = ${PIPE_DISABLE_THINKING:-1}
extra = {}
if disable_thinking:
    extra = {'temperature': ${PIPE_TEMPERATURE:-0.7}, 'top_p': ${PIPE_TOP_P:-0.8},
              'top_k': ${PIPE_TOP_K:-20}, 'min_p': ${PIPE_MIN_P:-0},
              'chat_template_kwargs': {'enable_thinking': False}}
body = {'model': '$MODEL', 'max_tokens': mt, 'stream': True,
        'system': 'You have NO tools available for this request — no function/tool-calling capability exists on this API call. Do not attempt any tool or function call, including Read/Grep/Glob mentioned elsewhere in the prompt; that instruction does not apply here. Answer directly in plain text using only the code/context already given, following the OUTPUT FORMAT exactly.',
        'messages': [{'role': 'user', 'content': p}]}
body.update(extra)
print(json.dumps(body))")
    raw=$(curl -s -m "${PIPE_LOCAL_TIMEOUT:-1500}" "$PIPE_BASE_URL/v1/messages" \
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
  # Cap is configurable (PIPE_MAX_NEED_ROUNDS, default 2 — unchanged from
  # the original claude/codex tuning): pipe-ox's stealth/ox-alpha ignored
  # the round-2 "FINAL, answer now" instruction and asked for a 3rd round
  # in 2/2 initial test tickets (2026-08-21) — a real per-model behavior
  # difference, not a bug in the cap itself. Backends that comply with
  # "FINAL" (claude/codex, confirmed live) are unaffected by raising this.
  if printf '%s' "$OUT" | command grep -q '^NEED:'; then
    if [ "${NEED_USED:-0}" -ge "${PIPE_MAX_NEED_ROUNDS:-2}" ]; then
      log "context exhausted: model requested region round $(( ${NEED_USED:-0} + 1 ))"
      exit 5
    fi
    NEED_USED=$(( ${NEED_USED:-0} + 1 ))
    log "model requested regions (round $NEED_USED): $(printf '%s' "$OUT" | command grep '^NEED:' | tr '\n' ' ')"
    ADD=$(printf '%s' "$OUT" | python3 "$OPS/scripts/pipeline-fetch-regions.py")
    NEEDF="/tmp/orch/pipeline-$TICKET-need.md"
    if [ "$NEED_USED" = 1 ]; then
      { cat "$PACK"; echo; echo "## REQUESTED CODE REGIONS"; printf '%s\n' "$ADD"; } > "$NEEDF"
    elif [ "$NEED_USED" -lt "${PIPE_MAX_NEED_ROUNDS:-2}" ]; then
      { echo; echo "## REQUESTED CODE REGIONS (round $NEED_USED)"; printf '%s\n' "$ADD"; } >> "$NEEDF"
    else
      { echo; echo "## REQUESTED CODE REGIONS (round $NEED_USED — FINAL)"; printf '%s\n' "$ADD"
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
