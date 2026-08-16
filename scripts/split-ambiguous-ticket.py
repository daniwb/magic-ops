#!/usr/bin/env python3
"""Split known heterogeneous map slices without losing their residual tail.

Dry-run by default.  ``--commit`` creates high-confidence children as todo,
keeps uncertain residual children in wait, and marks the parent superseded.
Every reconstructed miss is assigned to exactly one child.
"""
import argparse
import collections
import glob
import json
import os
import re
import sqlite3
import sys
import time

OPS = "/opt/development/magic-ops"
REPO = os.environ.get("REPO_DIR", "/opt/development/test/openmagic")
DB = os.environ.get("DISPATCHER_DB", f"{OPS}/services/dispatcher/v4/dispatcher.db")
sys.path.insert(0, f"{REPO}/scripts/paragraph")
import reparse as R  # noqa: E402
from gen_fleet_tasks import signature  # noqa: E402


def damage_group(detail):
    d = detail.lower()
    if re.search(r"~ deals \d+ damage to", d):
        return "fixed_numeric_damage", True
    if "equal to the number of nonbasic lands" in d:
        return "damage_count_nonbasic_lands", True
    if "equal to the number of lands" in d:
        return "damage_count_lands", True
    if "tapped this way" in d:
        return "damage_count_tapped_this_way", True
    return "damage_dynamic_residual", False


def conditional_group(detail):
    d = detail.lower()
    consequence = d.split(",", 1)[1].strip() if "," in d else d
    if re.search(r"\benter(?:s)? tapped\b", consequence):
        return "conditional_enters_tapped", True
    if re.search(r"\benter(?:s)? untapped\b", consequence):
        return "conditional_enters_untapped", True
    if "must be blocked" in consequence:
        return "conditional_must_be_blocked", True
    if "can't attack unless" in consequence or "cannot attack unless" in consequence:
        return "conditional_attack_tax", True
    if "can't attack" in consequence or "cannot attack" in consequence:
        return "conditional_cannot_attack", True
    if "can't block unless" in consequence or "cannot block unless" in consequence:
        return "conditional_block_tax", True
    if "can't block" in consequence or "cannot block" in consequence:
        return "conditional_cannot_block", True
    return "conditional_residual", False


def ticket_contract(row):
    kind = re.search(r"\*\*Miss shape:\*\* `([^`]+)`", row["descr"])
    family = re.search(r'^### template family "([^"]+)"', row["descr"], re.M)
    if not kind or not family:
        raise ValueError("ticket lacks machine-reconstructable miss shape/template family")
    return kind.group(1), family.group(1)


def load_population(contracts):
    wanted = {(kind, family) for kind, family in contracts.values()}
    found = collections.defaultdict(list)
    for path in sorted(glob.glob(os.path.join(R.CARDDB, "*.json"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            cards = json.load(open(path))
        except Exception:
            continue
        for name, card in cards.items():
            if not isinstance(card, dict) or card.get("status") != "review":
                continue
            for kind, detail in R.reparse_card(card)["misses"]:
                key = (kind, signature(detail))
                if key in wanted:
                    found[key].append((name, str(detail).strip()))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickets", type=int, nargs="+")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    rows = {}
    contracts = {}
    for tid in args.tickets:
        row = db.execute("select * from tickets where id=?", (tid,)).fetchone()
        if not row:
            raise SystemExit(f"ticket #{tid} not found")
        if row["state"] not in ("wait", "superseded"):
            raise SystemExit(f"ticket #{tid} state is {row['state']}, expected wait/superseded")
        rows[tid] = row
        contracts[tid] = ticket_contract(row)
    populations = load_population(contracts)
    proposals = {}
    for tid, (kind, family) in contracts.items():
        members = populations[(kind, family)]
        classifier = damage_group if kind == "verb_unmapped:damage" else conditional_group if kind == "static_conditional" else None
        if not classifier:
            raise SystemExit(f"ticket #{tid}: no deterministic classifier for {kind}")
        groups = collections.defaultdict(list)
        confidence = {}
        for name, detail in members:
            key, ready = classifier(detail)
            groups[key].append((name, detail))
            confidence[key] = ready
        if sum(map(len, groups.values())) != len(members):
            raise SystemExit(f"ticket #{tid}: incomplete partition")
        proposals[tid] = (groups, confidence)
        print(f"ticket #{tid}: {len(members)} misses -> {len(groups)} disjoint children")
        for key, vals in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
            state = "todo" if confidence[key] else "wait"
            print(f"  {len(vals):4} {state:4} {key}")
    if not args.commit:
        print("dry-run: no dispatcher changes")
        return
    now = int(time.time())
    db.execute("begin immediate")
    try:
        for tid, (groups, confidence) in proposals.items():
            existing = db.execute("select count(*) from tickets where parent_id=? and state!='superseded'", (tid,)).fetchone()[0]
            if existing:
                raise RuntimeError(f"ticket #{tid} already has {existing} children")
            parent = rows[tid]
            for key, vals in sorted(groups.items()):
                state = "todo" if confidence[key] else "wait"
                cards = len({name for name, _ in vals})
                examples = "\n".join(f"- [{name}] `{detail}`" for name, detail in vals[:5])
                kind, family = contracts[tid]
                metadata = json.dumps({
                    "version": 1,
                    "miss_shape": kind,
                    "template_family": family,
                    "behavior": key,
                    "member_cards": sorted({name for name, _ in vals}),
                }, separators=(",", ":"))
                title = f"REPARSE-MAP: {key} ({len(vals)} misses, {cards} cards)"
                descr = (
                    f"ATOMIC SPLIT CHILD of #{tid}.\n\n"
                    f"<!-- factory-split: {metadata} -->\n"
                    f"**Miss shape:** `{kind}`  \n**Behavior:** `{key}`  \n"
                    f"**Misses:** {len(vals)}; **cards:** {cards}\n\n"
                    f"**Examples:**\n{examples}\n\n"
                    "This child is a deterministic partition of the parent's full current miss population. "
                    + ("Proceed through the normal map/capability contract." if state == "todo" else
                       "RESIDUAL REVIEW: do not claim until a constrained semantic split makes it atomic.")
                )
                cur = db.execute(
                    "insert into tickets(type,title,descr,mechanic,state,parent_id,created_at,updated_at,priority) values('split',?,?,?,?,?,?,?,?)",
                    (title, descr, key, state, tid, now, now, parent["priority"]),
                )
                child = cur.lastrowid
                db.execute("insert into events(ticket_id,ts,msg) values(?,?,?)", (child, now, f"atomic split child of #{tid}"))
                print(f"created #{child} {state}: {title}")
            db.execute("update tickets set state='superseded',worker_id='',lease_exp=0,updated_at=? where id=?", (now, tid))
            db.execute("insert into events(ticket_id,ts,msg) values(?,?,?)", (tid, now, f"split into {len(groups)} complete/disjoint children"))
        db.commit()
    except Exception:
        db.rollback()
        raise


if __name__ == "__main__":
    main()
