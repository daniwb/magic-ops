#!/usr/bin/env bash
# One no-push Factory NG Claude observation for a fully specified Engine ticket.
set -euo pipefail

OPS=/opt/development/magic-ops
SOURCE=/opt/development/test/openmagic
TICKET="${TICKET:-$OPS/docs/factory-ng/tickets/engine-switch-pt-registry-bridge-v2.json}"
RUN_ID="factory-ng-claude-switch-pt-registry-$(date -u +%Y%m%dT%H%M%SZ)"
LOG="/tmp/orch/${RUN_ID}.log"
RAW="/tmp/orch/${RUN_ID}.raw.json"
TEXT="/tmp/orch/${RUN_ID}.reply.txt"
PACK="/tmp/orch/${RUN_ID}.packet.md"
CLONE=$(mktemp -d "/tmp/${RUN_ID}.XXXXXX")

log() { printf '[%s] %s\n' "$(date -u -Is)" "$*" | tee -a "$LOG"; }
log "start: ticket=$(basename "$TICKET") clone=$CLONE"

git clone --quiet --no-hardlinks "$SOURCE" "$CLONE"
cd "$CLONE"

for raw in "$OPS/docs/factory-ng/runs/2026-08-28-engine-pt-switch-layer-v2-opus-final.raw.json" "$OPS/docs/factory-ng/runs/2026-08-28-engine-switch-pt-v2-opus-final.raw.json" "$OPS/docs/factory-ng/runs/2026-08-28-engine-switch-pt-v2-opus-format-repair.raw.json"; do
  python3 -c "import json; print(json.load(open('$raw'))['result'], end='')" | python3 "$OPS/scripts/map-pipeline-apply.py" --allow-game | tee -a "$LOG"
done
git add -A
git -c user.name='Factory NG overlay' -c user.email='factory-ng@local' commit -qm 'factory-ng: accepted switch_pt parent overlays (observation only)'

pack_args=(--ticket-spec "$TICKET" --repo "$CLONE")
if [ "${NO_TOOLS:-1}" = "1" ]; then
  pack_args+=(--no-tools)
fi
python3 "$OPS/scripts/engine-pipeline-pack.py" "${pack_args[@]}" > "$PACK"
log "packet=$(wc -c < "$PACK") bytes"

if [ "${NO_TOOLS:-1}" = "1" ]; then
  system_prompt='You have no usable tools. Use only the prepared packet. Return only its strict edit blocks, NEED request, or verdict. Do not commit, push, deploy, or describe hypothetical changes.'
  max_turns="${MAX_TURNS:-1}"
else
  system_prompt='You may use only Read, Grep, and Glob to inspect the disposable clone. Do not use Bash, Edit, Write, web, agents, or skills. Return only the prepared packet strict edit blocks, NEED request, or verdict. Do not commit, push, deploy, or describe hypothetical changes.'
  max_turns="${MAX_TURNS:-4}"
fi
timeout -k 30 1200 claude -p --output-format json --model claude-opus-5 --max-turns "$max_turns" --permission-mode plan --disallowedTools 'Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill,NotebookEdit' --append-system-prompt "$system_prompt" < "$PACK" > "$RAW"
jq -r '.result // empty' "$RAW" > "$TEXT"
if [ ! -s "$TEXT" ]; then
  log "outcome=infra_empty_claude_reply raw=$RAW"
  exit 2
fi
if command grep -q '^NEED:' "$TEXT" || command grep -q '^VERDICT:' "$TEXT"; then
  log "outcome=claude_non_patch reply=$TEXT"
  exit 0
fi

python3 "$OPS/scripts/map-pipeline-apply.py" --allow-game < "$TEXT" | tee -a "$LOG"
git diff --check
changed=$(git diff --name-only)
if [ "$changed" != $'backend/cards/registry_switch_pt.go\nbackend/cards/shape_switch_pt_test.go' ] && [ "$changed" != $'backend/cards/shape_switch_pt_test.go\nbackend/cards/registry_switch_pt.go' ]; then
  log "outcome=scope_failed changed=$(printf '%s' "$changed" | tr '\n' ',')"
  exit 3
fi
(cd backend && go build ./...)
(cd backend && go test ./cards ./game -run 'TestVocabulary|TestShape_SwitchPT|TestSwitchPTExecution' -count=1)
log "outcome=proposal_gates_passed clone=$CLONE raw=$RAW reply=$TEXT"
