# Bounded collection and final-composition checks

The user authorized the measured batching improvements. Seventeen integrations
in the morning baseline applied 31 patches; ten waves contained one patch.
Recorded gate time totaled 162.8 minutes, including 39.9 minutes of corpus
reparse/import, 25.9 minutes of explicit builds and 51.8 minutes of the sharded
suite. Test gate timings include compilation; these are not compiler-only
measurements. See `baseline-integrations.json`.

## Changes

- Collect for at most 120 seconds from the oldest accepted patch while workers
  are active; flush at three candidates, with the existing eight-candidate cap.
  No wait for isolated retries, an idle fleet, invalid legacy timestamps or
  expired deadlines. New arrivals and controller restarts cannot extend a wait.
  Collection returns immediately to the controller instead of blocking workers
  or producers with a sleep.
- Apply conflict-free patches before running every original semantic gate on
  the final composition. Ordinary multi-patch waves no longer compile each
  successive candidate prefix. Tests still execute, including the named-test
  execution check; the build, game, focused and full six-shard gates remain.
- Merge conflicts retain per-ticket exclusion. A shared semantic/full-gate
  failure publishes nothing and uses the existing individual integration retry
  path. Single-candidate failures retain their individual diagnostics. Retry
  budgets and worker permissions are unchanged.
- Composed gate records identify their TicketSpec to make failures traceable.

The separate warm-cache retention change remains at a 40 GiB hourly cleanup
threshold with a 20 GiB free-space safeguard. This batching work adds no new
cache or persistent clone pool. Aggregate CPU admission is not changed: first
measure the reduction in repeated builds before adding another scheduling layer.

## Validation and activation

109 tests passed: seven batching, four merge-resolution, 19 reliability, 65
control, four capacity and ten producer-performance. Cases include a later
patch invalidating an earlier contract, refusal to publish a failed wave,
isolation of shared failures, and unchanged individual conflict attribution.
The existing real-Git fixture verifies conflict exclusion, publication and
idempotent retry. Enabled profiles, Python compilation and diff checks passed.

Policy was written atomically under `dispatcher-admin`; controller 2881227
received SIGHUP and successor 3915495 started at 12:33:11 UTC. The running
workers and pre-existing integration 3895365 continued. No game deployment.
The canonical checkout was clean after the reload.

The patch in `implementation.patch` is relative to the files at the start of
this change, preserving the repository's earlier uncommitted operations work.
No sustained throughput improvement is claimed until enough new waves complete.
