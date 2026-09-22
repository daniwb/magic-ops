# FTS5 source lookup audit — September 8, 2026

Read-only inspection around 15:04–15:10 UTC. Source revision:
`6642351731e0c336cd220a861dd14fc212e7d192`.

## Findings

The live SQLite table is `docs USING fts5(kind, title, body, path)` in
`/tmp/orch/knowledge.db`. It stores copied text, but no source line columns,
commit IDs or file hashes. Engine rows contain leading comments and function
signatures, helpers contain comments, primitive rows contain catalog sections
or up to 1,500 characters starting at a registry registration. Handler rows
contain header documentation. Search snippets come from these stored bodies.

`card-knowledge-service.py` rebuilds on startup, on `/reindex`, and every
1,800 seconds by default. The running service has no KB environment overrides.
Periodic rebuilds appear in its log; the database mtime at inspection was
14:42:06 UTC. The retired integrator-lite explicitly calls `/reindex`; the NG
integration script inspected does not. A shared index can lag source changes
and can also describe a newer revision than a worker's pinned clone.

Comparing all 1,188 indexed engine rows with the current source using the
indexer's own signature/comment extraction found **zero stale rows**. This
does not validate other document kinds, historical freshness, or completeness
of the indexer's symbol coverage.

Live requests reproduced a retrieval failure even with those fresh rows:

| Request | Result |
|---|---|
| `/find?q=draw_cards&n=5` | Four handler descriptions and EvalDynamicAmountFull |
| `/find?q=draw_cards&kind=engine&n=5` | EvalDynamicAmountFull only |
| `/find?q=DrawCards&kind=engine&n=5` | Player.DrawCards in backend/game/player.go |

The index does contain DrawCardWithEvent and DrawCardsWithEvent. Default FTS
tokenization/search does not connect these identifiers to `draw_cards`.
The current index needs normalized identifier words and capability aliases.
FTS is text retrieval, not a code relationship resolver; see the official
[FTS5 tokenizer documentation](https://www.sqlite.org/fts5.html#tokenizers).

`factory-ng-produce-capability-dependency.py:knowledge_hits` already selects
only kind/title/path from FTS, then reads the source file. However, it locates
the first line *containing* the title and takes a short window. An inventory
check found **402 of 1,188 rows** where the first match plus 60 lines still
ends before the first matching function declaration. Example:
ResolveSequenceChoice first occurs at effect_sequence.go:20, while its
declaration is at line 556. This is a potential bad-window count, not a count
of failed tickets; later packet resolution can recover some cases. The recent
NEED resolver repair does not remove this producer-side first-match logic.

The search service also tells workers that NO MATCH probably means a missing
engine capability. Its limited index cannot establish that conclusion. `/caps`
checks only selected event constants and converter labels; that is not proof
of complete capability existence or absence either.

## Recommended bounded change

Keep FTS5 for discovery. Return a compact candidate list with qualified symbol
identity (package/receiver/name), file, short purpose and indexed revision.
Normalize snake_case/CamelCase and explicitly connect capability aliases to
their implementation entry points. Names alone omit useful distinctions.

Use one deterministic source resolver for both packet preparation and NEED:
resolve the selected declaration or dispatch branch against the worker's
actual pinned checkout, then return current line numbers, signature/body,
directly needed types and a content hash. Do not trust cached line windows.
Use structural parsing for Go declarations/method identity. Expose bounded
call relationships when requested, rather than dumping an entire call graph.

For `draw_cards`, a useful verified implementation path is
GameState.executeDrawEffect → GameState.DrawCardsWithEvent →
GameState.DrawCardWithEvent. The last method handles replacement lookup and
event publication. Player.DrawCards is a lower-level loop over Player.DrawCard;
retrieving the similarly named function alone can therefore suggest the wrong
entry point for gameplay behavior.

Fresh source fetching prevents stale excerpts but cannot discover symbols
missing from an old index. Record freshness and fall back to local declaration
search on missing/stale candidates. A search miss must remain “not found by
this search”, not an automatic Engine demand.

This investigation changed documentation only. The proposed FTS/resolver
changes have not been implemented or activated.
