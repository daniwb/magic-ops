# Combined focused verification — 2026-09-14

The user's CPU optimization choice is implemented without scheduling. The
Compilation & testing switch stays Off until the user enables it.

The controller defers successful drafts, including while On, to a central
verifier. It groups up to eight proposals sharing a source revision, using a
120-second maximum collection window and a three-candidate target while
workers are drafting. Two disposable checkouts suffice: one reused for each
individual scope check and patch export, and one final composition for all tests.
Every required test selector remains enforced. Identical simple test commands
share evidence; Go's build cache reuses compilation across different selectors.
Measurements and arbitrary shell commands still execute per ticket.

No receipt is accepted until the entire composition passes. Receipts identify
the tested tree and every member. Conflicts, failed tests and crashed batches
retain original proposals and route to individual verification with bounded
repair. Switching Off between gates saves work without acceptance. Full
integration rechecks the included tickets on its own final composition (even
when it selects a subset), then runs the existing complete gates. The controller
serializes focused verification and integration to avoid overlapping builds.

Validation:

- 41 focused-batch, manual-switch, integration-batching and reliability tests
  passed (`/tmp/magic-focused-regression.log`).
- A real two-selector Go test passed: both named tests executed on the same
  composition; the second invocation made no compiler call
  (`/tmp/magic-focused-go-tests.log`). Cold standard-library compilation made
  this isolated test take 176 seconds under the shared CPU limit; this is not
  a production CPU reduction measurement.
- Nine final checks passed, including both worker harnesses deferring while On
  and a subset integration correctly rejecting a missing dependency
  (`/tmp/magic-focused-final-check.log`).
- The broader controller run exposed an unrelated live-corpus-dependent
  producer fixture failure (`test_integration_conflict_gets_one_latest_source_successor`).
  A receipt-cache mock compatibility failure was corrected and passed recheck.

Activation changes only the verification policy and reloads the supervised
controller under dispatcher-admin. Compilation remains Off. No canonical
source edits, game integration, push or deployment were performed by this task.
