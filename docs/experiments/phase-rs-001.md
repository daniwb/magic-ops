# Experiment 001 — Observe the phase.rs Engine Factory

Status: active; independent plan-review stage  
Started: 2026-08-27  

## Root task

Observe phase.rs's native `$engine-implementer` workflow while addressing the
real, open, unassigned issue
[#7954](https://github.com/phase-rs/phase/issues/7954):
`Non-fatal engine panic: post-replacement life loss must target a live player:
ResourceOverflow`.

This experiment is for understanding and measurement. It must not push, open a
PR, merge, or deploy.

## Frozen identity

- Project: `phase-rs/phase`
- Base SHA: `fae406c4603f450797014f3ac8e8818b3d36c2a4`
- Branch: `experiment/phase-rs-001`
- Worktree: `/opt/development/phase-experiments/phase-rs-001`
- Matching open PR at selection time: none
- Provider/model: recorded separately for every stage

## Calibration

Read-only command: `codex exec --ephemeral --json --ignore-user-config`

| Field | Value | Status |
|---|---:|---|
| Input tokens | 24,298 | measured |
| Cached input tokens | 9,984 | measured |
| Cache-write input tokens | 0 | measured |
| Output tokens | 8 | measured |
| Reasoning output tokens | 0 | measured |

The event stream exposes all primary dimensions. Raw stage events remain the
accounting authority; aggregate totals must reconcile to them.

## Planned stage graph

```text
Root: observe phase.rs #7954
  -> Stage 1: engine plan
  -> Stage 2: fresh-context plan review
       -> repeat plan/review until clean if necessary
  -> Stage 3: implementation in isolated worktree
  -> Stage 4: checkpoint candidate and measurement
  -> Stage 5: committed-candidate verification
  -> Stage 6: fresh-context implementation review
       -> repeat fix/review if necessary
  -> Stage 7: acceptance without publication
  -> Reflection: workflow, tokens, time, and Factory NG lessons
```

## Telemetry contract

Capture per stage and in total:

- input, cached-input, cache-write-input, output, and reasoning-output tokens;
- start/end and elapsed time;
- model/provider and Codex version;
- Skill and repository revisions;
- artifacts produced, commands, retries, failures, and verdict;
- changed files, verification results, and review findings.

Crossing a warning threshold creates reflection but does not discard the run.

## Current observations

1. A trivial Codex turn already has a 24k-token input baseline, of which about
   10k is cache-read input. Fixed orchestration context is material.
2. phase.rs's current orchestrator is a seven-stage workflow with immutable
   checkpoint review and optional multi-phase decomposition; it is more
   structured than the older six-step summary.
3. The canonical checkout briefly appeared dirty while the fast-forward was
   still materializing its worktree, then reconciled cleanly. Factory telemetry
   should distinguish a running repository operation from a stable dirty tree.
4. Nested Codex `read-only` and `workspace-write` sandboxes both failed before
   launching commands with `bwrap: loopback: Failed RTM_NEWADDR`. The isolated
   experiment worktree had to be used as the safety boundary with the nested
   sandbox disabled.
5. Two interrupted planning attempts produced no `turn.completed` event, so
   Codex did not expose their partial token consumption. Failed/interrupted-turn
   accounting needs a lower-level provider record.
6. A standalone `$engine-planner` invocation attempted to perform its own plan
   review in the same context. The outer `$engine-implementer` contract instead
   requires a fresh reviewer. Stage prompts must declare the outer controller's
   ownership explicitly; Skill composition cannot be inferred safely.

## Stage results

### Stage 1 — plan

- Artifact: `docs/experiments/artifacts/phase-rs-001/stage-01c-plan/final.md`
- Event stream: `docs/experiments/artifacts/phase-rs-001/stage-01c-plan/events.jsonl`
- Result: complete 338-line plan; worktree remained clean.
- Proposed seam: one exact signed `LifeChange` value spanning the existing
  `u32` event magnitude and bounded `i32` stored/event projections.
- Proposed class: combat/direct/replacement life gain/loss, lifelink, pay-life,
  set/exchange/double-life, replay, preview, and AI simulation paths.
- Phase-fit estimate: one coherent unit across 17 scope paths, therefore
  single-phase under phase.rs's conjunction gate.

| Field | Value | Status |
|---|---:|---|
| Input tokens | 6,178,439 | measured stage aggregate |
| Cached input tokens | 5,920,512 | measured stage aggregate |
| Uncached input tokens | 257,927 | derived subtraction |
| Cache-write input tokens | 0 | measured stage aggregate |
| Output tokens | 33,172 | measured stage aggregate |
| Reasoning output tokens | 20,864 | measured stage aggregate |
| JSONL size | 1,120,048 bytes | measured |

Codex emitted one cumulative `turn.completed` usage object. It did not expose
usage per internal model call, so the stage totals are exact while call-level
attribution is unavailable through `codex exec --json` alone.

### Stage 2a — independent plan review, infrastructure failure

- Model: `gpt-5.6-sol`, high reasoning.
- Result: `turn.failed` — selected model at capacity.
- Failure occurred after substantial repository inspection but before a review
  verdict.
- No `turn.completed` usage object was emitted, so partial consumption is
  unavailable through Codex JSONL.
- Worktree remained clean.
- Routing decision: retry the independent review on `gpt-5.6-terra` with high
  reasoning rather than treating model capacity as a plan defect.

### Stage 2b — alternate reviewer capacity failure

- Model: `gpt-5.6-terra`, high reasoning.
- Result: immediate `turn.failed` — selected model at capacity.
- No reported usage and no review work performed.
- Routing decision: use `gpt-5.5` with high reasoning for this review stage.

### Stage 2c — independent plan review

- Model: `gpt-5.5`, high reasoning.
- Result: two blocking findings; worktree remained clean.
- Finding 1: the proposed saturated `LifeChanged.amount` projection omitted
  overflow-prone magnitude consumers in `targeting.rs`, `trigger_matchers.rs`,
  `effects/mod.rs`, and `log.rs`.
- Finding 2: the one-unit Sizing claim undercounted independently testable
  behaviors and must be justified or decomposed.
- Probe limitation: no `cargo` on this execution environment's PATH and no
  gitignored Comprehensive Rules file.

| Field | Value | Status |
|---|---:|---|
| Input tokens | 926,186 | measured stage aggregate |
| Cached input tokens | 825,216 | measured stage aggregate |
| Uncached input tokens | 100,970 | derived subtraction |
| Cache-write input tokens | 0 | measured stage aggregate |
| Output tokens | 9,420 | measured stage aggregate |
| Reasoning output tokens | 4,330 | measured stage aggregate |

The warning threshold is exceeded. Preserve the run and launch reflection
before dispatching a fresh planner revision.

### Reflection 1 — excessive planning/review cost

- Model: `gpt-5.5`, medium reasoning.
- Verdict: `CONTINUE_WITH_CHANGES`.
- Required next step: a fresh revised plan addressing only the missing
  `LifeChanged.amount` consumer scope and the inconsistent Sizing claim;
  implementation remains blocked until a fresh review returns clean.
- Main cost diagnosis: cached tokens expose repeated orchestration-context
  replay; uncached tokens expose new inspection and command-output growth.
- Avoidable sources included repeated full Skill reads, planner self-review,
  broad uncapped searches, and treating large command output as conversation
  context instead of a compact addressable artifact.

| Field | Value | Status |
|---|---:|---|
| Input tokens | 233,113 | measured stage aggregate |
| Cached input tokens | 193,152 | measured stage aggregate |
| Uncached input tokens | 39,961 | derived subtraction |
| Cache-write input tokens | 0 | measured stage aggregate |
| Output tokens | 4,239 | measured stage aggregate |
| Reasoning output tokens | 812 | measured stage aggregate |

### Stage 1d — revised full plan

- Model: `gpt-5.5`, high reasoning.
- Result: complete revised plan; worktree remained clean.
- The run spawned an additional nested planner despite already being a fresh
  planning context. This preserved role separation but added an unobservable
  child interval; stage prompts need an explicit no-nested-delegation mode.
- The missing event consumers and projection invariant were added.
- Sizing now identifies five independently testable units and 21 non-test scope
  paths. Both phase-fit triggers are true, so the next workflow node is charter
  planning rather than another full-plan review.

| Field | Value | Status |
|---|---:|---|
| Input tokens | 1,650,891 | measured parent-stage aggregate |
| Cached input tokens | 1,522,816 | measured parent-stage aggregate |
| Uncached input tokens | 128,075 | derived subtraction |
| Cache-write input tokens | 0 | measured parent-stage aggregate |
| Output tokens | 14,926 | measured parent-stage aggregate |
| Reasoning output tokens | 2,837 | measured parent-stage aggregate |

### Stage 1e — phase charter

- Model: `gpt-5.5`, high reasoning.
- Result: five-phase charter; worktree remained clean.
- Phase order: exact carrier/replay → post-replacement projection → event
  magnitude consumers → difference producers/projections → threshold checks.
- Every leaf declares one unit and 2–8 non-test paths, so no leaf recursively
  fires the phase-fit conjunction.

| Field | Value | Status |
|---|---:|---|
| Input tokens | 253,458 | measured stage aggregate |
| Cached input tokens | 226,944 | measured stage aggregate |
| Uncached input tokens | 26,514 | derived subtraction |
| Cache-write input tokens | 0 | measured stage aggregate |
| Output tokens | 5,141 | measured stage aggregate |
| Reasoning output tokens | 1,352 | measured stage aggregate |

### Stage 2d — independent charter review

- Model: `gpt-5.5`, high reasoning.
- Result: one blocker and one material gap; worktree remained clean.
- Blocker: Phase 1 changes `ResolvedPlayerEdit::Life` from raw `i32` to
  `LifeChange`, but deferred producers initialize the field directly and would
  fail to compile. The phase is not independently green.
- Gap: `PendingLifeTotalAssignment` type/serialization ownership is attributed
  inconsistently between Phase 1 and Phase 4.
- Other charter checks passed: premise, dependency direction, literal paths,
  and recursive phase-fit termination.

| Field | Value | Status |
|---|---:|---|
| Input tokens | 647,784 | measured stage aggregate |
| Cached input tokens | 583,808 | measured stage aggregate |
| Uncached input tokens | 63,976 | derived subtraction |
| Cache-write input tokens | 0 | measured stage aggregate |
| Output tokens | 5,971 | measured stage aggregate |
| Reasoning output tokens | 3,098 | measured stage aggregate |

### Stage 1f — charter revision

- Model: `gpt-5.5`, high reasoning.
- Result: complete revised charter; worktree remained clean.
- Phase 1 now owns all compile-required `ResolvedPlayerEdit::Life` producers.
- Phase 4 now owns the complete `PendingLifeTotalAssignment` type,
  serialization, producer, and consumer migration.

| Field | Value | Status |
|---|---:|---|
| Input tokens | 227,449 | measured stage aggregate |
| Cached input tokens | 190,720 | measured stage aggregate |
| Uncached input tokens | 36,729 | derived subtraction |
| Cache-write input tokens | 0 | measured stage aggregate |
| Output tokens | 7,679 | measured stage aggregate |
| Reasoning output tokens | 2,961 | measured stage aggregate |

### Stage 2e — independent charter rereview

- Model: `gpt-5.5`, high reasoning.
- Result: clean charter verdict; worktree remained clean.
- Previous producer-completeness and pending-assignment ownership findings are
  resolved.
- Residual requirement: each phase still needs a phase plan, independent plan
  review, implementation, committed-candidate verification, and implementation
  review.

| Field | Value | Status |
|---|---:|---|
| Input tokens | 1,837,744 | measured stage aggregate |
| Cached input tokens | 1,639,936 | measured stage aggregate |
| Uncached input tokens | 197,808 | derived subtraction |
| Cache-write input tokens | 0 | measured stage aggregate |
| Output tokens | 11,018 | measured stage aggregate |
| Reasoning output tokens | 5,207 | measured stage aggregate |

## Checkpoint after clean charter

Measured completed-turn total:

| Field | Value |
|---|---:|
| Completed turns | 8 |
| Input tokens | 11,955,064 |
| Cached input tokens | 11,103,104 |
| Uncached input tokens | 851,960 |
| Cache-write input tokens | 0 |
| Output tokens | 91,566 |
| Reasoning output tokens | 41,461 |

These totals exclude interrupted/capacity-failed attempts because Codex emitted
no usage object for them.

Implementation prerequisite check:

- `cargo`: unavailable on PATH;
- `docs/MagicCompRules.txt`: missing in the isolated worktree;
- generated card data: missing;
- root filesystem: 4.5 GB free (95% used).

Do not start Phase 1 implementation on this host until toolchain/build storage
is provisioned. A cold phase.rs Rust build is likely to exhaust the remaining
disk and would make verification evidence unreliable or impossible.
