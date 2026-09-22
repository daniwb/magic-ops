# Producer CPU optimization — 2026-09-15

Activated the build-plan producer changes under dispatcher-admin. Each new
producer invocation loads them automatically; the controller and running gates
need no restart. The shared CPUs 12,19 / nice 10 limit and manual compilation
switch are unchanged. No canonical game-source edits or deployment.

## Changes

- Parser modules receive a bounded 8,192-entry compiled-pattern facade using
  public `re.compile` and compiled-pattern methods. The process-wide regex
  module is unchanged; DEBUG behavior, flags, callbacks and match objects remain
  native. Worker/final acceptance gates continue to use the canonical parser.
- Persist compact ticket-history projections, bulk-load their index and stat
  every file for inode/mtime/ctime/size changes. Job state is read fresh. Version
  assignment reuses the existing index. Integration-repair discovery reads full
  tickets only for candidates needing their original contract.
- Persist review-card shard projections and exact parser-built subtype tables.
  Parser cache fingerprints include implementation/support modules, Keywords.json,
  registered effect names, subtype data, runtime-helper content and Python version.
  Unrelated commits no longer invalidate every cached parse. Changed cards still
  have individual content hashes. Fresh/multi/repair lanes share compatible results.
- Repair/conflict scans parse only Oracle texts with an eligible bounded repair
  lineage. This avoids reparsing thousands of cards that cannot receive a retry.
- Current source identity and cleanliness are checked after parser preparation
  and again before ticket publication, including integration-repair publication.

## Measurements and validation

The frozen input snapshot is identified in snapshot.json. Complete parser output
for **30,102 cards matched exactly**, with zero exceptions in either run.
The measured corpus-pass CPU fell from **267.63 to 207.79 seconds (22.4%)**.
This is smaller than the earlier repeated 60-card experiment because a full
corpus pass encounters new card-name patterns. It is not an end-to-end throughput
claim; cached subsequent scans avoid much of that parsing altogether.

Ticket-history CPU fell from **7.22 to 1.99 seconds (72.5%)** for 6,287 production
keys. Parser setup took **9.01 seconds cold and 0.95 seconds in a subsequent
process** with the same corpus (16,768 review cards). Cold initialization remains
necessary after relevant input changes. Wall times were affected by shared load;
CPU time is reported for comparisons.

The 151-test focused/controller/lifecycle/verification suite passed 150 initially.
One existing live-source dependency test correctly returned `source_dirty` while
integration owned the checkout; that test passed on isolated rerun, alongside
all seven new runtime/cache tests. Logs retain both results. Earlier repair tests
exposed unnecessary whole-corpus repair scans; their filter was implemented and
the tests passed without changing their expectations.

The new tests cover public regex behavior and bounded memory, parser-only scope,
persistent table reuse, edit/replacement/deletion detection, input fingerprints,
sharing across lanes/revisions, fresh job state, supersession and version lookup.
No model calls or live ticket publication were added by validation. Canonical
source was clean at the post-activation health check. Five existing unresolved
integration failures remained outside this change.

The first observed updated multi-miss run completed normally at 06:42:51 UTC
with `scan_pending` (bounded resumable discovery). Live cache inspection confirmed
6,818 ticket projections, 30 shard projections and a subtype-table snapshot.
This confirms activation; it does not claim an immediate end-to-end queue drain.
