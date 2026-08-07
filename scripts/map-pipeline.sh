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
OPS=/opt/development/magic-ops
REPO=/opt/development/test/openmagic
CLONE="${CLONE:-/tmp/work/pipe-clone}"
MODEL="${PIPE_MODEL:-claude-sonnet-5}"
GO=/usr/local/go/bin/go
export GOCACHE=/opt/development/.gocache-magic
LOG="/tmp/orch/pipeline-$TICKET.log"
log() { printf '[%s] pipe-%s: %s\n' "$(date +%H:%M:%S)" "$TICKET" "$*" | tee -a "$LOG"; }

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

# ---- Stage B/C loop: model call -> apply -> gate (max 2 calls) ----
model_call() { # stdin: prompt -> stdout: model text
  local env_prefix=()
  [ -n "${PIPE_BASE_URL:-}" ] && export ANTHROPIC_BASE_URL="$PIPE_BASE_URL" ANTHROPIC_AUTH_TOKEN="${PIPE_AUTH_TOKEN:-ollama}"
  local raw
  raw=$(timeout -k 30 900 claude -p --output-format json --model "$MODEL" \
      --max-turns 15 --permission-mode bypassPermissions \
      --disallowedTools 'Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill,NotebookEdit' \
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
    log "empty model reply (raw saved) — retrying once"
    OUT=$(model_call < "$PROMPT_FILE")
    [ -z "$OUT" ] && { log "empty twice — abort"; exit 1; }
  fi
  printf '%s\n' "$OUT" > "/tmp/orch/pipeline-$TICKET-reply-$attempt.md"

  # NEED round: the model may request missing code regions once per run.
  if printf '%s' "$OUT" | command grep -q '^NEED:' && [ "${NEED_USED:-0}" = 0 ]; then
    NEED_USED=1
    log "model requested regions: $(printf '%s' "$OUT" | command grep '^NEED:' | tr '\n' ' ')"
    ADD=$(printf '%s' "$OUT" | python3 "$OPS/scripts/pipeline-fetch-regions.py")
    PROMPT_FILE="/tmp/orch/pipeline-$TICKET-need.md"
    { cat "$PACK"; echo; echo "## REQUESTED CODE REGIONS"; printf '%s\n' "$ADD"; } > "$PROMPT_FILE"
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
       && TEST_OUT=$(cd backend && timeout 600 "$GO" test ./cards/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes' -count=1 2>&1); then
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
$(printf '%s\n%s' "${BUILD_OUT:-}" "${TEST_OUT:-}" | tail -c 2500)"
      log "gate: build/tests red"
    fi
    git checkout -q -- . && git clean -qfd
  fi
  # retry prompt = original pack + failure
  PROMPT_FILE="/tmp/orch/pipeline-$TICKET-retry.md"
  { cat "$PACK"; echo; echo "## PREVIOUS ATTEMPT FAILED — fix and resend the FULL corrected blocks"; echo "$GATE_TAIL"; } > "$PROMPT_FILE"
  attempt=$((attempt + 1))
done
log "exhausted 2 calls — escalate to agentic worker"
exit 2
