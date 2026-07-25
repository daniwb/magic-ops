#!/bin/bash
# Haiku-Card-Worker für den Dispatcher — nutzt die Claude-Subscription-Quota
# (kein DeepSeek/Ollama-Routing). Reines Haiku für beide Versuche (günstig);
# harte Karten gehen nach 3 Fehlversuchen in wait-triage.
set -uo pipefail

# Saubere Claude-Auth: KEIN GLM_WORKER setzen → der Worker unsetzt selbst
# ANTHROPIC_BASE_URL/API_KEY/AUTH_TOKEN und nutzt die normale Claude-Anmeldung.
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_API_KEY

export MODEL_HAIKU="${HAIKU_MODEL:-claude-haiku-4-5-20251001}"
export MODEL_SONNET="${HAIKU_MODEL:-claude-haiku-4-5-20251001}"  # Eskalation ebenfalls Haiku
export CHEAP_FIRST=1              # jeder Erstversuch auf Haiku
export WORKER_MAX_TURNS=25
export USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-95}"  # Weekly-Gate respektieren
export GOFLAGS=-p=3

WID="${1:-wh1}"
exec bash /opt/development/magic-claude/scripts/dispatcher-worker-real.sh "$WID" "/tmp/work/disp-$WID"
