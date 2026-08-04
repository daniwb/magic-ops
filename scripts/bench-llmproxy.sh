#!/usr/bin/env bash
# bench-llmproxy.sh <model> — measure an llmproxy lane before pointing rl1 at it.
#   1) raw generation speed (tok/s) via /v1/chat/completions
#   2) agentic smoke through the shim (:4102): claude CLI must execute Bash echo LANE-OK
# Usage: bash bench-llmproxy.sh gpt-oss:120b
set -uo pipefail
MODEL="${1:?usage: bench-llmproxy.sh <model>}"
PROXY="${PROXY:-https://llm.k.ezq.ch}"
SHIM="${SHIM:-http://127.0.0.1:4102}"

echo "== 1) raw speed: $MODEL via $PROXY"
START=$(date +%s.%N)
RESP=$(curl -s -m 300 "$PROXY/v1/chat/completions" -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Count from 1 to 100, comma-separated, nothing else.\"}],\"max_tokens\":600}")
END=$(date +%s.%N)
python3 - "$START" "$END" <<EOF
import json, sys
resp = '''$RESP'''
t = float(sys.argv[2]) - float(sys.argv[1])
try:
    d = json.loads(resp)
    u = d.get('usage') or {}
    ct = u.get('completion_tokens', 0)
    if ct:
        print(f'  model={d.get("model")}  wall={t:.1f}s  completion_tokens={ct}  tok/s={ct/t:.1f}')
    else:
        print(f'  no usage in response ({t:.1f}s): {str(d)[:300]}')
except Exception as e:
    print(f'  ERROR {e}: {resp[:300]}')
EOF

echo "== 2) agentic smoke via shim $SHIM (claude CLI, Bash tool)"
OUT=$(ANTHROPIC_BASE_URL="$SHIM" ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY= \
  timeout 600 "$HOME/.local/bin/claude" -p --model "$MODEL" \
  --permission-mode bypassPermissions --max-turns 4 \
  "Run this exact bash command and then reply with its output: echo LANE-OK" 2>&1)
if printf '%s' "$OUT" | grep -q "LANE-OK"; then
  echo "  AGENTIC OK — tool call round-tripped"
else
  echo "  AGENTIC FAIL — output was:"
  printf '%s\n' "$OUT" | tail -5
fi
