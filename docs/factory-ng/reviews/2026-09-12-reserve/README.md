# Runnable reserve replenishment

Five enabled workers imply a ten-ticket runnable reserve. The live factory
repeatedly had zero runnable tickets despite available Claude/Codex quota.
Fresh Map verdicts also accumulated validated Engine demand during a sweep.

Three scheduling defects are corrected:

- `scan_pending` continues within the existing bounded sweep and requests the
  next controller cycle when still below capacity. It no longer waits for the
  five-minute periodic scan. Only each producer's latest result controls that
  decision, so a later exhausted/error result stops immediate continuation.
- The capability-dependency producer remains eligible for subsequent rounds
  while other producers make progress. An early `awaiting_dependency` result
  no longer excludes newly arriving Map verdicts for the rest of that sweep.
- Retry headroom cannot reduce the effective ready target. Five working jobs
  previously reduced admission from twelve to seven; admission now has a floor
  of ten in that configuration. The existing maximum is raised to the target
  before applying this calculation, as before.

Sweep attempt limits, source validation, routing/profile compatibility, repair
budgets, the two-miss pilot limit and every integration gate remain in force.
No worker preference or quota settings changed. The reserve is shared among
compatible workers; it is a production target, not proof that ten eligible
candidates always exist.

102 tests passed: 67 control, 12 producer-performance, 19 reliability and four
capacity tests. New cases exercise repeated bounded scan continuation, same-sweep
dependency discovery, exhaustion/backpressure and the ten-ticket admission floor.
Enabled profiles, Python compilation and changed-file whitespace checks passed.

Controller 3915495 received SIGHUP under `dispatcher-admin` after validation.
The supervisor started successor 360455 at 21:15:39 UTC, which reconciled the
in-flight worker and dispatched Redeem at 21:16:02 UTC. No game deployment.
`implementation.patch` records only this session's code/test/runbook changes,
relative to the pre-existing working tree; unrelated operations edits remain.

`activation.json` records live observations after activation. All three Codex
leases received work; codex-3 started a chosen-source prevention dependency at
21:25:13 UTC, and later codex/codex-2 also took Engine dependencies. Fresh scans
and dependency production alternate in the same sweep. The runnable reserve
was still below ten; this is admission/dispatch evidence, not a claim that the
reserve is filled or that accepted work has integrated.
