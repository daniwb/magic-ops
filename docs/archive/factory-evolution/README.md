# Factory evolution archive

Archived 2026-09-01. These documents preserve the decisions, experiments,
failures, and measurements that led to Factory NG. They are historical
evidence, not current operating instructions. Current authority is
[`RUNBOOK.md`](../../../RUNBOOK.md) plus
[`docs/factory-ng/CURRENT.md`](../../factory-ng/CURRENT.md).

## Timeline

| Date | Archived document | What it records | Lesson retained in NG |
|---|---|---|---|
| 2026-07-25 | [`HANDOFF-record-first-2026-07-25.md`](HANDOFF-record-first-2026-07-25.md) | Record-first conversion, agentic worker costs, local-model experiments, and dispatcher-era handoff | Deterministic preparation, honest token accounting, and narrow model authority |
| 2026-07-31 | [`cardslist-test-sample-20260731.md`](cardslist-test-sample-20260731.md) | A manually assembled card sample and difficulty grouping | Corpus evidence must replace subjective ticket difficulty |
| 2026-08-07 | [`pipeline-workflows-2026-08-07.md`](pipeline-workflows-2026-08-07.md) | Staged Map/Engine/Handler execution and its measured cost reduction | The proven staged harness remains NG's execution core |
| 2026-08-09 | [`operator-projects-2026-08-09.md`](operator-projects-2026-08-09.md) | Manually selected class rounds and miss backlogs | Work must be compiled from current measured ground truth |
| 2026-08-16 | [`factory-redesign-2026-08-16.md`](factory-redesign-2026-08-16.md) | Atomic capability and attempt-ledger migration | Atomic dependencies and immutable outcomes replace free-text handoffs |
| 2026-08-27 | [`model-routing-v1/`](model-routing-v1/README.md) | First cross-model routing benchmark and its complete reproducibility bundle | External behavior gates matter more than plausible-looking patches |
| 2026-08-27 | [`factory-ng-plan-2026-08-27.md`](factory-ng-plan-2026-08-27.md) | The original ground-truth Factory NG design discussion | TicketSpec provenance, model-neutral tickets, profile-specific execution, and one dashboard |
| pre-NG | [`README-pre-ng.md`](README-pre-ng.md) | Repository entry point for the dispatcher/orchestrator era | Preserved only to reconstruct the former system boundary |

## Archive policy

- Files are moved here intact except for an archive banner and repaired links.
- Do not edit archived claims to match present behavior; add a new reflection
  document instead.
- Keep receipts, measurements, TicketSpecs, contracts, Skills, and the current
  routing benchmark in their existing locations because they remain live NG
  evidence or executable inputs.
- Historical session artifacts under `docs/sessions/`, experiments under
  `docs/experiments/`, and dated reports under `reports/` are already
  self-identifying evidence collections and remain in place.
