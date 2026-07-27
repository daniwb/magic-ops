#!/bin/bash
# Streams 2+3 of the local-GPU plan (reports/ollama-triage-summary-2026-07-27.md):
# annotate todo card tickets with local triage verdicts.
#   - BUILDABLE tier=record  -> 'DSL-RECORD: ' title prefix (cheap-lane routing
#     hook; worker STEP 0 catches a mis-tag, it just tries record first)
#   - MISSING_* (grep-surviving) -> LOCAL-TRIAGE note in descr + events row.
#     NEVER parks — Sonnet prechecks the hint when it works the ticket.
#   - UNSURE / refuted -> sidecar record only (ticket untouched)
# Sidecar table local_triage(ticket_id PK, ...) makes runs idempotent.
# Honors the LOCAL_GPU_OFF kill switch (home-office mode).
# Usage: local-triage-queue.sh [N]   (default 10 tickets per run)
set -uo pipefail
OPS="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$OPS/LOCAL_GPU_OFF" ] && { echo "local GPU disabled — skipping"; exit 0; }
DB="${DB:-/opt/development/magic-claude/services/dispatcher/v4/dispatcher.db}"
N="${1:-10}"
MODEL="${MODEL:-qwen3.6:27b}"
export MODEL THINK="${THINK:-true}" NUM_PREDICT="${NUM_PREDICT:-6000}" MAX_TIME="${MAX_TIME:-900}"
RUN_DIR=$(mktemp -d /tmp/local-triage.XXXXXX); trap 'rm -rf "$RUN_DIR"' EXIT

# --- pick untriaged single-card todo tickets, extract card names -------------
python3 - "$DB" "$N" > "$RUN_DIR/batch.tsv" <<'PY'
import sqlite3, sys, re, json, glob
db = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)
db.execute("select 1")  # fail fast if unreadable
have = set()
try:
    have = {r[0] for r in db.execute("select ticket_id from local_triage")}
except sqlite3.OperationalError:
    pass  # table created on first write
carddb = {}
for f in glob.glob('/opt/development/test/openmagic/backend/data/carddb/[a-z0].json'):
    carddb.update(json.load(open(f)))
def card_of(title):
    m = re.match(r'^DSL: \[[A-Z0-9]{2,4}\] (.+?) —', title)
    if m: return m.group(1).strip()
    m = re.match(r'^DSL-SPLIT: (.+?) \(from', title)
    if m: return m.group(1).strip()
    return None  # bundles/vocabs/already-tagged are skipped
n = int(sys.argv[2]); out = 0
for tid, title in db.execute(
        "select id,title from tickets where type='card' and state='todo' "
        "and title not like 'DSL-RECORD%' order by priority desc, id"):
    if out >= n: break
    if tid in have: continue
    card = card_of(title)
    if card and card in carddb:
        print(f"{tid}\t{card}")
        out += 1
PY
[ -s "$RUN_DIR/batch.tsv" ] || { echo "nothing to triage"; exit 0; }

# --- triage each card (single-shot, jsonl sidecar) ---------------------------
while IFS=$'\t' read -r TID CARD; do
  [ -f "$OPS/LOCAL_GPU_OFF" ] && { echo "kill switch raised mid-run — stopping"; break; }
  REPORT="$RUN_DIR/report-$TID.md" REPORT_JSONL="$RUN_DIR/verdicts.jsonl" \
    TID="$TID" "$OPS/scripts/ollama-triage.sh" "$CARD" >/dev/null 2>&1
  # tag the jsonl line with the ticket id (triage only knows the card name)
  python3 - "$RUN_DIR/verdicts.jsonl" "$TID" "$CARD" <<'PY'
import json,sys
p,tid,card=sys.argv[1],int(sys.argv[2]),sys.argv[3]
lines=[json.loads(l) for l in open(p)] if __import__('os').path.exists(p) else []
for l in lines:
    if l.get('card')==card and 'ticket' not in l: l['ticket']=tid
open(p,'w').write('\n'.join(json.dumps(l) for l in lines)+'\n')
PY
  echo "triaged #$TID $CARD"
done < "$RUN_DIR/batch.tsv"
[ -f "$RUN_DIR/verdicts.jsonl" ] || { echo "no verdicts produced"; exit 0; }

# --- apply: sidecar always; descr/title only for actionable verdicts ---------
python3 - "$DB" "$RUN_DIR/verdicts.jsonl" "$MODEL" <<'PY'
import sqlite3, sys, json, time
db = sqlite3.connect(sys.argv[1], timeout=15)
db.execute("PRAGMA busy_timeout=10000")
db.execute("""create table if not exists local_triage(
  ticket_id integer primary key, ts integer, model text,
  verdict text, tier text, evidence text)""")
now = int(time.time()); model = sys.argv[3]
tagged = hinted = other = 0
for line in open(sys.argv[2]):
    r = json.loads(line)
    tid = r.get('ticket')
    if not tid: continue
    db.execute("insert or replace into local_triage values(?,?,?,?,?,?)",
               (tid, now, model, r['verdict'], r.get('tier'), r.get('evidence')))
    if r['verdict'] == 'BUILDABLE' and r.get('tier') == 'record':
        db.execute("update tickets set title='DSL-RECORD: '||title, updated_at=? "
                   "where id=? and title not like 'DSL-RECORD%'", (now, tid))
        db.execute("insert into events(ticket_id,ts,msg) values(?,?,?)",
                   (tid, now, f"local triage ({model}): record-shaped — tagged DSL-RECORD"))
        tagged += 1
    elif r['verdict'].startswith('MISSING'):
        descr = db.execute("select descr from tickets where id=?", (tid,)).fetchone()[0]
        note = f"LOCAL-TRIAGE hint ({model}, ~70% precision — PRECHECK before parking): {r['verdict']} | {r.get('evidence') or 'no evidence'}"
        if 'LOCAL-TRIAGE hint' not in descr:
            db.execute("update tickets set descr=?, updated_at=? where id=?",
                       (descr + "\n\n---\n" + note, now, tid))
        db.execute("insert into events(ticket_id,ts,msg) values(?,?,?)",
                   (tid, now, f"local triage ({model}): {r['verdict']} (hint only)"))
        hinted += 1
    else:
        other += 1
db.commit()
print(f"applied: {tagged} DSL-RECORD tags, {hinted} MISSING hints, {other} unsure/handler (sidecar only)")
PY
