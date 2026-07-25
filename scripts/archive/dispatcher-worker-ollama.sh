#!/bin/bash
# w3 = Ollama-Cloud-Worker (glm-5.2:cloud) für den Dispatcher — separate Quota,
# läuft ungebremst während die Sonnet-Worker usage-gated sind.
#
# READINESS-PROBE statt Timer: die Quota kommt "irgendwann" zurück (User: ~4h).
# Blind starten hängt den Worker (Vorfall 2026-07-13 03:00) — deshalb alle 20 min
# ein Mini-Testcall; erst wenn der antwortet, startet die Arbeitsschleife.
set -uo pipefail

# Clean-slate, dann Ollama-Routing (Muster aus .w5-glm-launch.sh)
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_API_KEY
export GLM_WORKER=1
export ANTHROPIC_BASE_URL=http://127.0.0.1:11434
export ANTHROPIC_AUTH_TOKEN=ollama
# Zwei-Stufen wie Haiku→Sonnet: flash (Medium Usage) für jeden Erstversuch,
# pro (Extra High Usage!) nur als Eskalation ab Versuch 2
# glm-5.2 einstufig (User-Entscheid 2026-07-20: DeepSeek raus — flash
# eskalierte in 14/18 Faellen zu pro, der Umweg lohnte nicht)
export MODEL_HAIKU="${OLLAMA_MODEL:-glm-5.2:cloud}"
export MODEL_SONNET="${OLLAMA_MODEL:-glm-5.2:cloud}"
export WORKER_MAX_TURNS=40        # Nicht-Claude-Modelle brauchen mehr Turns
export USAGE_LIMIT_PCT=0          # Claude-Subscription-Gate irrelevant für Ollama
export GOFLAGS=-p=3               # Compile-Parallelität deckeln (8 Kerne, 4 Worker)
export CLAUDE_TIMEOUT=1200        # glm-Cloud ist langsamer als Sonnet

CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
PROBE_INTERVAL="${PROBE_INTERVAL:-1200}"  # 20 min

log() { printf '[%s] w3-ollama: %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }

log "warte auf Ollama-Quota (Probe alle $((PROBE_INTERVAL/60)) min, Modell $MODEL_SONNET)…"
until OUT=$(timeout 180 "$CLAUDE_BIN" -p --model "$MODEL_HAIKU" \
        --permission-mode bypassPermissions --max-turns 1 \
        <<< "Reply with exactly: OK" 2>&1) && printf '%s' "$OUT" | grep -q "OK"; do
  log "Quota noch nicht verfügbar ($(printf '%s' "$OUT" | tail -c 120 | tr '\n' ' ')) — nächste Probe in $((PROBE_INTERVAL/60)) min"
  sleep "$PROBE_INTERVAL"
done
log "✅ Ollama antwortet — starte Worker"

exec bash /opt/development/magic-claude/scripts/dispatcher-worker-real.sh w3 /tmp/work/disp-w3
