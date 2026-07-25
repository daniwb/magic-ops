#!/bin/bash
# DeepSeek-Card-Worker (direkt über api.deepseek.com, NICHT Ollama).
# flash→pro zweistufig (CHEAP_FIRST), Peak-Hours ausgespart (doppelte Kosten).
set -uo pipefail

unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_API_KEY  # AUTH_TOKEN=ollama → 401
export GLM_WORKER=1  # Worker-interner env-guard: NICHT wieder auf Ollama unsetzen
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_API_KEY="$(cat /opt/development/deepseek-sandbox/.deepseek_key)"
export MODEL_HAIKU="${DS_CHEAP:-deepseek-v4-flash}"    # Erstversuch
export MODEL_SONNET="${DS_ESCALATE:-deepseek-v4-pro}"  # Eskalation ab Versuch 2
export CHEAP_FIRST=1
export WORKER_MAX_TURNS=40
export USAGE_LIMIT_PCT=0        # Claude-Gate irrelevant
export GOFLAGS=-p=3
export CLAUDE_TIMEOUT=1200
export PEAK_PAUSE=1             # UTC 1-4h + 6-10h aussparen

WID="${1:-wd}"
exec bash /opt/development/magic-claude/scripts/dispatcher-worker-real.sh "$WID" "/tmp/work/disp-$WID"
