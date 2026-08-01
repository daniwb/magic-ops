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

# --- pick untriaged todo tickets (single cards AND bundles) -----------------
# Bundles are 3-card tickets ("DSL-BUNDLE: [tag] A + B + C"). Each card is still
# triaged INDIVIDUALLY (ollama-triage.sh takes N names, one prompt per card) —
# the model is never asked to judge three cards in one context. The per-card
# verdicts are folded into ONE ticket verdict in the apply step below.
# A bundle is only enqueued if ALL its cards resolve in the carddb, so a bad
# name-split can never look like "the rest were fine".
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
def cards_of(title):
    m = re.match(r'^DSL: \[[A-Z0-9]{2,4}\] (.+?) —', title)
    if m: return [m.group(1).strip()]
    m = re.match(r'^DSL-SPLIT: (.+?) \(from', title)
    if m: return [m.group(1).strip()]
    m = re.match(r'^DSL-BUNDLE: \[[^\]]+\] (.+)$', title)
    if m: return [c.strip() for c in m.group(1).split(' + ') if c.strip()]
    return []  # vocabs/already-tagged are skipped
n = int(sys.argv[2]); out = 0
for tid, title in db.execute(
        "select id,title from tickets where type='card' and state='todo' "
        "and title not like 'DSL-RECORD%' order by priority desc, id"):
    if out >= n: break
    if tid in have: continue
    cards = cards_of(title)
    # all-or-nothing: a partially resolvable bundle is skipped, not half-triaged
    if cards and all(c in carddb for c in cards):
        print("\t".join([str(tid)] + cards))
        out += 1
PY
[ -s "$RUN_DIR/batch.tsv" ] || { echo "nothing to triage"; exit 0; }

# --- triage each card (single-shot, jsonl sidecar) ---------------------------
while IFS=$'\t' read -r TID CARDS_LINE; do
  [ -f "$OPS/LOCAL_GPU_OFF" ] && { echo "kill switch raised mid-run — stopping"; break; }
  IFS=$'\t' read -r -a CARDS <<< "$CARDS_LINE"
  [ "${#CARDS[@]}" -ge 1 ] || continue
  if [ "${#CARDS[@]}" -gt 1 ]; then
    echo "Triage: ${#CARDS[@]} Karten (#$TID) — ${CARDS[0]} …" > /tmp/local-lanes-status
  else
    echo "Triage: ${CARDS[0]} (#$TID)" > /tmp/local-lanes-status
  fi
  # one prompt per card inside ollama-triage.sh; one jsonl line per card back
  REPORT="$RUN_DIR/report-$TID.md" REPORT_JSONL="$RUN_DIR/verdicts.jsonl" \
    TID="$TID" "$OPS/scripts/ollama-triage.sh" "${CARDS[@]}" >/dev/null 2>&1
  # tag this ticket's jsonl lines with the ticket id (triage only knows names)
  python3 - "$RUN_DIR/verdicts.jsonl" "$TID" "${CARDS[@]}" <<'PY'
import json,sys,os
p,tid,cards=sys.argv[1],int(sys.argv[2]),set(sys.argv[3:])
lines=[json.loads(l) for l in open(p)] if os.path.exists(p) else []
for l in lines:
    if l.get('card') in cards and 'ticket' not in l: l['ticket']=tid
open(p,'w').write('\n'.join(json.dumps(l) for l in lines)+'\n')
PY
  echo "triaged #$TID ${CARDS[*]}"
done < "$RUN_DIR/batch.tsv"
[ -f "$RUN_DIR/verdicts.jsonl" ] || { echo "no verdicts produced"; exit 0; }

# --- apply: sidecar always; descr/title only for actionable verdicts ---------
python3 - "$DB" "$RUN_DIR/verdicts.jsonl" "$MODEL" "$RUN_DIR/batch.tsv" <<'PY'
import sqlite3, sys, json, time, os
from collections import defaultdict
db = sqlite3.connect(sys.argv[1], timeout=15)
db.execute("PRAGMA busy_timeout=10000")
db.execute("""create table if not exists local_triage(
  ticket_id integer primary key, ts integer, model text,
  verdict text, tier text, evidence text)""")
now = int(time.time()); model = sys.argv[3]

# expected card count per ticket — a bundle that lost a card mid-run (transport
# error, NOT FOUND) must never be folded into a clean "all BUILDABLE"
expected = {}
if os.path.exists(sys.argv[4]):
    for ln in open(sys.argv[4]):
        parts = ln.rstrip('\n').split('\t')
        if len(parts) >= 2: expected[int(parts[0])] = len(parts) - 1

groups = defaultdict(list)
for line in open(sys.argv[2]):
    r = json.loads(line)
    if r.get('ticket'): groups[r['ticket']].append(r)

def fold(recs, exp):
    """N per-card verdicts -> one ticket verdict. Pessimistic on purpose: a
    bundle is only as buildable as its weakest card, and the blocker is named
    so the Sonnet worker knows which of the three will park."""
    multi = exp > 1
    def ev(rs): return '; '.join(
        f"{r['card']}: {r.get('evidence') or r.get('why') or 'no evidence'}" for r in rs)
    if len(recs) != exp:                       # missing verdicts -> never claim buildable
        return 'UNSURE', None, f"incomplete triage ({len(recs)}/{exp} Karten)", multi
    missing = [r for r in recs if r['verdict'].startswith('MISSING')]
    if missing:
        return missing[0]['verdict'], None, ev(missing), multi
    unsure = [r for r in recs if r['verdict'] == 'UNSURE']
    if unsure:
        return 'UNSURE', None, ev(unsure), multi
    tiers = {r.get('tier') for r in recs}
    return 'BUILDABLE', ('record' if tiers == {'record'} else 'handler'), ev(recs), multi

tagged = hinted = other = 0
for tid, recs in groups.items():
    exp = expected.get(tid, len(recs))
    verdict, tier, evidence, multi = fold(recs, exp)
    db.execute("insert or replace into local_triage values(?,?,?,?,?,?)",
               (tid, now, model, verdict, tier, evidence))
    # record-tier routing is a SINGLE-card mechanism: local-record-builder.sh only
    # matches 'DSL:'/'DSL-SPLIT:' titles, so tagging a bundle would just pollute it
    if verdict == 'BUILDABLE' and tier == 'record' and not multi:
        db.execute("update tickets set title='DSL-RECORD: '||title, updated_at=? "
                   "where id=? and title not like 'DSL-RECORD%'", (now, tid))
        db.execute("insert into events(ticket_id,ts,msg) values(?,?,?)",
                   (tid, now, f"local triage ({model}): record-shaped — tagged DSL-RECORD"))
        tagged += 1
    elif verdict.startswith('MISSING'):
        descr = db.execute("select descr from tickets where id=?", (tid,)).fetchone()[0]
        scope = f" [{exp}-Karten-Bundle, Blocker benannt]" if multi else ""
        note = (f"LOCAL-TRIAGE hint ({model}, ~70% precision — PRECHECK before parking)"
                f"{scope}: {verdict} | {evidence or 'no evidence'}")
        if 'LOCAL-TRIAGE hint' not in descr:
            db.execute("update tickets set descr=?, updated_at=? where id=?",
                       (descr + "\n\n---\n" + note, now, tid))
        db.execute("insert into events(ticket_id,ts,msg) values(?,?,?)",
                   (tid, now, f"local triage ({model}): {verdict} (hint only)"))
        hinted += 1
    else:
        other += 1
db.commit()
print(f"applied: {tagged} DSL-RECORD tags, {hinted} MISSING hints, {other} unsure/handler (sidecar only)")
PY
