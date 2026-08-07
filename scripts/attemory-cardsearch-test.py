#!/usr/bin/env python3
"""Comparative test: attemory (:8005, attention retrieval) vs kb-service
(:4103, FTS5) for card/primitive search. Ingests the SAME corpus from the
kb service's sqlite index into an attemory session, then runs benchmark
queries against both. Run with magic-ops/.venv/bin/python."""
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

from attemory.client import AttemoryClient

KB_DB = '/tmp/orch/knowledge.db'
SESSION = 'cardsearch-test'
N_HANDLERS = int(sys.argv[1]) if len(sys.argv) > 1 else 500

cli = AttemoryClient(port=int(__import__("os").environ.get("ATTEMORY_PORT","8006")))
assert cli.health(), 'attemory not healthy'

db = sqlite3.connect(KB_DB)
rows = list(db.execute("SELECT kind, title, body FROM docs WHERE kind='primitive'"))
rows += list(db.execute("SELECT kind, title, body FROM docs WHERE kind='handler' LIMIT ?", (N_HANDLERS,)))
print(f'ingesting {len(rows)} docs ({N_HANDLERS} handlers cap) into session {SESSION!r}...')

try:
    cli.delete_session(SESSION)
except Exception:
    pass
cli.create_session(SESSION)
t0 = time.time()
for i, (kind, title, body) in enumerate(rows):
    cli.add_memory(f'[{kind}] {title}\n{body[:1200]}', session_id=SESSION)
    if (i + 1) % 100 == 0:
        print(f'  {i+1}/{len(rows)} ({time.time()-t0:.0f}s)', flush=True)
print(f'ingest done in {time.time()-t0:.0f}s')
t0 = time.time()
cli.index_session(SESSION)
print(f'indexed in {time.time()-t0:.0f}s')

QUERIES = [
    ('grothama-like', 'Whenever a creature deals combat damage to this creature, '
     'that creature controller draws that many cards'),
    ('myr-turbine-like', 'Tap five untapped Myr you control: search your library '
     'for a Myr creature card and put it onto the battlefield'),
    ('primitive-lookup', 'grant a triggered ability to all commander creatures you own'),
]

for name, q in QUERIES:
    print(f'\n=== {name}')
    t0 = time.time()
    res = cli.search(q, session_id=SESSION, top_k=3)
    ta = time.time() - t0
    for r in res:
        txt = getattr(r, 'text', str(r))
        print(f'  [attemory {ta:.1f}s] {txt[:100]}')
    t0 = time.time()
    url = 'http://127.0.0.1:4103/similar?' + urllib.parse.urlencode({'text': q, 'n': 3})
    kb = urllib.request.urlopen(url, timeout=15).read().decode()
    tk = time.time() - t0
    for line in [l for l in kb.splitlines() if l.startswith('===')][:3]:
        print(f'  [fts5     {tk:.1f}s] {line[:100]}')
