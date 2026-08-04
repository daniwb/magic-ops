#!/usr/bin/env bash
# watch-local-ai.sh [worker] [-f] — show the local AI worker's actual
# conversation (claude CLI transcript). Default worker: rl1.
W="${1:-rl1}"; FOLLOW="${2:-}"
DIR="$HOME/.claude/projects/-tmp-work-disp-$W"
F=$(ls -t "$DIR"/*.jsonl 2>/dev/null | head -1)
[ -z "$F" ] && { echo "no transcript for $W ($DIR)"; exit 1; }
echo "== transcript: $F"
render() { python3 -c '
import json,sys
for line in sys.stdin:
    try: d=json.loads(line)
    except Exception: continue
    m=d.get("message") or {}
    role=m.get("role") or d.get("type","?")
    c=m.get("content")
    if isinstance(c,list):
        for b in c:
            t=b.get("type")
            if t=="text": print(f"[{role}] {b.get(\"text\",\"\")[:300]}")
            elif t=="tool_use": print(f"[{role}>TOOL {b.get(\"name\")}] {json.dumps(b.get(\"input\",{}))[:200]}")
            elif t=="tool_result":
                rc=b.get("content"); 
                if isinstance(rc,list): rc=" ".join(x.get("text","") for x in rc if isinstance(x,dict))
                print(f"[tool<] {str(rc)[:200]}")
    elif isinstance(c,str): print(f"[{role}] {c[:300]}")
'; }
if [ "$FOLLOW" = "-f" ]; then tail -n 50 -f "$F" | render; else tail -n 200 "$F" | render; fi
