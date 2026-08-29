# Plan: issue #7954 — overflow-safe post-replacement life changes

Base: `fae406c4603f450797014f3ac8e8818b3d36c2a4`  
Mode: planning only. No source edits, commits, pushes, publication, self-review, or `review-engine-plan` invocation.

## Premise Verification

- The checkout is at the requested base SHA and the worktree is clean.
- Issue #7954 reports a production panic at `apply_life_loss_after_replacement` with `ResourceOverflow` while an AI combat simulation processes approximately 2.49 billion damage.
- The requested base contains the failing expression:
  `ResolvedPlayerEdit::Life { delta: -(loss_amount as i32) }`.
- The diagnostic proves the production route reached `GameState::apply_resolved_player_edit`; this is not only a synthetic arithmetic concern.
- The reported card premise is consistent with current Oracle text:
  - [Thrakkus the Butcher](https://api.scryfall.com/cards/named?exact=Thrakkus%20the%20Butcher): doubles the power of each Dragon you control when Thrakkus attacks.
  - [Miirym, Sentinel Wyrm](https://api.scryfall.com/cards/named?exact=Miirym%2C%20Sentinel%20Wyrm): creates a nonlegendary token copy when another nontoken Dragon you control enters.
- Static inspection identifies two defects in the same class:
  - cumulative negative deltas can make `Player::life.checked_add(delta)` fail below `i32::MIN`;
  - a single post-replacement amount above `i32::MAX` can reverse direction through `as i32`.
- No serialized game state, deck list, or 179-creature fixture was attached, so the exact production board cannot be replayed during planning.

## Applicable Skills

- `engine-planner`: primary planning workflow.
- `add-replacement-effect`: applies because the failing delivery consumes a replacement-processed `LifeLoss` event. No new replacement event, condition, registry entry, parser route, or replacement handler is planned.
- `project-reference`: used for repository-safe verification conventions.
- Implementation-time CR verification is required before any CR annotation changes. `docs/MagicCompRules.txt` is absent in this checkout, so implementation must fetch and grep the rules before writing or changing any CR annotation.
- Not applicable:
  - `add-engine-variant`: no enum variant is proposed.
  - `add-engine-effect`: no new effect or stub completion.
  - `oracle-parser`: no parser behavior changes; only one stale parser doc comment is in scope.
  - `card-test`, frontend, AI-feature, and interactive-effect skills: no cast-pipeline card test, UI, policy, or new choice-state work.

## Pattern Coverage

This covers the engine-wide life-change class, not Thrakkus specifically:

- combat and noncombat damage to players;
- direct `GainLife` and `LoseLife` effects;
- replacement-modified gain/loss;
- lifelink;
- pay-life costs;
- set, exchange, redistribute, and double-life operations;
- Yurlok-style empty-mana life loss;
- resolved-command replay;
- AI combat simulations, loop analysis, action preview, logs, triggers, and event-context amount consumers.

The affected card class is thousands of cards: damage, gain-life, lose-life, and pay-life cards overlap heavily, but all converge on the same life authorities.

## Analogous Trace

Two existing patterns were traced.

1. Post-replacement player damage:

   `crates/engine/src/game/combat_damage.rs::apply_combat_damage`  
   → `crates/engine/src/game/effects/deal_damage.rs::apply_damage_after_replacement`  
   → `crates/engine/src/game/effects/life.rs::apply_damage_life_loss`  
   → `crates/engine/src/game/replacement.rs::replace_event`  
   → `crates/engine/src/game/effects/life.rs::apply_life_loss_after_replacement`  
   → `crates/engine/src/types/game_state.rs::resolve_and_apply_player_edit`  
   → `ResolvedRulesJournal::record_player_edit`.

   Replacement-choice resume sibling:

   `crates/engine/src/game/engine_replacement.rs::handle_replacement_choice`  
   → `apply_life_gain_after_replacement` / `apply_life_loss_after_replacement`.

2. Existing bounded-integer policy:

   `crates/engine/src/game/arithmetic.rs`  
   → saturating P/T and quantity projections  
   → layer/quantity consumers and boundary tests.

The plan extends the explicit saturation policy while retaining exact post-replacement life-change magnitude in the semantic command.

## Building Blocks

- Preserve `ProposedEvent::LifeGain/LifeLoss { player_id, amount: u32, applied }` as the replacement pipeline authority.
- Preserve `apply_life_gain`, `apply_life_loss`, and their post-replacement delivery functions as the only rules-facing life mutation paths.
- Preserve `ResolvedPlayerEdit` and `resolve_and_apply_player_edit` as the single journaling and mutation authority.
- Introduce one typed scalar building block, `LifeChange`, rather than duplicating casts and subtraction logic:
  - exact signed domain `[-u32::MAX, u32::MAX]`;
  - constructors `gain(u32)`, `loss(u32)`, and `between(new: i32, old: i32)`;
  - accessors `signed_i64()`, `magnitude()`, `is_zero()`, and direction predicates;
  - explicit saturated projections for stored life, `GameEvent::LifeChanged`, preview, analysis, and comparisons.
- Add a single shared helper for `LifeChanged.amount` magnitude consumers, so no production consumer calls `abs()` or unary negation on the raw event amount.
- Reuse `team_life_total`, replacement continuations, `PendingLifeTotalAssignment`, and the resolved journal rather than adding another replay or delivery mechanism.

## Bounded Event Projection Contract

`LifeChange` is the exact semantic authority. `GameEvent::LifeChanged.amount` is a bounded signed projection for legacy event consumers, logs, trigger matching, and `EventContextAmount`.

Precise invariant:

- Exact life-change domain: `LifeChange` stores every final post-replacement gain/loss exactly in `[-u32::MAX, u32::MAX]`.
- Stored life projection: `Player::life: i32` is updated with saturating semantics and may become `i32::MIN` or `i32::MAX`.
- Per-turn histories: `life_gained_this_turn` and `life_lost_this_turn` add the exact `u32` magnitude with `saturating_add`.
- Event projection:
  - gain `n` emits `min(n, i32::MAX as u32) as i32`;
  - loss `n` emits `-min(n, i32::MAX as u32) as i32`;
  - production helpers never emit `i32::MIN` for `LifeChanged.amount`;
  - zero projects to `0`; no resolved command is recorded. Do not introduce unrelated zero-event behavior changes.
- Consumer rule:
  - every magnitude consumer must call the shared helper;
  - the helper returns `i32::MAX` for either saturated production events or hostile/legacy `i32::MIN` events;
  - sign-only consumers may continue checking `< 0`, `> 0`, or `== 0`.

All current `LifeChanged.amount` magnitude consumers are in scope:

- `crates/engine/src/game/targeting.rs::extract_amount_from_event`
- `crates/engine/src/game/trigger_matchers.rs::life_amount_matches`
- `crates/engine/src/game/effects/mod.rs::previous_effect_amount_from_events`
- `crates/engine/src/game/log.rs::format_segments`

Audited sign-only or signed-delta consumers are not magnitude consumers and do not need magnitude rewrites: `log::tone`, `effects::effect_had_impact`, `triggers` speed trigger routing, `trigger_index`, combat event ordering assertions, public-state dirty routing, and signed `i64` analysis axes.

## Logic Placement

- `types/player.rs`: define `LifeChange`, because it describes the player-life domain, not one effect.
- `types/resolved_commands.rs`: use `LifeChange` inside existing `ResolvedPlayerEdit::Life`.
- `types/game_state.rs`: apply exact semantic change to bounded stored life and journal it.
- `types/events.rs`: document `LifeChanged.amount` and expose the shared bounded magnitude helper.
- `game/effects/life.rs`: translate final replacement events into `LifeChange`, emit bounded event projections, and share dispatch for precomputed life changes.
- `game/targeting.rs`, `game/trigger_matchers.rs`, `game/effects/mod.rs`, `game/log.rs`: consume `LifeChanged.amount` through the shared helper.
- `game/effects/exchange_life.rs`, `game/effects/double.rs`, `game/engine_debug.rs`, `game/preview.rs`, `analysis/resource.rs`: compute life differences through `LifeChange::between` or direction-safe helpers.
- `game/players.rs` and `game/quantity.rs`: keep derived life projections saturating.
- `game/life_costs.rs` and `game/replacement.rs`: compare bounded team life against `u32` thresholds without lossy casts.
- No logic moves into WASM, server, AI policy, or frontend code.

## Rust Idioms

- Keep the existing parameterized `ResolvedPlayerEdit::Life` variant; do not add gain/loss siblings.
- Use a private-field newtype for `LifeChange`, not a boolean direction flag.
- Use `i64` internally only as the exact signed carrier for a `u32` magnitude.
- Use `i64::from`, `unsigned_abs`, `try_from`, checked/saturating helpers, and explicit clamps.
- Use `saturating_add` or explicit folded saturation for cumulative projections.
- No lossy `as i32`, unchecked negation, or wrapping arithmetic in touched life paths.
- Keep matches exhaustive.
- Retain serialized `delta` field name and numeric JSON shape for compatibility.

## Nom Compliance

No parser behavior changes. The only parser-path touch is a stale doc comment in `crates/engine/src/parser/oracle_nom/quantity.rs` that currently describes `LifeChanged` extraction as `amount.abs()`. Update the comment to name the shared magnitude helper. No detection, dispatch, classification, or nom parser changes are planned.

## Extension vs Creation

This extends two established patterns:

- resolved semantic player edits remain the sole final mutation authority;
- bounded engine scalar projections saturate rather than wrap or panic.

`LifeChange` is justified because gain, loss, difference computation, replay, preview, analysis, and event consumers currently reproduce unsafe signed/unsigned conversions independently.

## Variant Discoverability

No engine enum variant is added, so `cargo engine-inventory` and `add-engine-variant` are not required. `ResolvedPlayerEdit::Life` changes only its payload type.

## Identity / Provenance Contract

- Authority: final `ProposedEvent::LifeGain` or `ProposedEvent::LifeLoss`.
- Identity: `player_id` is latched when the event is proposed and remains unchanged through replacement ordering.
- Magnitude: final post-replacement `u32 amount` is converted exactly to `LifeChange`.
- Binding time: after replacement pipeline returns `Execute`, or when stored pending replacement resumes.
- Semantics: recipient and magnitude are snapshotted; delivery must not rescan targets, controllers, or replacement sources.
- Storage:
  - immediate path: local final proposed event;
  - deferred path: existing `PendingReplacement`;
  - replay: `ResolvedPlayerEdit::Life { delta: LifeChange }`;
  - paused life-total permutation: `PendingLifeTotalAssignment`.
- Consumption: `apply_life_gain_after_replacement` or `apply_life_loss_after_replacement`, exactly once.
- Expiration: consumed event/continuation is removed; existing applied-replacement keys prevent reapplication.
- Invalid recipient: unknown player remains a typed invariant error. Saturation must not conceal identity failures.
- Multi-authority hostile guard: retain and run existing two-replacement tests where noncommuting life-loss replacements compete, proving the selected replacement’s latched event is delivered.

## Scope Matrix

| Boundary | Reachable cases | Planned treatment |
|---|---|---|
| Event kind | `LifeGain`, `LifeLoss` | Both construct exact `LifeChange`; zero remains a no-op command |
| Replacement result | `Execute`, `Prevented`, `NeedsChoice` | Only `Execute` mutates; existing continuation ownership remains unchanged |
| Origin | combat damage, noncombat damage, direct effect, lifelink, cost, mana loss, set/exchange/double | All converge on existing life authorities |
| Recipient | individual player, shared-life team member | Exact player remains latched; derived team totals saturate safely |
| Magnitude | normal, `i32::MAX`, `i32::MAX + 1`, `u32::MAX`, cumulative boundary crossing | Preserve exact semantic magnitude; explicitly saturate bounded projections |
| Stored state | `Player::life: i32`, per-turn `u32` histories | Saturating updates; never wrap or panic |
| Event projection | `GameEvent::LifeChanged.amount: i32` | Preserve sign, clamp magnitude to `i32::MAX`, never produce `i32::MIN` |
| Replay | live command, legacy serialized numeric delta, malformed out-of-domain delta | Exact replay, backward-compatible wire shape, reject invalid domain |
| Analysis | AI swarm clone, loop-growth snapshot, preview diff | Replace raw subtraction with the shared typed difference |
| Adjacent resources | energy, counters, speed | Unchanged checked-precondition behavior |

## Sizing

Phase-fit T1/T2 application:

- T1 is true: the plan contains five independently testable units.
- T2 is true: expected non-test scope-path count is 21, which is `>= 13` under the engine-implementer counting rule. The two integration test files are listed separately and excluded from T2 as test fixtures. No regenerated pipeline data is planned.
- Because T1 and T2 are both true, the phase-fit gate fires. This ordinary plan is not a charter; the outer engine-implementer controller should partition using the dependency seams below.

Unit U1 — exact life-change carrier and resolved replay

- Behavior: represent final life changes exactly and apply them safely to `Player::life`, per-turn histories, and journal replay.
- Surfaces: `types/player.rs`, `types/resolved_commands.rs`, `types/game_state.rs`, `types/resolution.rs`, `game/library.rs`.
- Discriminating tests: extreme gain/loss commands saturate stored life, preserve exact history magnitude, replay identically, deserialize legacy numeric deltas, and reject out-of-domain JSON.
- Dependencies: none.

Unit U2 — post-replacement delivery and bounded event projection

- Behavior: convert final replacement-processed gain/loss events to exact `LifeChange` and emit signed bounded `LifeChanged` projections that never reverse sign and never use `i32::MIN`.
- Surfaces: `game/effects/life.rs`, `types/events.rs`, replacement resume call sites through existing imports.
- Discriminating tests: `u32::MAX` loss emits negative `-i32::MAX`, stores exact `-u32::MAX` journal magnitude, saturates stored life, and replays; symmetric gain emits `i32::MAX`; AI swarm witness with two unblocked `i32::MAX`-power attackers completes and certifies lethal.
- Dependencies: U1.

Unit U3 — `LifeChanged.amount` magnitude consumers

- Behavior: every magnitude consumer uses one helper and remains safe for saturated production events and hostile/legacy `i32::MIN` events.
- Surfaces: `game/targeting.rs`, `game/trigger_matchers.rs`, `game/effects/mod.rs`, `game/log.rs`, `parser/oracle_nom/quantity.rs` doc comment.
- Discriminating tests: `extract_amount_from_event` returns `i32::MAX` for saturated loss; trigger amount constraints do not panic on legacy `i32::MIN`; previous-effect life lost/gained accumulation saturates across multiple max events; log formatting renders max/legacy-min loss magnitude without panic.
- Dependencies: U2 for the production projection helper; tests may construct hostile events directly.

Unit U4 — life-total assignment, difference producers, and derived projections

- Behavior: all “make life equal to X” and snapshot-difference paths compute exact bounded differences without overflowing.
- Surfaces: `game/effects/life.rs`, `game/effects/exchange_life.rs`, `game/effects/double.rs`, `game/engine_debug.rs`, `game/preview.rs`, `analysis/resource.rs`, `game/players.rs`, `game/quantity.rs`.
- Discriminating tests: pending life-total assignment resumes after replacement with exact remaining `LifeChange`; exchange/stat and exchange-total endpoints at `i32::MIN/i32::MAX` do not overflow; double life at `i32::MIN` loses exact `2_147_483_648`; preview reports exact `i64` deltas; `grown_life_deltas` reports only positive exact/saturated magnitudes; team totals and `LifeAboveStarting` saturate.
- Dependencies: U1.

Unit U5 — bounded life threshold comparisons

- Behavior: affordability and life-threshold replacement conditions compare `u32` thresholds against bounded team life without `amount as i32`.
- Surfaces: `game/life_costs.rs`, `game/replacement.rs`.
- Discriminating tests: `can_pay_life_cost` rejects `u32::MAX` when team life is `i32::MAX`; paying ordinary affordable life remains unchanged; `UnlessPlayerLifeAtMost { amount: u32::MAX }` suppresses the replacement on ordinary life totals, while a small threshold sibling still behaves normally.
- Dependencies: U1 only for shared comparison helpers if placed there; otherwise independent.

Preferred T3 seams:

- U1 is infrastructure and should land before U2/U3/U4/U5.
- U2 and U3 form a natural seam: production projection first, then consumers.
- U4 and U5 are independent after U1 and can be separate phases if the controller charters the run.

## Exact Proposed Scope Paths

Production/type/doc paths:

- `crates/engine/src/types/player.rs`
- `crates/engine/src/types/resolved_commands.rs`
- `crates/engine/src/types/game_state.rs`
- `crates/engine/src/types/resolution.rs`
- `crates/engine/src/types/events.rs`
- `crates/engine/src/game/effects/life.rs`
- `crates/engine/src/game/effects/exchange_life.rs`
- `crates/engine/src/game/effects/double.rs`
- `crates/engine/src/game/engine_debug.rs`
- `crates/engine/src/game/library.rs`
- `crates/engine/src/game/life_costs.rs`
- `crates/engine/src/game/players.rs`
- `crates/engine/src/game/preview.rs`
- `crates/engine/src/analysis/resource.rs`
- `crates/engine/src/game/targeting.rs`
- `crates/engine/src/game/trigger_matchers.rs`
- `crates/engine/src/game/effects/mod.rs`
- `crates/engine/src/game/log.rs`
- `crates/engine/src/game/replacement.rs`
- `crates/engine/src/game/quantity.rs`
- `crates/engine/src/parser/oracle_nom/quantity.rs`

Integration test paths:

- `crates/engine/tests/integration/cr733_resolved_commands_p2.rs`
- `crates/engine/tests/integration/swarm_combat_witness.rs`

No replacement registry, parser behavior, adapter, frontend, AI-policy, or card-data source changes are proposed.

## Implementation Steps

1. CR verification prerequisite

   - Fetch `docs/MagicCompRules.txt` with the repository script.
   - Verify every retained or new annotation before writing it, especially relevant life, damage, replacement, exchange, and state-based-action rules.
   - Do not write an annotation whose exact rule text cannot be verified.

2. Add the typed life-change value

   In `crates/engine/src/types/player.rs`:

   - Add `LifeChange`, backed privately by `i64`.
   - Constrain serialization/deserialization to signed `u32` magnitude.
   - Add constructors for gain, loss, and exact difference between two `i32` totals.
   - Add exact magnitude/direction accessors and explicit projection/application methods.
   - Preserve zero as representable internally; resolved-journal validation continues rejecting zero commands.

3. Thread the type through replay and continuations

   In `types/resolved_commands.rs`, `types/game_state.rs`, and `types/resolution.rs`:

   - Change `ResolvedPlayerEdit::Life { delta }` from raw `i32` to `LifeChange`, retaining field name and numeric JSON.
   - Separate life no-op validation from energy/counter raw `i32` validation.
   - Change `PendingLifeTotalAssignment.remaining` to carry `LifeChange`.
   - Update construction sites found by `rg "ResolvedPlayerEdit::Life|PendingLifeTotalAssignment"`.
   - Add legacy JSON and malformed out-of-domain tests.

4. Make resolved life application total

   In `types/game_state.rs`:

   - Apply `LifeChange` to `Player::life` with saturating stored projection.
   - Update `life_gained_this_turn` / `life_lost_this_turn` using exact `u32` magnitude and `saturating_add`.
   - Continue returning `UnknownPlayer` and `ZeroDelta` appropriately.
   - Leave energy, counters, and speed on existing checked-precondition paths.
   - Record exact `LifeChange` in the journal after successful application.

5. Define and use bounded `LifeChanged` projection

   In `types/events.rs` and `game/effects/life.rs`:

   - Document `LifeChanged.amount` as a bounded event projection, not exact authority.
   - Add helper(s) for projecting `LifeChange` into event amount and extracting event magnitude safely.
   - Production projection must never emit `i32::MIN`.
   - `apply_life_gain_after_replacement` and `apply_life_loss_after_replacement` must construct `LifeChange::gain/loss` without casts.
   - Emit `GameEvent::LifeChanged` through the projection helper.
   - Preserve the exact `u32` return amount from post-replacement helpers.
   - Preserve the life-safety receipt hook.

6. Harden all `LifeChanged.amount` magnitude consumers

   - `game/targeting.rs`: replace `amount.abs()` in `extract_amount_from_event`.
   - `game/trigger_matchers.rs`: replace `amount.abs()` and threshold casts in `life_amount_matches`.
   - `game/effects/mod.rs`: replace `-*amount`, direct `*amount`, and `.sum::<i32>()` life-channel accumulation with helper-based saturated accumulation.
   - `game/log.rs`: replace `amount.abs()` in loss formatting.
   - `parser/oracle_nom/quantity.rs`: update the comment that names the old `amount.abs()` extraction.

7. Migrate life-difference producers

   - `game/effects/life.rs`: compute assignment deltas with `LifeChange::between`; resume pending tails as typed changes.
   - `game/effects/exchange_life.rs`: replace `stat_value - old_life` and `-diff`.
   - `game/effects/double.rs`: handle `i32::MIN` with direction-safe magnitude logic.
   - `game/engine_debug.rs`: compute set-life difference through `LifeChange::between`.
   - `game/preview.rs`: change `LifeDelta.delta` to exact `i64` projection and compute with `LifeChange::between`.
   - `analysis/resource.rs`: replace raw snapshot subtraction in `grown_life_deltas`.
   - `game/players.rs`: use saturating folds for team-life sum and aggregate sum.
   - `game/quantity.rs`: make `LifeAboveStarting` saturating after `team_life_total`.

8. Harden life threshold comparisons

   - `game/life_costs.rs`: compare `u32 amount` against nonnegative team life without `amount as i32`.
   - `game/replacement.rs`: update `UnlessPlayerLifeAtMost` to compare `team_life_total` against `u32` threshold without lossy casts.
   - Preserve ordinary payable-cost behavior and existing prohibition ordering.

9. Add regressions

   In `cr733_resolved_commands_p2.rs`:

   - Extreme resolved life edit loss/gain saturation and replay.
   - Legacy numeric JSON compatibility and out-of-domain rejection.
   - `u32::MAX` post-replacement loss emits `-i32::MAX`, never positive and never `i32::MIN`.
   - Symmetric `u32::MAX` gain emits `i32::MAX`.
   - Event-context extraction, trigger matcher, previous-effect amount channel, and log formatting consume max/legacy-min events without panic.
   - Pending life-total assignment resume preserves remaining exact changes.
   - Extreme exchange, double, preview, analysis, team, quantity, cost, and replacement-threshold assertions.
   - Small-value siblings proving normal arithmetic remains unchanged.

   In `swarm_combat_witness.rs`:

   - Build two unblocked `i32::MAX`-power attackers through `GameScenario`.
   - Call `adversarial_swarm_witness_with_counters`.
   - Assert lethal certification, `candidate_clone_applies == 1`, and unchanged input state.
   - This is the positive reach guard proving the reducer completed the exact AI production branch.

10. Verify

   - Run `cargo fmt --all`.
   - If Tilt is available:
     `./scripts/tilt-wait.sh --timeout 240 clippy test-engine card-data`
   - If Tilt is unavailable:
     `cargo clippy --all-targets -- -D warnings`
     `cargo test -p phase-engine`
     `./scripts/gen-card-data.sh`
   - Confirm no parser/card-support delta and no generated artifact diff.
   - Re-run targeted `rg` sweeps over touched life paths for `as i32`, `amount.abs()`, unary negation, and raw life subtraction; justify every remaining conversion.
   - Finish with `git status --short`.

## Verification Matrix

| Claim | Changed seam | Production entry | Revert-failing assertion | Hostile/sibling and reach guard | Coverage |
|---|---|---|---|---|---|
| Cumulative combat loss cannot panic below `i32::MIN` | `LifeChange`, `apply_resolved_player_edit` | AI swarm witness → combat damage → post-replacement life loss | Two max-power attackers return lethal certificate; reverting restores panic | `candidate_clone_applies == 1`; ordinary 3/3 swarm remains exact | No parser/support change |
| Single replacement-expanded loss never reverses sign | `apply_life_loss_after_replacement` | `apply_life_loss` / replacement resume → `Execute` | `u32::MAX` loss journals exact negative magnitude and emits `-i32::MAX` | Production event projection asserts not positive and not `i32::MIN`; zero sibling emits no command | Unchanged |
| Gain and loss share one safe numeric model | `LifeChange::{gain,loss}` | direct gain/loss and lifelink authorities | `u32::MAX` gain reaches `i32::MAX`, never becomes loss | Ordinary `+4`/`-2` event tests remain exact | Unchanged |
| `LifeChanged.amount` consumers are bounded-safe | event magnitude helper | trigger/event-context/previous-effect/log consumers | Legacy `i32::MIN` event and saturated max production event do not panic and yield `i32::MAX` magnitude | Positive reach through each production consumer; sign-only consumers unchanged | Unchanged |
| Replay retains final post-replacement magnitude | `ResolvedPlayerEdit::Life` | resolved journal replay | Original and replayed state/history match for extreme changes | Unknown player and zero command still fail; oversized JSON rejected | Unchanged |
| Paused replacement delivery retains recipient and amount | typed pending assignment and existing pending replacement | `ChooseReplacement` resume | Existing two-replacement tests deliver selected final event once | Two noncommuting replacement sources; first branch is pending consumption | Unchanged |
| Extreme set/exchange/double operations do not overflow | shared typed difference dispatcher | respective effect resolvers | Endpoints resolve without panic or direction reversal | `i32::MIN` double, `i32::MAX ↔ i32::MIN` exchange, normal sibling | Unchanged |
| Team, quantity, preview, and analysis projections cannot overflow | `team_life_total`, `LifeAboveStarting`, preview, `grown_life_deltas` | SBA/cost checks, quantity resolution, action preview, loop analysis | Extreme snapshots return saturated/exact-direction results | Two team members at same bound; positive and negative snapshot siblings | Unchanged |
| Life-cost affordability cannot succeed through sign-wrapped conversion | `life_costs` comparison | casting/activation pay-life validation | Amount above representable positive team life is insufficient | Ordinary payable cost remains payable; `CantLoseLife` still prohibits | Unchanged |
| Life-threshold replacement conditions cannot wrap | `replacement.rs` condition comparison | replacement matcher condition | `UnlessPlayerLifeAtMost { amount: u32::MAX }` suppresses on ordinary life totals | Small threshold sibling still distinguishes above/below | Unchanged |

## `add-replacement-effect` Checklist Disposition

- `ReplacementEvent`: unchanged; `LoseLife` and `GainLife` already exist.
- `ReplacementCondition`: unchanged.
- Registry/matcher/applier: unchanged except safe comparison inside existing `UnlessPlayerLifeAtMost`.
- Parser/routing: unchanged.
- `apply_post_replacement_effect`: unchanged.
- `engine.rs` routing: unchanged.
- Pipeline verification: added through real combat and replacement-executed life loss.
- Provenance verification: existing multi-replacement resume tests retained.
- Optional replacement and candidate-count behavior: unchanged and covered by existing replacement tests.
- Serialization: explicitly tested because resolved and pending payload types change.
- Skill anchor self-check: referenced replacement symbols exist at the base SHA.

## Probe Limitations

- No throwaway compiled probe was added because this planning stage is prohibited from editing files, and `cargo` is not on `PATH` in this shell.
- The issue’s production panic remains the positive runtime reach evidence.
- `docs/MagicCompRules.txt` is absent, so implementation must fetch and grep the authoritative rules before changing CR annotations.
- The planning stage left the worktree clean.