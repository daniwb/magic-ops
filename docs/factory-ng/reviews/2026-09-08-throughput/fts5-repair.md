# Knowledge lookup repair — implemented September 8, 2026

The operator authorized the single-service lookup and source-resolution repair.
The updated knowledge service is running on port 4103. The canonical engine
checkout stayed clean; no card implementation, integration gate, model quota,
live deployment or immutable ticket was changed for this repair.

## Implemented behavior

- The capability producer no longer opens `knowledge.db`. All active knowledge
  database access is owned by `card-knowledge-service.py`; the old archive
  experiment is historical. Producers, packet builders, the CLI and worker MCP
  use the shared HTTP client. Ordinary dispatcher SQLite access is unrelated.
- `/search` returns structured candidates. Exact names and qualified identities
  come first, followed by normalized words matched together. CamelCase,
  snake_case and common draw/card inflections are normalized. Matching names
  outrank incidental prose; equivalent GameState names are presented first.
  Broader discovery requires a separate, explicit fallback request, which keeps
  the first three meaningful capability words together. There is no unrestricted
  OR over a capability requirement. Explicit handler similarity remains a
  separately labelled operation.
- Go's parser identifies functions, receivers, types and string case branches.
  Candidates have `path::package.receiver.symbol` identities. The shared source
  resolver reparses the actual worker checkout and returns current declaration
  lines, a bounded excerpt, content hash and source revision. Cached positions
  are never used to select the excerpt. Missing/ambiguous identities are
  unresolved. Directly requested types use the same resolver. Existing explicit
  line-range requests remain supported as explicitly requested ranges.
- The NG engine packet uses service discovery and parsed declarations instead
  of generic keyword windows or first-occurrence anchors. Newly generated
  ticket evidence contains the selected symbol and lookup trace; older tickets
  are not rewritten. A real old draw-history ticket now receives the existing
  history branch and tracking handler.
- Workers have a read-only `read_source(symbol_id)` MCP tool and CLI
  `source <symbol_id>` command. Search/capability tool descriptions no longer
  claim that a miss proves an Engine gap. Service errors, discovery misses and
  source-resolution failures are distinct. Producer discovery defers if the
  service is unavailable.
- Index snapshots include revision and build time. They rebuild on startup,
  periodically, on explicit reindex, and before lookup when canonical HEAD has
  changed. Rebuilds require a settled source checkout and publish a complete
  SQLite snapshot atomically. An unsuccessful rebuild retains the previous
  index; search responses disclose a stale revision and refresh error.

## Where to see exactly what was searched

Each new runner attempt writes a `*.lookup.jsonl` artifact beside its raw
responses in `docs/factory-ng/runs/`. The receipt references it as
`raw_artifacts.kind = knowledge_trace`. It records caller, ticket/attempt,
original query, normalized query and strategy, candidate symbols, selected
identity, source revision/hash, and the actual supplied excerpt. NEED source
and type resolution also append to this trace. MCP/CLI calls inherit the same
attempt context. Explicit ordinary Read/Grep tool activity remains in the model
artifact rather than being represented as a knowledge-service query.

New TicketSpecs retain producer searches in `evidence[].lookup_trace` and
selected identities in `evidence[].symbol`. Central service requests are also
logged to `/tmp/orch/knowledge-lookups.jsonl`, including callers that have no
attempt trace configured. Existing historical attempts cannot be retroactively
given exact original request logs.

## Verification

- 14 knowledge tests passed using real HTTP, SQLite and Go parsing: aliases,
  explicit fallback, receiver disambiguation, shifted lines/changed bodies,
  deleted symbols, path containment, source traces, service errors versus
  misses, producer service use, new-revision refresh, failed refresh retention,
  and the worker source tool.
- 14 staged tests, 64 controller tests, 19 reliability tests and the existing
  knowledge-index test passed: 112 tests total. Three controller fixtures now
  substitute the HTTP discovery result instead of depending on a live database.
  Five enabled profiles validate; Python compilation and scoped whitespace
  checks passed. The Go parser was compiled and formatted.
- [Five live query/source checks](fts5-live-verification.json) passed. Queries
  took 70–206 ms in this sample; this is not a load benchmark. The full
  [lookup trace](fts5-live-verification.jsonl) retains actual source selections.
- The [real draw-history packet](fts5-packet-smoke.txt) contains
  `cards_drawn_this_turn` and `handleTrackCardsDrawn`, and excludes the earlier
  unrelated destroy-land helper. Its [trace](fts5-packet-smoke.lookup.jsonl)
  records how those excerpts were selected. No model call was made.
- [All 18 previously unsuccessful staged tickets were queried](fts5-failed-ticket-replay.json):
  10 returned candidates, eight returned explicit misses, and none returned a
  service error. Candidate discovery does not establish semantic correctness or
  successful card implementation. Those eight misses remain inputs to the
  Engine-gap investigation; they are not automatic requests for new primitives.

## Activation and limits

The knowledge tmux pane was restarted under the dispatcher-admin scoped lock,
then the live endpoint and source resolver were checked. The index currently
includes 2,148 engine documents, up from 1,188 because types and case branches
are now indexed too; this is not card throughput. Factory workers were not
restarted. New attempts load the updated client/tools; already-running MCP
processes retain their loaded tool definitions until the next attempt.

FTS5 remains lexical discovery. It is not a complete call graph or a proof of
game-rule support. The index represents canonical source; fetched code always
comes from the specified worker checkout. Changes existing only in a worker
clone are available to direct source resolution but do not enter the shared
canonical discovery index. The five-card model trial and broader throughput
measurement remain outstanding.
