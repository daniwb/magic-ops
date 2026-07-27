#!/bin/bash
# Stream 4: local record GENERATION for record-shaped tickets (tagged by
# local-triage-queue.sh / sidecar tier='record'). The local model writes the
# AbilityDSL JSON; it is applied via recordedit in a SCRATCH CLONE and gated by
# the record linter + shape tests. GREEN -> candidate file for Sonnet/human
# review in $OPS/record-candidates/pending/. NOTHING is committed to main and
# no ticket state changes — the candidate is a head start, not a merge.
# Honors LOCAL_GPU_OFF. Usage: local-record-builder.sh [N] (default 5)
set -uo pipefail
OPS="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$OPS/LOCAL_GPU_OFF" ] && { echo "local GPU disabled — skipping"; exit 0; }
DB="${DB:-/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db}"
REPO="${REPO:-/opt/development/test/openmagic}"
OLLAMA="${OLLAMA:-http://192.168.1.15:11434}"
MODEL="${MODEL:-qwen3.6:27b}"
GO="${GO:-/usr/local/go/bin/go}"
N="${1:-5}"
CLONE="${CLONE:-/tmp/work/record-builder}"
PEND="$OPS/record-candidates/pending"; FAILED="$OPS/record-candidates/failed"
mkdir -p "$PEND" "$FAILED"
mark_failed(){ echo "{\"ticket\":$1,\"card\":\"$2\",\"reason\":\"$3\"}" > "$FAILED/ticket-$1.json"; }
RUN=$(mktemp -d /tmp/record-builder.XXXXXX); trap 'rm -rf "$RUN"' EXIT
ulimit -Sv 4194304

# --- scratch clone (reset to live repo state each run) -----------------------
if [ ! -d "$CLONE/.git" ]; then mkdir -p "$(dirname "$CLONE")"; git clone -q "$REPO" "$CLONE"; fi
git -C "$CLONE" fetch -q origin 2>/dev/null || true
git -C "$CLONE" checkout -qB main && git -C "$CLONE" reset -q --hard origin/main 2>/dev/null \
  || git -C "$CLONE" reset -q --hard HEAD
git -C "$CLONE" clean -qfd

# --- candidates: record-tier verdicts without a pending/failed candidate -----
python3 - "$DB" "$N" "$PEND" > "$RUN/batch.tsv" <<'PY'
import sqlite3, sys, re, os, json, glob
db = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)
carddb = {}
for f in glob.glob('/opt/development/test/openmagic/backend/data/carddb/[a-z0].json'):
    carddb.update(json.load(open(f)))
done = {fn.split('ticket-')[1].split('.')[0] for fn in os.listdir(sys.argv[3])} if os.path.isdir(sys.argv[3]) else set()
failed_dir = os.path.join(os.path.dirname(sys.argv[3]), 'failed')
if os.path.isdir(failed_dir):
    done |= {fn.split('ticket-')[1].split('.')[0] for fn in os.listdir(failed_dir)}
n = int(sys.argv[2]); out = 0
for tid, tier, verdict in db.execute("select ticket_id,tier,verdict from local_triage where tier='record' and verdict='BUILDABLE'"):
    if out >= n: break
    if str(tid) in done: continue
    row = db.execute("select title,state from tickets where id=?", (tid,)).fetchone()
    if not row or row[1] != 'todo': continue
    m = re.match(r'^(?:DSL-RECORD: )?DSL: \[[A-Z0-9]{2,4}\] (.+?) —', row[0]) or \
        re.match(r'^(?:DSL-RECORD: )?DSL-SPLIT: (.+?) \(from', row[0])
    if m and m.group(1).strip() in carddb:
        print(f"{tid}\t{m.group(1).strip()}")
        out += 1
PY
[ -s "$RUN/batch.tsv" ] || { echo "no record candidates queued"; exit 0; }

while IFS=$'\t' read -r TID CARD; do
  [ -f "$OPS/LOCAL_GPU_OFF" ] && { echo "kill switch raised mid-run — stopping"; break; }
  echo "Record-Build: $CARD (#$TID)" > /tmp/local-lanes-status
  # --- prompt: shape catalog + live example records + the card ---------------
  python3 - "$CARD" > "$RUN/prompt.txt" <<'PY'
import json, sys, glob
card = sys.argv[1]
carddb = {}
for f in glob.glob('/opt/development/test/openmagic/backend/data/carddb/[a-z0].json'):
    carddb.update(json.load(open(f)))
c = carddb[card]
print(open('/opt/development/test/openmagic/scripts/skills/shape-catalog.md').read())
print("\n=== LIVE EXAMPLE RECORDS (verified/manual, your value-key reference) ===")
shown = 0
for name, r in carddb.items():
    if r.get('status') in ('manual','verified') and r.get('abilities'):
        print(json.dumps({"name": name, "abilities": r['abilities']}))
        shown += 1
        if shown >= 6: break
print("""
=== YOUR JOB ===
Write the AbilityDSL "abilities" JSON array for THE CARD below, using ONLY
triggers/effects from the shape catalog and value-keys as seen in the example
records. Printed keywords (Flying, ...) are NOT abilities — omit them.
Output ONLY the JSON array on one line, no markdown, no commentary.
If any ability cannot be expressed as a catalog shape, OR the card text
contains a keyword mechanic outside the plain keyword list (toxic, protection,
ward, crew, ...), output exactly: CANNOT
=== THE CARD ===""")
print(f"NAME: {c['name']}\nTYPE: {c.get('type','')}\nKEYWORDS: {', '.join(c.get('keywords',[]))}\nTEXT: {c.get('text','')}")
PY
  python3 - "$RUN/prompt.txt" "$MODEL" <<'PY' > "$RUN/req.json"
import json, sys
print(json.dumps({"model": sys.argv[2], "stream": False, "think": True,
  "options": {"num_ctx": 16384, "num_predict": 6000, "temperature": 0.6,
              "top_p": 0.95, "top_k": 20},
  "messages": [{"role": "user", "content": open(sys.argv[1]).read()}]}))
PY
  curl -s --connect-timeout 5 --max-time 600 -H 'Content-Type: application/json' \
    -d @"$RUN/req.json" "$OLLAMA/api/chat" > "$RUN/resp.json" || { echo "#$TID $CARD: transport fail"; continue; }
  ABIL=$(python3 -c "
import json,sys,re
d=json.load(open('$RUN/resp.json'))
c=d['message'].get('content','').strip()
m=re.search(r'\[.*\]', c, re.S)
print(m.group(0).replace(chr(10),' ') if m and c!='CANNOT' else '')")
  if [ -z "$ABIL" ]; then echo "#$TID $CARD: model declined/no JSON"; mark_failed "$TID" "$CARD" "declined"; continue; fi
  # --- gate: recordedit + linter + shape tests in the scratch clone ----------
  if ! (cd "$CLONE/backend" && timeout 120 "$GO" run ./tools/recordedit \
        -name "$CARD" -abilities "$ABIL" -notes "LOCAL CANDIDATE ticket #$TID — NOT reviewed" >/dev/null 2>&1); then
    echo "#$TID $CARD: recordedit rejected"; mark_failed "$TID" "$CARD" "recordedit"; continue
  fi
  if (cd "$CLONE/backend" && timeout 600 "$GO" test ./cards/ -run 'TestCardDBLint|TestShape_' -count=1 >/dev/null 2>&1); then
    python3 - "$TID" "$CARD" "$ABIL" "$PEND" "$MODEL" <<'PY'
import json, sys
tid, card, abil, pend, model = sys.argv[1:6]
json.dump({"ticket": int(tid), "card": card, "model": model,
           "abilities": json.loads(abil),
           "apply": f"cd backend && go run ./tools/recordedit -name {card!r} -abilities {abil!r} -notes 'ticket #{tid} (local candidate, reviewed)'",
           "status": "pending-review"},
          open(f"{pend}/ticket-{tid}.json", "w"), indent=1)
PY
    echo "#$TID $CARD: GREEN — candidate filed"
  else
    echo "#$TID $CARD: linter/shape-test RED — discarded"; mark_failed "$TID" "$CARD" "linter-red"
  fi
  git -C "$CLONE" checkout -q -- backend/data/carddb 2>/dev/null || true
done < "$RUN/batch.tsv"
echo "pending candidates: $(ls "$PEND" 2>/dev/null | wc -l) in $PEND"
