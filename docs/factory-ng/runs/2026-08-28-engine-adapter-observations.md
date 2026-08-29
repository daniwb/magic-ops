# Factory NG observation — Engine child adapter routing

Status: no source mutation, no live ticket, no commit, no deployment.

Ticket bundle: `engine:draw-target-lifting-v1`, the Engine child described in
[`../tickets/first-targeted-draw-dag.md`](../tickets/first-targeted-draw-dag.md).

## Attempt 1 — Codex Luna constrained

- Result: `infrastructure_failed` before repository inspection.
- Cause: the read-only Bubblewrap sandbox could not create its loopback
  interface: `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`.
- Raw counters reported by Codex: input `59,017`, cache-read `52,992`, output
  `928`, reasoning `535`; cache-write was not reported (`unavailable`).
- Quality is **not measured**. The model could not execute `ls`, `git status`,
  or `rg`, so it had no opportunity to evaluate or implement the ticket.

## Attempt 2 — Claude Sonnet staged fallback

- Result: `infrastructure_failed`.
- The plan-mode CLI process produced no stdout, stderr, JSON receipt, or exit
  receipt after several minutes. Provider token/cost/cache counters are
  **unavailable**, not zero.
- Quality is **not measured**. The fallback has no evidence of repository
  inspection or a model decision.

## Attempt 3 — Claude Sonnet staged, complete no-tools packet

This used the same Engine child after deterministic preparation supplied the
file path and line-pinned converter excerpt, full `executeDrawEffect` body,
and a sibling target-test convention.

- Result: a scoped proposal was returned in 90.8 seconds. It changed only
  `backend/cards/converter.go` and added one focused card test; `git apply
  --check` and `git diff --check` passed in an isolated clone.
- Raw provider counters: input `2`, cache-creation `8,329`, cache-read
  `17,729`, output `10,476` (including `9,059` thinking), provider cost
  `$0.1440028`. These are retained as emitted; cache counters are not folded
  into the effective-token calculation.
- Gate result: **failed**. The proposed test imported
  `magic-ops/backend/game`; the module is `magic-backend/game`, so
  `go test ./cards -run '^TestDrawSpellTargetLifting$'` failed at setup.
- Quality verdict: the converter patch is mechanically applicable, but the
  complete proposal is not accepted because its discriminating test does not
  compile.

## Attempt 4 — one focused Claude repair

The harness supplied the exact module error and existing test header. Claude
returned an import-only repair in one turn: input `2`, cache-creation `6,845`,
cache-read `17,729`, output `145`, thinking `0`, cost `$0.0336118`.

The repair applied cleanly in the same isolated clone, but the next focused Go
gate exposed a second error in the original generated test:

```text
cards/draw_target_lifting_test.go:63:5: expected '}', found 'EOF'
```

The repair budget is exhausted. **Final attempt outcome: `gate_failed`.** The
proposal is rejected; no part of it is accepted or copied into a real worktree.
This prevents a superficially plausible converter change from being mistaken
for working code.

This is a successful Factory safety outcome: a small wrong detail was caught
in an isolated gate before it could reach a worktree, commit, or deployment.

## Routing decision

Do not rerun this Engine ticket merely with a larger model. The next bounded
Factory task is `factory:read-only-adapter-receipt-v1`: make each supported
adapter either emit a complete timeout/exit receipt or fail before dispatch.
It must preserve the no-mutation observation mode. The next **evidence** child
also needs the module declaration and a line-pinned existing test-file header
in every Go ticket packet. Add a deterministic `gofmt`/syntax preflight before
the Go test so a malformed generated test is reported together with, rather
than after, an import error. Re-dispatch only as a new attempt with that
complete packet; do not resume this exhausted attempt.
