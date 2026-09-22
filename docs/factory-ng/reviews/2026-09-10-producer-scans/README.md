# September 10 — producer scan and fresh-work repair

The user authorized fixing repeated producer scans and the scheduling delays,
and a measured expansion of useful card work. Changes were prepared under
`/tmp/magic-scan-fix`; existing unrelated working-tree changes were preserved.

## Findings

- The previous two ~24h windows yielded 224 and 87 enabled cards. Successful
  integrations changed from 82 to 73; two earlier landings contributed 58 and
  40 cards. The lower figure is not evidence of a stopped integration service.
- The old fresh producer created 4 tickets versus 37 in the preceding window.
  It admitted 18 explicit verb families and required exactly one remaining
  miss. Its historical top-N plan was last committed August 16.
- A profiled 45-second dependency scan read ticket JSON 40,981 times. Version
  selection rescanned all tickets, and a saturated Engine lane still prepared
  multiple retry packets before discarding them. Timed-out scans restarted at
  the first receipt. There were 146 90-second capability producer timeouts in
  the inspected day.
- The fresh producer spent most of a 55-second profile reparsing cards and
  compiling regular expressions. It restarted discovery from the first card.

## Changes

1. The dependency producer uses its existing in-memory ticket index for version
   selection. It scans for Map resumes before preparing at most one deferred
   Engine fallback. Exact admission remains with the controller; retry limits,
   successor ancestry, required gates and trial restrictions are preserved.
2. A disposable SQLite cache retains receipt-demand projections and raw
   capability extraction. File size, mtime and ctime invalidate entries. Legacy
   raw JSONL is not repeatedly parsed as JSON; partial files are retried when
   they change. Current Oracle validation is retained, sharing one card-record
   load per scan. Job state is always read fresh.
3. Fresh scans checkpoint a cursor and parse summaries in ~15-second work
   slices. Parse entries are bound to repository path, exact source revision
   and complete card input. Selected cards are reparsed and source identity is
   checked before publication. A source change discards that scan revision's
   cache entries. Pending scans are not reported as exhausted.
4. The controller runs producer subprocess waits in one helper thread and
   continues reconciliation/worker dispatch/integration on its original owning
   thread at ~15-second intervals, including across consecutive short producer
   calls. Producer deadlines remain in effect. Admission uses fresh queue state
   after dispatch; stopping cannot publish a newly prepared ticket.
5. Fresh discovery covers every explicitly enabled verb even if the old top-N
   plan omitted it. The new measured plan is an immutable operations artifact,
   not an edit to canonical openmagic. `fight` and `damage_by` are enabled:
   registered `fight` and `damage` remain the entry points, with explicit
   source/recipient, bidirectional-versus-one-way, choice and controller
   requirements. Unsupported exact shapes still require Engine dependencies.
   `counter_unless` is not enabled: its runtime exists, but it lacks the V2
   registry metadata required by this producer. Broader admission is not made
   by treating grandfathered vocabulary as proven V2 support.

## Measurement and validation

A complete census of 17,276 review cards at
`374344d5b2b3a10001eec0357912ac8dac3f3f26` took 125.72 seconds in a disposable
clone. It found 40 `fight` and 63 `damage_by` cards with exactly one remaining
miss (103 candidate cards, not completed cards or guaranteed yield). The
census and refreshed plan retain their source revision. Current source is
revalidated for actual ticket production.

A new fresh-work dry-run produced an Aggressive Instinct TicketSpec in 18.64
seconds, with the original Map gates plus explicit damage-source semantics.
No dry-run ticket was manually enqueued. A warm dependency-only scan completed
in 9.46 seconds and an ordinary dependency scan in 11.46 seconds. These are
individual measurements under concurrent factory load, not sustained daily
throughput claims or a controlled wall-time speedup ratio.

Python validation: 9 new scan/scheduling tests, 65 control tests, 19 reliability
tests, 8 recovery tests and 5 capability-contract tests passed (106 total).
The new tests cover resume progress, cache invalidation, partial receipts,
version history, saturated-lane Map precedence, one fallback preparation,
controller thread ownership, producer timeout and stop behavior, and admission
of families absent from a historical plan.

Existing Go shape checks for `TestShape_Triggered_Fight` and
`TestShape_ETB_DamageOpponent` were run against the isolated source snapshot.
Their terminal result and live activation evidence are recorded below.

No retry counters were reset, no historical receipts were rewritten, and no
live game deployment was requested or performed. Every produced card patch
still requires its ordinary focused and full production integration gates.

## Activation

Published at 19:01:51 UTC under the dispatcher-admin lock. The old controller
exited gracefully at 19:01:56; the supervisor started controller PID 1153298
at 19:02:11. Three worker leases were assigned at 19:02:35. Enabled profile
validation passed (3 contracts). Both named Go shape tests passed; canonical
openmagic was clean at the initial activation check. Live family admission
verification follows in activation.json.

The first newly enabled-family ticket, Aggressive Instinct (`map.plan-damage-by-aggressive-instinct-9e89e924ec/v1`), was automatically queued at 19:05:32 UTC. Codex-2 was assigned an Engine job at 19:04:49 while that fresh producer was active. This verifies live production and scheduling, not card completion or a 200-cards/day rate.
