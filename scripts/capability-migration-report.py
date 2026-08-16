#!/usr/bin/env python3
"""Report legacy free-text primitive parks that need atomic rediscovery.

This deliberately performs no writes. Legacy ``missing_prim`` values lack
paragraph-level behavioral evidence, so automatically converting them would
recreate the ambiguity the capability contract is intended to remove.
"""
import argparse
import json
import sqlite3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    db = sqlite3.connect(args.db)
    rows = db.execute(
        """select t.id,t.title,t.missing_prim,t.descr,t.updated_at
           from tickets t left join ticket_capabilities tc on tc.ticket_id=t.id
           where t.state='blocked' and coalesce(t.missing_prim,'')!=''
             and tc.ticket_id is null order by t.id"""
    ).fetchall()
    records = [
        {"ticket_id": r[0], "title": r[1], "legacy_missing_prim": r[2],
         "updated_at": r[4], "migration_state": "needs_atomic_discovery",
         "reason": "legacy park has no validated paragraph-level capability contract"}
        for r in rows
    ]
    if args.json:
        print(json.dumps(records, indent=2))
        return
    print("legacy blocked tickets requiring atomic discovery: %d" % len(records))
    for rec in records:
        print("#%(ticket_id)d\t%(legacy_missing_prim)s\t%(title)s" % rec)


if __name__ == "__main__":
    main()
