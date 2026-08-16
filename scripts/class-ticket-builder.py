#!/usr/bin/env python3
"""class-ticket-builder.py — class-level queue source (phase.rs adoption).

Files ranked class-round tickets as state='fable' in dispatcher v4 — the
Fable-session queue (operator sessions claim these; fleet workers never do:
spine/kind class rounds burned 20-50M tokens on fleet models)'s sqlite DB
(no Kanboard dependency), same insert shape the dispatcher's own vocab-filing
path uses (services/dispatcher/v4/main.go:399: type='vocab', state='vocab').

Depth-controlled, not rate-controlled: tops the queue up until TARGET_OPEN
class-round tickets are open, picking the highest-marginal-unlock items from
corpus/build-plan.jsonl that aren't already ticketed (any non-terminal
ticket naming the item counts). The plan reranks nightly (--refresh), so the
queue always holds the CURRENT top classes instead of a frozen snapshot.

  class-ticket-builder.py            # dry-run
  class-ticket-builder.py --commit   # top up to TARGET_OPEN
  class-ticket-builder.py --refresh  # re-run coverage_planner first
"""
import json, os, sqlite3, subprocess, sys, time

REPO = os.environ.get("REPO_DIR", "/opt/development/magic-new")
DB = os.environ.get("DISPATCHER_DB",
                    "/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db")
TARGET_OPEN = int(os.environ.get("TARGET_OPEN", "5"))
MIN_UNLOCK = int(os.environ.get("MIN_UNLOCK", "30"))
COMMIT = "--commit" in sys.argv
TERMINAL = ("done", "dup", "archived-v1", "parked-era1", "superseded")

if "--refresh" in sys.argv:
    subprocess.run(["python3", "scripts/paragraph/coverage_planner.py", "-n", "80"],
                   cwd=REPO, check=False, capture_output=True)

plan = [json.loads(l) for l in open(f"{REPO}/corpus/build-plan.jsonl")]
db = sqlite3.connect(DB, timeout=15)
marks = ",".join("?" for _ in TERMINAL)
open_rows = db.execute(
    f"SELECT title FROM tickets WHERE state NOT IN ({marks})", TERMINAL).fetchall()
open_titles = " | ".join(r[0] for r in open_rows)
open_rounds = sum(1 for r in open_rows if "class round" in r[0])

made = 0
for row in plan:
    if open_rounds + made >= TARGET_OPEN:
        break
    item, unlock = row.get("item", ""), row.get("marginal_unlock", 0)
    if not item or unlock < MIN_UNLOCK or item in open_titles:
        continue
    title = f"REPARSE-ENGINE: {item} — class round (unlock {unlock})"
    descr = f"""CLASS ROUND (class-ticket-builder.py, phase.rs regime).
Item: {item} | marginal unlock: {unlock} review cards
Examples: {', '.join(row.get('examples', [])[:5])}

Build the CLASS, not a card: one primitive/emitter/executor covering the
whole item. Follow the QUALITY GATES in your system prompt (premise from the
carddb record text; EXISTENCE_CHECK 5-grep line BEFORE any new primitive;
honest miss over silently wrong; discriminating test through the real
pipeline). Evidence: corpus/build-plan.jsonl, corpus/primitive-inventory.json,
docs/phase-rs-factory-analysis.md.

DoD: executor+registry+shape test green (go test ./cards/... ./game/...),
reparse.py emitter wired, eligible review cards flipped with a round tag,
honest misses reported with named reasons."""
    if COMMIT:
        now = int(time.time())
        cur = db.execute(
            "INSERT INTO tickets(type,title,descr,mechanic,state,created_at,updated_at)"
            " VALUES('card',?,?,?,'fable',?,?)", (title, descr, item, now, now))
        print(f"CREATED #{cur.lastrowid}: {title}")
    else:
        print(f"WOULD CREATE: {title}")
    made += 1

if COMMIT:
    db.commit()
db.close()
print(f"open_class_rounds_before={open_rounds} {'created' if COMMIT else 'candidates'}={made}")
