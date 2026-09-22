# Automatic repair follow-up — September 8, 2026

The factory now reserves a small amount of capacity for existing failed Engine
integrations even when the ordinary queue is oversized. It also follows Map
repair history through dependency handoffs, so a lost counter cannot silently
stop an eligible repair or grant unlimited retries.

## What changed

- The controller uses the existing two-slot repair reserve size for a restricted
  Engine integration-repair pass. The pass cannot create fresh Engine demand.
  It only derives immutable successors from accepted observations and matching
  candidate-specific integration failures. Completed and superseded work is
  excluded. Active repairs count against the reserve and outrank ordinary
  Engine work. It does not rewrite historical tickets or mark failed work accepted.
- Engine successors preserve the original gates and scope. They carry the exact
  failure, including diagnostics that previously disappeared behind long Go
  output, and a hash-verified bounded excerpt of the retained candidate patch
  for review/reuse. That patch is historical evidence; it is not automatically
  applied or taken as current source authority.
- One shared ancestry check recovers Map repair generations through old
  `supersedes`/`integration_recovery_parent` links. New dependency handoffs retain
  the generation. Missing or cyclic history fails closed. Failed dependency Map
  resumes can enter the bounded repair path when allowance remains; complete
  parsing and all original gates stay mandatory.
- The existing limits remain two Map repair generations and one Engine
  integration repair. A later evidence refresh cannot hide a used Engine repair.
  Exhausted jobs retain their failed receipt/state and gain `repair_blocker`
  and an explicit `waiting_reason` in controller/dashboard job data.
- Both worker runners already enforced actual named-test execution after the
  September 7 fix. This repair verifies that behavior with a real Go regression
  and improves the correction context: missing-name failures include editable
  test source, and the correction instruction permits fixing a mismatched
  candidate name while preserving assertions. Required behavioral clauses are
  also explicitly retained in the remote runner's contract section.

## Concrete examples

A test-name mismatch is now covered end to end: a candidate has `TestWrongName`,
the gate requires `TestValue`, the first run is rejected, the bounded correction
receives current test source, and acceptance happens only after `TestValue`
actually passes. The historical 35 candidate failures are not reclassified as
passing merely because this regression succeeds.

Tidal Surge Map v5 resolves through v4 to v3's already-used generation 2.
It therefore receives an explicit 2/2 repair-limit blocker, not a fresh retry
budget. Its card remains unfinished. The counterpart regression with one
remaining allowance produces exactly the final permitted successor, retaining
its complete-card test and scope. A newly integrated Engine dependency still
requires Map verification even when the corpus already calls the card eligible.

## Verification

- 8 recovery tests: ancestry, missing/cyclic history, remaining/exhausted limits,
  dependency handoff, saturated queue admission, existing active reserve slots,
  immutable receipt/patch binding, no duplicate successor and no fresh demand.
- 15 staged-runner tests, including actual isolated Go test rejection/correction.
- 19 reliability tests.
- 65 controller tests. The initial run raced live canonical integration in two
  existing tests that use its default source path. The complete suite then
  passed with those producer subprocesses directed to a clean isolated source
  snapshot at `ebbdca7d10a642d1061b8502f415815283fad570`.
- All five enabled worker profiles validate; edited tracked files pass diff checks.

Total: 107 tests. No production Engine/parser changes or live game deployment
were performed by this repair. Existing active workers finish under the runner
version they loaded; subsequent workers use the updated code. The controller
was reloaded by exact PID under the dispatcher-admin lock; see
[reload evidence](automatic-repair-reload.json). The supervisor replacement and
Tidal's explicit blocker were verified. Live automatic successor admission is
recorded separately below; queue admission is not card completion.

## Live automatic admission

At 19:18:30 UTC the replacement controller automatically queued
`ticket:engine.auto-dynamic-x-count-named-copies-in-all-graveyards-aee4fdb33f/v2`
(Kindle), despite the oversized ordinary queue. Its predecessor is retained
and marked superseded; the successor preserves the exact gates and scope.
[Live handoff evidence](automatic-repair-live-handoff.json) records the job,
predecessor and Tidal blocker. This proves automatic repair admission, not
worker acceptance, integration or a completed card.
