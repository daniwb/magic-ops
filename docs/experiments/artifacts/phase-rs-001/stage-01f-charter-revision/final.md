# Phase Charter: issue #7954 — overflow-safe post-replacement life changes

Base SHA: `fae406c4603f450797014f3ac8e8818b3d36c2a4`  
Mode: charter revision only. No implementation, review invocation, publication, commit, push, or source edit. Worktree observed clean before chartering and remained clean.

## Premise Verification

Preserve the draft premise:

- Issue #7954 reports a production panic at `apply_life_loss_after_replacement` with `ResourceOverflow` while AI combat simulation processes approximately 2.49 billion damage.
- Base contains the failing cast/negation expression: `ResolvedPlayerEdit::Life { delta: -(loss_amount as i32) }`.
- The diagnostic proves the production route reached `GameState::apply_resolved_player_edit`.
- Card premise was verified against Scryfall:
  - Thrakkus the Butcher doubles the power of each Dragon you control when Thrakkus attacks.
  - Miirym, Sentinel Wyrm creates a nonlegendary token copy when another nontoken Dragon you control enters.
- No serialized game state, deck list, or 179-creature fixture was attached, so exact production replay remains unavailable at planning time.

## Applicable Skills

Preserve these skills for phase plans and implementation:

- `engine-planner`: this charter revision stage and each phase-plan stage.
- `add-replacement-effect`: applicable because the failing delivery consumes replacement-processed `LifeLoss` / `LifeGain` events. No new replacement event, registry entry, parser route, or handler is planned.
- `project-reference`: verification and Tilt/cargo workflow.
- Not applicable unless a later phase-plan changes scope: `add-engine-variant`, `add-engine-effect`, `oracle-parser`, `card-test`, frontend, AI-feature, and interactive-effect skills.

Implementation-time CR verification remains required before adding or changing CR annotations. `docs/MagicCompRules.txt` must be fetched and grepped before any CR number is written.

## Feasibility

A green-tree phased split exists. The repaired stable seams are:

- Phase 1 changes the `ResolvedPlayerEdit::Life` payload to `LifeChange` and includes every compile-required `ResolvedPlayerEdit::Life` construction-site migration in the same phase. No raw-field producer migration is deferred past the payload change.
- `PendingLifeTotalAssignment` is not partially migrated in Phase 1. Its type, serialization, producer, and consumer surfaces are assigned coherently to Phase 4 with the life-total assignment work.
- Post-replacement production event projection can land after the carrier and producer compatibility seam.
- Legacy `LifeChanged.amount` consumers can be hardened independently once the projection helper exists.
- Remaining difference-producing life effects and derived projections can land separately because they depend only on `LifeChange`.
- Threshold comparisons can land last and touch only affordability/replacement condition checks.

No strict-failure parser seam is needed because parser behavior and card-support coverage remain unchanged.

## Phase 1 — Exact Life-Change Carrier, Resolved Replay, And Producer Compatibility

Goal: introduce the exact signed life-change domain, change `ResolvedPlayerEdit::Life` to use it, make resolved player life replay safe, and migrate every compile-required `ResolvedPlayerEdit::Life` producer so the tree stays green.

Scope-path hints:

- `crates/engine/src/types/player.rs`
- `crates/engine/src/types/resolved_commands.rs`
- `crates/engine/src/types/game_state.rs`
- `crates/engine/src/game/library.rs`
- `crates/engine/src/game/effects/life.rs`
- `crates/engine/src/game/engine_debug.rs`
- `crates/engine/tests/integration/cr733_resolved_commands_p2.rs`

Verification plan:

- `cargo fmt --all`.
- If Tilt is available: `./scripts/tilt-wait.sh --timeout 240 clippy test-engine`.
- If Tilt is unavailable: `cargo clippy --all-targets -- -D warnings` and `cargo test -p phase-engine`.
- Add/update integration assertions for extreme resolved life edit gain/loss saturation, exact per-turn history saturation, replay equivalence, legacy numeric JSON compatibility, oversized JSON rejection, unknown-player failure, and zero-command failure.
- Add/retain compile coverage for all `ResolvedPlayerEdit::Life` construction sites: post-replacement gain, post-replacement loss, debug set-life, resolved-command fixtures, game-state tests, library tests, and integration tests.

Deferrals:

- DEFERRED(phase 2): bounded `GameEvent::LifeChanged` projection for post-replacement gain/loss events.
- DEFERRED(phase 3): all `LifeChanged.amount` magnitude-consumer hardening.
- DEFERRED(phase 4): `PendingLifeTotalAssignment` type, serialization, producer, and consumer migration; exchange/double/preview/analysis/team/quantity difference producers.
- DEFERRED(phase 5): life-cost and life-threshold comparison hardening.

Seam notes:

- Keep `ResolvedPlayerEdit::Life` as the single replay authority.
- Retain serialized `delta` field name and numeric JSON shape.
- No compile-required `ResolvedPlayerEdit::Life` producer remains deferred after this phase.
- In `game/effects/life.rs`, Phase 1 is limited to producer compatibility for resolved edits; event projection remains Phase 2 and life-total assignment tail migration remains Phase 4.
- `PendingLifeTotalAssignment.remaining` stays in its existing representation until Phase 4.

Phase-fit proof:

- Units: 1.
- Non-test scope paths: 6.
- T1 is false and T2 is false; therefore T1∧T2 is false. No recursive split required.

## Phase 2 — Post-Replacement Delivery And Bounded Event Projection

Goal: convert final replacement-processed life gain/loss events into exact `LifeChange` for resolved edits and emit bounded signed `LifeChanged.amount` projections that never reverse sign and never emit `i32::MIN`.

Scope-path hints:

- `crates/engine/src/types/events.rs`
- `crates/engine/src/game/effects/life.rs`
- `crates/engine/tests/integration/cr733_resolved_commands_p2.rs`
- `crates/engine/tests/integration/swarm_combat_witness.rs`

Verification plan:

- `cargo fmt --all`.
- If Tilt is available: `./scripts/tilt-wait.sh --timeout 240 clippy test-engine`.
- If Tilt is unavailable: `cargo clippy --all-targets -- -D warnings` and `cargo test -p phase-engine`.
- Add/update assertions that `u32::MAX` loss journals exact negative magnitude, stores saturated life, emits `-i32::MAX`, never positive and never `i32::MIN`.
- Add symmetric `u32::MAX` gain assertion emitting `i32::MAX`.
- Add AI swarm witness using two unblocked `i32::MAX`-power attackers, asserting lethal certification, `candidate_clone_applies == 1`, and unchanged input state.
- Preserve existing two-replacement resume tests as provenance guards.

Deferrals:

- DEFERRED(phase 3): consumers still using raw `LifeChanged.amount` magnitude operations.
- DEFERRED(phase 4): `PendingLifeTotalAssignment` and non-replacement life difference producers in assignment, exchange, double, preview, analysis, team totals, and quantity.
- DEFERRED(phase 5): threshold comparisons in costs and replacement conditions.

Seam notes:

- `game/effects/life.rs` is shared with phases 1 and 4. Phase 2 should touch only direct post-replacement delivery/projection surfaces and must re-read the phase 1 result before editing.
- Replacement registry, parser routing, and post-replacement effect plumbing remain unchanged.
- Coverage remains unchanged because no Oracle parsing support changes.

Phase-fit proof:

- Units: 1.
- Non-test scope paths: 2.
- T1 is false and T2 is false; therefore T1∧T2 is false. No recursive split required.

## Phase 3 — `LifeChanged.amount` Magnitude Consumers

Goal: route every bounded event-magnitude consumer through the shared helper and make hostile/legacy `i32::MIN` events safe.

Scope-path hints:

- `crates/engine/src/game/targeting.rs`
- `crates/engine/src/game/trigger_matchers.rs`
- `crates/engine/src/game/effects/mod.rs`
- `crates/engine/src/game/log.rs`
- `crates/engine/src/parser/oracle_nom/quantity.rs`
- `crates/engine/tests/integration/cr733_resolved_commands_p2.rs`

Verification plan:

- `cargo fmt --all`.
- If Tilt is available: `./scripts/tilt-wait.sh --timeout 240 clippy test-engine card-data`.
- If Tilt is unavailable: `cargo clippy --all-targets -- -D warnings`, `cargo test -p phase-engine`, and `./scripts/gen-card-data.sh`.
- Assert event-context extraction returns `i32::MAX` for saturated loss.
- Assert trigger matcher amount constraints do not panic on legacy `i32::MIN`.
- Assert previous-effect life gained/lost accumulation saturates across multiple max events.
- Assert log formatting renders max and legacy-min loss magnitudes without panic.
- Confirm parser/card-support delta is zero; the parser touch is documentation only.

Deferrals:

- DEFERRED(phase 4): remaining unsafe raw life-total differences outside `LifeChanged.amount` consumers, including `PendingLifeTotalAssignment`.
- DEFERRED(phase 5): bounded `u32` threshold comparisons.

Seam notes:

- `game/effects/mod.rs` is a shared effect dispatcher surface; restrict this phase to previous-effect life amount accumulation.
- `parser/oracle_nom/quantity.rs` change is comment-only and must not alter nom behavior or support coverage.
- Hostile `i32::MIN` events are legacy/malformed direct fixtures; production projection from phase 2 must not emit them.

Phase-fit proof:

- Units: 1.
- Non-test scope paths: 5.
- T1 is false and T2 is false; therefore T1∧T2 is false. No recursive split required.

## Phase 4 — Pending Life-Total Assignment, Difference Producers, And Derived Projections

Goal: migrate all “make life equal to X”, paused life-total assignment tails, exchange, double-life, preview, analysis, team-total, and quantity paths to direction-safe exact differences and saturating projections.

Scope-path hints:

- `crates/engine/src/game/effects/life.rs`
- `crates/engine/src/types/game_state.rs`
- `crates/engine/src/types/resolution.rs`
- `crates/engine/src/game/effects/exchange_life.rs`
- `crates/engine/src/game/effects/double.rs`
- `crates/engine/src/game/preview.rs`
- `crates/engine/src/analysis/resource.rs`
- `crates/engine/src/game/players.rs`
- `crates/engine/src/game/quantity.rs`
- `crates/engine/tests/integration/cr733_resolved_commands_p2.rs`

Verification plan:

- `cargo fmt --all`.
- If Tilt is available: `./scripts/tilt-wait.sh --timeout 240 clippy test-engine`.
- If Tilt is unavailable: `cargo clippy --all-targets -- -D warnings` and `cargo test -p phase-engine`.
- Assert `PendingLifeTotalAssignment` serializes and restores with the new exact remaining-delta representation.
- Assert pending life-total assignment resumes after replacement with exact remaining `LifeChange`.
- Assert exchange endpoints at `i32::MIN` / `i32::MAX` do not overflow or reverse direction.
- Assert double life at `i32::MIN` loses exact `2_147_483_648`.
- Assert preview reports exact `i64` deltas.
- Assert `grown_life_deltas` reports only positive exact/saturated magnitudes.
- Assert team totals and `LifeAboveStarting` saturate.

Deferrals:

- DEFERRED(phase 5): affordability and replacement-condition threshold comparisons.

Seam notes:

- This phase owns the full `PendingLifeTotalAssignment` migration: struct field type in `types/game_state.rs`, resolution-state serialization and legacy fixtures in `types/resolution.rs`, producer construction in `apply_life_totals_assignment`, and consumer draining in `drain_pending_life_total_assignment`.
- This phase reuses `game/effects/life.rs` after phases 1 and 2; implementation must re-read the latest file before editing.
- Debug set-life `ResolvedPlayerEdit::Life` producer compatibility already landed in Phase 1 and is not repeated here.
- No event projection contract changes beyond using the already-landed `LifeChange` utilities.
- Adjacent resources such as energy, counters, and speed stay on existing checked-precondition paths.

Phase-fit proof:

- Units: 1.
- Non-test scope paths: 9.
- T1 is false and T2 is false; therefore T1∧T2 is false. No recursive split required.

## Phase 5 — Bounded Life Threshold Comparisons

Goal: remove lossy `amount as i32` comparisons from life affordability and replacement threshold conditions.

Scope-path hints:

- `crates/engine/src/game/life_costs.rs`
- `crates/engine/src/game/replacement.rs`
- `crates/engine/tests/integration/cr733_resolved_commands_p2.rs`

Verification plan:

- `cargo fmt --all`.
- If Tilt is available: `./scripts/tilt-wait.sh --timeout 240 clippy test-engine card-data`.
- If Tilt is unavailable: `cargo clippy --all-targets -- -D warnings`, `cargo test -p phase-engine`, and `./scripts/gen-card-data.sh`.
- Assert `can_pay_life_cost` rejects `u32::MAX` when team life is `i32::MAX`.
- Assert ordinary affordable life payment remains unchanged.
- Assert `UnlessPlayerLifeAtMost { amount: u32::MAX }` suppresses replacement on ordinary life totals.
- Assert a small-threshold sibling still distinguishes above/below correctly.
- Run final `rg` sweeps over touched life paths for `as i32`, `amount.abs()`, unary negation, and raw life subtraction; justify every remaining conversion.
- Finish with `git status --short`.

Deferrals:

- None. This phase closes the full deferral list from the draft plan.

Seam notes:

- `game/replacement.rs` modification is limited to existing `UnlessPlayerLifeAtMost` comparison logic.
- No replacement condition variant, registry entry, parser route, or candidate-count behavior changes.
- Existing replacement provenance and multi-replacement tests remain authoritative.

Phase-fit proof:

- Units: 1.
- Non-test scope paths: 2.
- T1 is false and T2 is false; therefore T1∧T2 is false. No recursive split required.

## Dependency Order

1. Phase 1 must land first because `LifeChange`, the resolved replay payload, and all compile-required `ResolvedPlayerEdit::Life` producer migrations are the shared green-tree infrastructure.
2. Phase 2 depends on phase 1 for exact post-replacement `LifeChange` construction and bounded event projection.
3. Phase 3 depends on phase 2 for the shared event magnitude helper and production bounded projection contract.
4. Phase 4 depends on phase 1 for `LifeChange`, and should run after phase 2 and phase 3 to avoid concurrent edits in `game/effects/life.rs`.
5. Phase 5 depends on phase 1 only, but lands last to keep threshold-only behavior isolated and close the full task.

## Global Recursive Phase-Fit Proof

Original draft fired phase-fit because T1=true with 5 units and T2=true with 21 non-test scope paths.

Revised partition result:

| Phase | Units | Non-test paths | T1 | T2 | T1∧T2 |
|---|---:|---:|---|---|---|
| 1 | 1 | 6 | false | false | false |
| 2 | 1 | 2 | false | false | false |
| 3 | 1 | 5 | false | false | false |
| 4 | 1 | 9 | false | false | false |
| 5 | 1 | 2 | false | false | false |

Unique non-test scope across the full charter remains 21 paths. Every individual phase is below the conjunction threshold. Since no phase fires T1 and T2 together, recursive phase-fit terminates at all five phase leaves.