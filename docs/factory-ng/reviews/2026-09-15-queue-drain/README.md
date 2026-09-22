# Queue throughput investigation — 15 September 2026

The requested goal was to measure queue reduction and remove demonstrated
bottlenecks while preserving all acceptance and integration gates. The user
reported 51 waiting, then 42. Instrumented observations begin at **16:43:37 UTC:
43 waiting + 9 running = 52 unfinished**. Those are different timestamps, not
inconsistent definitions of one sample.

## Changes enabled

- Persistent observer: `scripts/factory_ng_queue_tracking.py`, called by the
  watchdog, stores `state/factory-ng-queue-trend.json` and append-only JSONL
  history. It separates waiting, running, completions, new entries, reentries,
  and unsuccessful exits. Dispatch alone cannot count as queue reduction.
- Growth warning: at least five additional unfinished tickets over an observed
  window of at least 30 minutes, with at least 20 still unfinished. The usual
  watchdog runs every ten minutes. This detects sustained growth; it does not
  guarantee a queue can never grow or automatically alter resource policy.
- Original ticket semantic checks now accompany the six production stages to
  the Ryzen. Enabled at **16:51:43 UTC**. Exact commands, ticket identities,
  source/input hashes, gate results and returned tree are validated. Red checks
  block integration; transport failure reruns semantics and full gates locally.
- Two local repair processes may overlap in the existing four-CPU affinity pool,
  each retaining Go parallelism two. Four remote focused slots and one remote
  full-gate slot remain; final canonical integration is serialized.
- Fixed a live receipt reconciliation loop at **17:09:31 UTC**. Resumed workers
  retain a verification marker during integration; integration had overwritten
  their consumed observation receipt, causing an old acceptance to appear new.
  Conflicting patches were repeatedly resubmitted (one reached 16 attempts).
  Integration now preserves the consumed observation. Conflict evidence stays
  visible for existing repair producers; attempts and job state were not reset.

## Production evidence

| Completed UTC | Tickets landed | Original semantic checks | Six production stages |
|---|---:|---|---|
| 16:48:57 | 7 | Local, 533.028 s | Ryzen, 99.853 s |
| 17:01:23 | 4 | Local (earlier admitted policy) | Ryzen |
| 17:04:42 | 3 | Ryzen, 30.618 s | Ryzen, 62.998 s |

The first two waves took about twelve minutes from invocation to receipt. The
third took 178 seconds including preparation, transport, validation and push.
Ticket mixes and cache warmth differ: this is live bottleneck evidence, not a
controlled speedup ratio. The third wave used 7.45 GiB peak against its 12 GiB cap.
Subsequent green waves are recorded in the final observation below.

The isolated expanded transport pilot passed all 20 checks and reconstructed the
exact known accepted tree in **130.704 seconds**. One preceding attempt correctly
refused an occupied production slot. Its temporary environment was removed.

## Validation

Scoped regression runs: 50 semantic/transport/integration/tracker checks; 34
repair-slot checks; 23 observer/reliability checks; four final observer checks;
and 38 receipt-loop/reliability/batching/priority/tracker checks. These suites
overlap and are not a count of unique tests. Logs are stored here. Live remote
receipts prove the original semantic checks and full production gates passed
before push. No live deployment was performed.

## Limits and retained failures

Successful completions are distinct from failed/superseded exits. Unsuccessful
exit counts are events: an integration failure followed by a reentry can appear
more than once. A lower queue is not evidence that every departed ticket shipped.
The initial backlog also contains repairs held by provider usage policy, including
six Claude-owned repairs with the configured next opening at 18:00 UTC. Those
limits remain in force. Existing producer/integration faults are separately
visible in watchdog state; a shrinking queue is not an all-components-green claim.

[Queue chart](queue-trend.png), [sample history](queue-history.json),
[first live full-gate receipt](first-live-remote-integration.json),
[first live remote-semantic receipt](first-live-remote-semantics-integration.json),
[pilot](semantic-pilot.json), [receipt-loop activation](receipt-loop-activation.json).

## Final observation

At **2026-09-15T17:14:55Z**, after **31.3 minutes**:

| Measure | Initial | Final |
|---|---:|---:|
| Waiting | 43 | 14 |
| Running checks/integration | 9 | 5 |
| Total unfinished | 52 | 19 |

**16 tickets completed through five successful integration waves**,
including three waves with original semantics executed remotely. There were
10 newly observed tickets and 5 reentries;
32 unsuccessful exit events were recorded separately.
The initial cohort's final states are `{"completed": 14, "failed": 19, "focused_run": 2, "focused_wait": 9, "integration_failed": 5, "integration_run": 1, "superseded": 2}`.
The observer reports `shrinking` and no growth alert.

Five formerly looping conflicts retained unchanged attempt counts (6, 6, 16, 8,
10) across successive post-fix samples, instead of reentering integration.
See `receipt-loop-observation.jsonl`. No failed ticket was counted as shipped.
All 16 successes are linked in `successful-waves.json`.

The requested monitoring/fix goal is satisfied for this observation window.
Persistent watchdog sampling and growth warnings remain enabled. The evidence
supports a reduced test/integration backlog, not a promise about all future load
or resolution of every failed proposal. Final health inspection found the
canonical source clean with no integration owner; ten unresolved integration
failures remain explicitly visible to repair/recovery workflows.

Final health-check update at 2026-09-15T17:15:54Z: 14 waiting + 2 running = 16 unfinished; 19 completed through 6 successful waves. Canonical checkout clean and integration lock free. Earlier final-observation table retains its stated timestamp.
