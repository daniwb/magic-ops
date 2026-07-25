#!/bin/bash
# DeepSeek-Primitive-Builder-Schleife (direkt über api.deepseek.com).
# Nutzt deepseek-v4-pro (Primitive sind high-stakes), Peak-Hours ausgespart.
# Läuft als Dauerschleife (Batches à MAX_PRIMS, dann Pause).
set -uo pipefail

unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_API_KEY
export GLM_WORKER=1
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_API_KEY="$(cat /opt/development/deepseek-sandbox/.deepseek_key)"
export MODEL="${DS_PRIM_MODEL:-deepseek-v4-pro}"
export BUILDER_ID=primds
export USAGE_LIMIT_PCT=0
export GOFLAGS=-p=3
export PEAK_PAUSE=1
export MAX_PRIMS="${MAX_PRIMS:-5}"
export CLONE=/tmp/work/prim-builder-ds

DEDUP_MARK=/tmp/vocab-dedup-last
while true; do
  # Dedup-Vorlauf höchstens alle 2h (schont Tokens; siehe skill dedup-vocab)
  last=0; [ -s "$DEDUP_MARK" ] && last=$(cat "$DEDUP_MARK" 2>/dev/null || echo 0)
  nows=$(date +%s)
  if [ $((nows - last)) -ge 7200 ]; then
    echo "$nows" > "$DEDUP_MARK"
    MODEL="$MODEL" bash /opt/development/magic-claude/scripts/vocab-dedup-v4.sh || true
  fi
  bash /opt/development/magic-claude/scripts/dispatcher-primitive-builder-v4.sh
  sleep 300
done
