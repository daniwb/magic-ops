# Factory NG model-routing benchmark v1

> Archived 2026-09-01 with its prompt, runner, model matrix, results, and
> report. Use `docs/benchmarks/model-routing-v2/` for current routing evidence.

This benchmark compares models on the same frozen target-player-draw ticket at
repository commit `6d85a3d649103d8f3a50fb6436ed266c77b0942a`.

The candidate must repair the complete production path, not merely make the
parser emit a plausible record. Acceptance uses harness-owned tests for:

1. exact positive and adjacent-negative Map behavior;
2. DSL conversion into a player-targeted draw spell;
3. cast and resolution against the chosen player with populated libraries;
4. parser and cards-package regression;
5. scope discipline (`backend/game` and `backend/cardfns` are forbidden).

Headline metrics are wall-clock time, calculated marginal cost, and mechanical
quality. Local Qwen has zero API cost; electricity and hardware amortization are
reported separately when measurements exist. Cached input is a subset of input
and is never added twice.

This is a screening benchmark, not a claim of general model superiority. A
second unseen ticket is required before a routing policy is promoted.
