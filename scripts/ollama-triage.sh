#!/bin/bash
# Local-GPU triage: pre-check card tickets for missing shapes/primitives BEFORE
# spending Claude tokens. Single-shot /api/chat per card — NO agentic loop, NO
# Claude-CLI harness on this host (that combination leaked memory, 2026-07;
# see HANDOFF.md). Read-only: never claims tickets, never mutates the DB.
#
# Verdict contract (one per card, strict lines):
#   VERDICT: BUILDABLE | MISSING_SHAPE: <kebab> | MISSING_PRIMITIVE: <kebab> | UNSURE
#   WHY: <1-2 sentences>
#   EVIDENCE: <exact catalog entries checked / closest matches>
# UNSURE (or any malformed output) => requeue for Sonnet, verdict discarded.
# A MISSING_* verdict is NEVER terminal: it must be confirmed by a (batched)
# Sonnet pass; the EVIDENCE line travels into the park/primitive ticket as
#   LOCAL-TRIAGE: <verdict> | <evidence>
# so Sonnet prechecks the local claim first.
#
# Memory-leak prevention (this host):
#   - hard virtual-memory cap on the whole script (ulimit -Sv, default 2 GB)
#   - stateless curl per card, --max-time + --connect-timeout, stream:false
#   - num_predict caps generation; response size checked after write
#   - nothing persists between cards; one flat report file
#
# Usage: ollama-triage.sh "Card Name" ["Card Name" ...]
set -uo pipefail
ulimit -Sv "${MEM_KB:-2097152}"   # 2 GB virtual memory cap for this script tree

# Global kill switch: touch magic-ops/LOCAL_GPU_OFF to silence the GPU box
# (home-office mode). Every local-GPU lane honors this file.
OFF_FILE="$(cd "$(dirname "$0")/.." && pwd)/LOCAL_GPU_OFF"
[ -f "$OFF_FILE" ] && { echo "local GPU disabled ($OFF_FILE exists) — skipping"; exit 0; }

OLLAMA="${OLLAMA:-http://192.168.1.15:11434}"
MODEL="${MODEL:-qwen3-coder:30b}"
NUM_CTX="${NUM_CTX:-32768}"       # fits 24 GB card next to the Q4 weights; do NOT raise past 49152
NUM_PREDICT="${NUM_PREDICT:-400}"
THINK="${THINK:-false}"           # true: allow chain-of-thought — raise NUM_PREDICT to 3000+, thinking tokens count against it
PRESENCE_PENALTY="${PRESENCE_PENALTY:-0}"  # >0 curbs circular thinking loops in small thinkers
# Qwen 3.5/3.6 official guidance: NEVER greedy-decode (endless repetition);
# thinking/precise: temp 0.6 top_p 0.95 top_k 20; loop-prone small thinkers: presence 1.5
TEMP="${TEMP:-0.6}"
TOP_P="${TOP_P:-0.95}"
TOP_K="${TOP_K:-20}"
MAX_TIME="${MAX_TIME:-600}"
REPO="${REPO:-/opt/development/test/openmagic}"
OPS="$(cd "$(dirname "$0")/.." && pwd)"
STAMP=$(date +%Y-%m-%d-%H%M)
REPORT="${REPORT:-$OPS/reports/ollama-triage-$STAMP.md}"
WORK=$(mktemp -d /tmp/ollama-triage.XXXXXX); trap 'rm -rf "$WORK"' EXIT

[ $# -ge 1 ] || { echo "usage: $0 \"Card Name\" [...]" >&2; exit 2; }
curl -sf --connect-timeout 5 --max-time 10 "$OLLAMA/api/tags" >/dev/null \
  || { echo "FATAL: Ollama at $OLLAMA unreachable" >&2; exit 3; }

# ---- static prompt prefix: shape catalog + signature-only primitive index ----
{
  echo "=== SHAPE CATALOG (record-tier vocabulary) ==="
  cat "$REPO/scripts/skills/shape-catalog.md"
  echo ""
  echo "=== PRIMITIVE SIGNATURE INDEX (handler-tier vocabulary; signatures only) ==="
  python3 "$OPS/scripts/concise-catalog.py" "$REPO/scripts/skills/primitive-catalog.md" \
    | sed -E 's/^(- `[^`]+`).*/\1/' | grep -E '^(##|- `)'
  echo ""
  cat <<'INSTR'
=== YOUR JOB: TRIAGE ONE CARD (do NOT implement anything) ===
Question: can this card's rules text be implemented with the vocabulary above?
 - Record tier: every ability is a known SHAPE (trigger x effect from the shape catalog).
 - Handler tier: Go code composed ONLY from primitives in the signature index.
Decide which single verdict fits:
 - BUILDABLE            all abilities expressible (record or handler tier)
 - MISSING_SHAPE: <x>   record-shaped card, but one ability needs a shape not in the catalog
 - MISSING_PRIMITIVE: <x>  no combination of listed primitives can express some ability
 - UNSURE               anything else
HARD RULES:
1. IF YOU ARE UNSURE IN ANY WAY, ANSWER "VERDICT: UNSURE". The ticket is then
   simply requeued for Sonnet — that is the correct, cheap outcome. A wrong
   MISSING_* verdict is the expensive error: it can park a buildable card.
   Never guess "missing" to be safe; UNSURE is the safe answer.
2. Before any MISSING_* verdict, name in EVIDENCE the closest existing
   catalog entries you checked and why each one falls short. This evidence is
   attached to the ticket so a stronger model can precheck your claim first.
3. Output EXACTLY these lines, nothing else, no markdown (TIER only when BUILDABLE):
VERDICT: <BUILDABLE | MISSING_SHAPE: kebab-name | MISSING_PRIMITIVE: kebab-name | UNSURE>
TIER: <record if EVERY ability maps to a shape-catalog trigger x effect; handler otherwise>
WHY: <1-2 sentences>
EVIDENCE: <ONLY the closest candidate shapes/primitives (max 8, comma-separated), each with a word on why it falls short — never dump the whole vocabulary>
INSTR
} > "$WORK/prefix.txt"

# full catalogs for the deterministic grep-refute of MISSING_* claims
# (the mandatory-grep rule, enforced by the script since the model can't grep)
{ python3 "$OPS/scripts/concise-catalog.py" "$REPO/scripts/skills/primitive-catalog.md"
  cat "$REPO/scripts/skills/shape-catalog.md"; } > "$WORK/full-catalog.md"

{
  echo "# Ollama triage — $STAMP"
  echo ""
  echo "model: \`$MODEL\` @ $OLLAMA · num_ctx=$NUM_CTX · num_predict=$NUM_PREDICT · single-shot, read-only"
  echo ""
} > "$REPORT"

for CARD in "$@"; do
  # card record (name/type/text) from the committed DB — python keeps memory flat
  CARDBLOCK=$(python3 - "$CARD" <<'PY'
import json,sys,glob
name=sys.argv[1]
for f in glob.glob('/opt/development/test/openmagic/backend/data/carddb/[a-z0].json'):
    d=json.load(open(f))
    if name in d:
        c=d[name]
        print(f"NAME: {c['name']}\nTYPE: {c.get('type','')} {'/'.join(c.get('sub_types',[]))}\nKEYWORDS: {', '.join(c.get('keywords',[]))}\nTEXT: {c.get('text','')}")
        sys.exit(0)
sys.exit(1)
PY
) || { echo "## $CARD" >> "$REPORT"; echo "NOT FOUND in carddb — skipped" >> "$REPORT"; continue; }

  cat "$WORK/prefix.txt" > "$WORK/prompt.txt"
  printf '\n=== THE CARD ===\n%s\n' "$CARDBLOCK" >> "$WORK/prompt.txt"

  python3 - "$WORK/prompt.txt" "$MODEL" "$NUM_CTX" "$NUM_PREDICT" "$THINK" "$PRESENCE_PENALTY" "$TEMP" "$TOP_P" "$TOP_K" > "$WORK/req.json" <<'PY'
import json,sys
prompt=open(sys.argv[1]).read()
# think defaults to false — thinking models (gemma4) otherwise burn the whole
# num_predict budget on chain-of-thought and return empty content
print(json.dumps({"model":sys.argv[2],"stream":False,"think":sys.argv[5]=='true',
  "options":{"num_ctx":int(sys.argv[3]),"num_predict":int(sys.argv[4]),
             "temperature":float(sys.argv[7]),"top_p":float(sys.argv[8]),
             "top_k":int(sys.argv[9]),"presence_penalty":float(sys.argv[6])},
  "messages":[{"role":"user","content":prompt}]}))
PY

  T0=$(date +%s)
  HTTP=$(curl -s --connect-timeout 5 --max-time "$MAX_TIME" \
    -o "$WORK/resp.json" -w '%{http_code}' \
    -H 'Content-Type: application/json' -d @"$WORK/req.json" \
    "$OLLAMA/api/chat") || HTTP=000
  T1=$(date +%s); DUR=$((T1-T0))

  {
    echo "## $CARD"
    if [ "$HTTP" != "200" ] || [ ! -s "$WORK/resp.json" ] || [ "$(stat -c%s "$WORK/resp.json")" -gt 1048576 ]; then
      echo "- verdict: **UNSURE** (transport: http=$HTTP, ${DUR}s) → requeue for Sonnet"
    else
      python3 - "$WORK/resp.json" "$DUR" "$WORK/full-catalog.md" "$CARD" "${REPORT_JSONL:-}" <<'PY'
import json,sys,re
d=json.load(open(sys.argv[1])); dur=sys.argv[2]
card=sys.argv[4]; jsonl=sys.argv[5]
catalog=open(sys.argv[3]).read().lower()
out=d.get('message',{}).get('content','').strip()
pt=d.get('prompt_eval_count','?'); ct=d.get('eval_count','?')
m=re.search(r'^VERDICT:\s*(BUILDABLE|MISSING_SHAPE:\s*[\w-]+|MISSING_PRIMITIVE:\s*[\w-]+|UNSURE)\s*$',out,re.M)
why=re.search(r'^WHY:\s*(.+)$',out,re.M); ev=re.search(r'^EVIDENCE:\s*(.+)$',out,re.M)

STOP={'the','a','an','of','to','with','and','or','this','that','by','for','on','in','cant','cannot'}
def grep_refute(kebab):
    # measured on 20-card backtest 2026-07-27: killed 3/10 false-MISSING claims,
    # incl. two where the model named an EXISTING primitive as missing
    words=[w for w in kebab.lower().split('-') if w not in STOP]
    squash=''.join(words)
    if squash and squash in catalog.replace('_','').replace(' ',''):
        return f"exact-name match for '{squash}'"
    for ln in catalog.split('\n'):
        if words and all(w in ln for w in words):
            return f"all claim words on one line: {ln.strip()[:90]}"
    return None

tier=re.search(r'^TIER:\s*(record|handler)\s*$',out,re.M)
rec={"card":card,"verdict":"UNSURE","tier":None,"why":None,"evidence":None,"refuted":None}
if not m:
    print(f"- verdict: **UNSURE** (malformed output) → requeue for Sonnet\n- raw: `{out[:200]}`")
else:
    v=re.sub(r'\s+',' ',m.group(1))
    rec["why"]=why.group(1) if why else None
    rec["evidence"]=ev.group(1) if ev else None
    rec["tier"]=tier.group(1) if tier else None
    refuted=None
    if v.startswith('MISSING'):
        refuted=grep_refute(v.partition(':')[2].strip())
    if refuted:
        rec["refuted"]=refuted; rec["claimed"]=v
        print(f"- verdict: **UNSURE** — model claimed `{v}` but catalog grep refutes it ({refuted}) → requeue for Sonnet")
        print(f"- ticket annotation: `LOCAL-TRIAGE: refuted {v} | {refuted}`")
    else:
        rec["verdict"]=v
        print(f"- verdict: **{v}**{' [tier: '+tier.group(1)+']' if tier else ''} ({dur}s, prompt {pt} tok, out {ct} tok)")
        if why: print(f"- why: {why.group(1)}")
        if ev:  print(f"- evidence: {ev.group(1)}")
        if v.startswith('MISSING'):
            print(f"- ticket annotation: `LOCAL-TRIAGE: {v} | {ev.group(1) if ev else 'no evidence'}`")
            print(f"- NOT terminal: batch-confirm with Sonnet before parking")
        elif v=='UNSURE':
            print(f"- → requeue for Sonnet (by design)")
if jsonl:
    with open(jsonl,'a') as f: f.write(json.dumps(rec)+'\n')
PY
    fi
    echo ""
  } >> "$REPORT"
  echo "[$CARD] done ($DUR s)"
done
echo "report: $REPORT"
