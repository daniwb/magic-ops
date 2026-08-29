# Plan: issue #7954 — overflow-safe post-replacement life changes

Base: `fae406c4603f450797014f3ac8e8818b3d36c2a4`  
Mode: planning only; Experiment 001 publication is prohibited.

## Premise verification

- The checkout is exactly at the requested base SHA and is clean.
- [Issue #7954](https://github.com/phase-rs/phase/issues/7954) reports a production panic at `apply_life_loss_after_replacement` with `ResourceOverflow` while an AI combat simulation processes approximately 2.49 billion damage.
- The reported build `bc9310a` and the requested base contain the same failing expression:
  `ResolvedPlayerEdit::Life { delta: -(loss_amount as i32) }`.
- The diagnostic positively proves the production route reached `GameState::apply_resolved_player_edit`; this is not merely a synthetic arithmetic hypothesis.
- The reported deck premise is consistent with current Oracle text:
  [Thrakkus the Butcher](https://api.scryfall.com/cards/named?exact=Thrakkus%20the%20Butcher) doubles every Dragon’s power when it attacks, while [Miirym, Sentinel Wyrm](https://api.scryfall.com/cards/named?exact=Miirym%2C%20Sentinel%20Wyrm) creates nonlegendary Dragon-token copies.
- Static analysis identifies two defects in the same class:
  - cumulative negative deltas eventually make `Player::life.checked_add(delta)` fail below `i32::MIN`;
  - a single post-replacement amount above `i32::MAX` can reverse direction through `as i32`.
- No saved game or 179-creature state was attached, so the exact board cannot be replayed during planning.

## Applicable skills

- `engine-planner`: primary planning workflow.
- `add-replacement-effect`: applies because the failing delivery consumes a replacement-processed `LifeLoss` event.
- `review-engine-plan`: standalone architectural review completed; no blocking gaps remain.
- `validate-cr-annotations`: applicable, but `docs/MagicCompRules.txt` is absent. No CR annotation may be written until the implementation stage fetches the file and verifies every cited rule.
- `project-reference`: used for repository-safe verification conventions.
- Not applicable:
  - `add-engine-variant`: no enum variant is proposed.
  - `add-engine-effect`: no new effect or stub completion.
  - `oracle-parser`, `card-test`, frontend, AI-feature, and interactive-effect skills: no parser, cast-pipeline, UI, policy, or new choice-state work.

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
- AI combat simulations, loop analysis, and public previews.

Scryfall currently reports roughly 4,935 unique cards containing “damage,” 332 containing “gain life,” 59 containing “lose life,” and 487 containing both “pay” and “life”; these overlap, but establish coverage on the order of thousands of cards plus ordinary combat.

## Analogous Trace

Two existing patterns were traced:

1. Post-replacement player damage:

   `game/combat_damage.rs::apply_combat_damage`  
   → `game/effects/deal_damage.rs::apply_damage_after_replacement`  
   → `game/effects/life.rs::apply_damage_life_loss`  
   → `game/replacement.rs::replace_event`  
   → `game/effects/life.rs::apply_life_loss_after_replacement`  
   → `types/game_state.rs::resolve_and_apply_player_edit`  
   → `ResolvedRulesJournal::record_player_edit`.

   The replacement-choice resume sibling is:

   `game/engine_replacement.rs::handle_replacement_choice`  
   → `apply_life_loss_after_replacement`.

2. Existing bounded-integer policy:

   `game/arithmetic.rs`  
   → saturating P/T and quantity projections  
   → layer/quantity consumers and boundary tests.

The plan extends that explicit saturation policy while retaining the exact post-replacement life-change magnitude in the semantic command.

## Building Blocks

- Preserve `ProposedEvent::LifeGain/LifeLoss { player_id, amount: u32, applied }` as the replacement pipeline’s authority.
- Preserve `apply_life_gain`, `apply_life_loss`, and their post-replacement delivery functions as the only rules-facing life mutation path.
- Preserve `ResolvedPlayerEdit` and `resolve_and_apply_player_edit` as the single journaling/mutation authority.
- Introduce one typed scalar building block, `LifeChange`, rather than duplicating casts and subtraction logic:
  - exact signed domain `[-u32::MAX, u32::MAX]`;
  - `gain(u32)`, `loss(u32)`, and `between(new: i32, old: i32)`;
  - `signed()`, `magnitude()`, `is_zero()`;
  - explicit saturated projections to stored/event `i32`.
- Reuse `team_life_total`, replacement continuations, and the existing resolved journal rather than adding another delivery or replay mechanism.

## Logic Placement

- `types/player.rs`: define the reusable life-change value type because it describes the player-life domain, not a particular effect.
- `types/resolved_commands.rs`: use `LifeChange` inside the existing `ResolvedPlayerEdit::Life` variant.
- `types/game_state.rs`: apply the exact semantic change to the bounded stored projection and journals.
- `game/effects/life.rs`: translate final replacement events into `LifeChange` and emit the bounded `LifeChanged` projection.
- Other effect modules only construct or dispatch `LifeChange`; they do not mutate life directly.
- Analysis and preview modules use the same difference primitive instead of raw `i32` subtraction.
- No logic moves into WASM, server, AI policy, or frontend code.

## Rust Idioms

- Keep the existing parameterized `ResolvedPlayerEdit::Life` variant; do not add gain/loss sibling variants.
- Use a private-field, `#[serde(transparent)]` newtype rather than a boolean direction or unchecked raw casts.
- Use `i64` internally only as the exact signed carrier for a `u32` magnitude.
- Use `i64::from(...)`, `unsigned_abs`, `try_from`, and explicit clamps; no lossy `as i32`, unchecked negation, or wrapping arithmetic.
- Keep matches exhaustive.
- Retain the serialized `delta` field name and numeric JSON shape for compatibility.

## Nom Compliance

No parser path changes. Nom compliance is not applicable.

## Extension vs Creation

This extends two established patterns:

- resolved semantic player edits remain the sole final mutation authority;
- bounded engine scalar projections saturate rather than wrap or panic.

`LifeChange` is justified because gain, loss, difference computation, replay, preview, and analysis currently reproduce the same unsafe signed/unsigned conversions independently.

## Variant Discoverability

No engine enum variant is added, so `cargo engine-inventory` and the `add-engine-variant` gate are not required. `ResolvedPlayerEdit::Life` changes only its payload type.

## Identity / Provenance Contract

- Authority: the final `ProposedEvent::LifeGain` or `LifeLoss`.
- Identity: `player_id` is latched when the event is proposed and remains unchanged through replacement ordering.
- Magnitude: the final post-replacement `u32 amount` is converted exactly to `LifeChange`.
- Binding time: after the replacement pipeline returns `Execute`, or when the stored pending replacement resumes.
- Semantics: recipient and magnitude are snapshotted; delivery must not rescan targets, controllers, or replacement sources.
- Storage:
  - immediate path: local final proposed event;
  - deferred path: existing `PendingReplacement`;
  - replay: `ResolvedPlayerEdit::Life { delta: LifeChange }`;
  - paused life-total permutation: `PendingLifeTotalAssignment`.
- Consumption: `apply_life_gain_after_replacement` or `apply_life_loss_after_replacement`, exactly once.
- Expiration: consumed event/continuation is removed; existing applied-replacement keys prevent reapplication.
- Invalid recipient: an unknown player remains a typed invariant error. Saturation must not conceal identity failures.
- Multi-authority hostile guard: retain and run existing tests where two noncommuting life-loss replacements compete, proving the selected replacement’s latched event—not a later registry rescan—is delivered.

## Scope Matrix

| Boundary | Reachable cases | Planned treatment |
|---|---|---|
| Event kind | `LifeGain`, `LifeLoss` | Both construct exact `LifeChange`; zero remains a no-op |
| Replacement result | `Execute`, `Prevented`, `NeedsChoice` | Only `Execute` mutates; existing continuation ownership remains unchanged |
| Origin | combat damage, noncombat damage, direct effect, lifelink, cost, mana loss, set/exchange/double | All converge on existing life authorities |
| Recipient | individual player, shared-life team member | Exact player remains latched; derived team totals saturate safely |
| Magnitude | normal, `i32::MAX`, `i32::MAX + 1`, `u32::MAX`, cumulative boundary crossing | Preserve exact semantic magnitude; explicitly saturate bounded projections |
| Stored state | `Player::life: i32`, per-turn `u32` histories | Saturating updates; never wrap or panic |
| Event projection | `GameEvent::LifeChanged.amount: i32` | Preserve sign and clamp; document exact magnitude as journal-owned |
| Replay | live command, legacy serialized numeric delta, malformed out-of-domain delta | Exact replay, backward-compatible wire shape, reject invalid domain |
| Analysis | AI swarm clone, loop-growth snapshot, preview diff | Replace raw subtraction with the shared typed difference |
| Adjacent resources | energy, counters, speed | Unchanged checked-precondition behavior |

## Sizing

### Unit U1 — Exact life-change carrier with bounded projections

One coherent behavior: represent every final life change exactly over the existing `u32` event domain and project it safely into bounded state/event views.

Registration surfaces:

- player numeric type;
- `ResolvedPlayerEdit::Life` payload and journal validation;
- pending life-total-assignment serialization;
- post-replacement delivery;
- set/exchange/double/debug/cost producers;
- team, preview, and analysis projections.

Discriminating test:

- the real AI swarm/reducer path with two unblocked `i32::MAX`-power attackers must complete, certify lethal, and reach the combat-damage leaf without panic;
- a replacement-expanded loss above `i32::MAX` must remain negative, journal its full magnitude, and replay identically.

Dependencies: none; this is a single lockstep unit.

Expected phase-fit scope count: 17 literal paths. There is only one independently implementable/tested unit, so the multi-unit trigger is false; the plan should remain one phase despite broad lockstep call-site coverage.

## Exact Proposed Scope Paths

Production/type paths:

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

Test paths:

- `crates/engine/tests/integration/cr733_resolved_commands_p2.rs`
- `crates/engine/tests/integration/swarm_combat_witness.rs`

No parser, replacement registry, `engine_replacement.rs`, adapter, frontend, AI-policy, or card-data source changes are proposed.

## Implementation Steps

1. CR verification prerequisite

   - Fetch `docs/MagicCompRules.txt` with the repository script.
   - Verify every retained or new annotation, especially the relevant portions of CR 107, 119, 120.3a, 510.2, and 704.5a.
   - Do not write an annotation whose exact rule text cannot be verified.

2. Add the typed life-change value

   In `types/player.rs`:

   - Add `LifeChange`, backed privately by `i64`.
   - Constrain its serialized/deserialized range to a signed `u32` magnitude.
   - Add constructors for gain, loss, and the exact difference between two `i32` totals.
   - Add exact magnitude/direction accessors and explicit `i32` projection/application methods.
   - Preserve zero as a representable intermediate no-op; resolved-journal validation continues rejecting zero commands.

3. Thread the type through replay and continuations

   In `types/resolved_commands.rs`, `types/game_state.rs`, and `types/resolution.rs`:

   - Change `ResolvedPlayerEdit::Life { delta }` from raw `i32` to `LifeChange`, retaining the field name and transparent numeric JSON.
   - Separate life no-op validation from the `i32` energy/counter match arm.
   - Change `PendingLifeTotalAssignment.remaining` to carry `LifeChange`.
   - Update legacy-state tests to prove old integer payloads still deserialize.
   - Reject serialized values outside the signed-`u32` domain.

4. Make resolved life application total

   In `types/game_state.rs`:

   - Apply the exact change to `Player::life` through `LifeChange`’s saturated projection.
   - Update `life_gained_this_turn` or `life_lost_this_turn` using the exact `u32` magnitude and `saturating_add`.
   - Continue returning `UnknownPlayer` and `ZeroDelta` where appropriate.
   - Leave energy, counters, and speed on their existing checked-precondition paths.
   - Record the exact `LifeChange` in the journal after successful application.

5. Fix all post-replacement delivery

   In `game/effects/life.rs`:

   - Construct `LifeChange::gain(gain_amount)` and `LifeChange::loss(loss_amount)` without casts.
   - Emit `GameEvent::LifeChanged` using the explicitly clamped signed event projection.
   - Keep the return value as the exact post-replacement `u32` amount.
   - Preserve the life-safety receipt hook; ordinary payable costs remain within the non-saturated region.
   - Add a shared dispatcher for already-computed `LifeChange` values so set/exchange/redistribution paths do not repeat sign and negation logic.
   - Compute life-total-assignment differences with `LifeChange::between` and store the typed tail across replacement pauses.

6. Migrate every life-difference producer

   - `game/effects/exchange_life.rs`: replace `stat_value - old_life` and `-diff`.
   - `game/effects/double.rs`: handle `i32::MIN` through `unsigned_abs`/`LifeChange`, never unary-negate it.
   - `game/engine_debug.rs`: compute debug set-life differences through `LifeChange::between`.
   - `game/library.rs`: update the test construction of `ResolvedPlayerEdit::Life`.
   - `game/life_costs.rs`: compare `u32 amount` against nonnegative team life without `amount as i32`.
   - Update every construction/consumption site found by `rg "ResolvedPlayerEdit::Life|PendingLifeTotalAssignment"`; no raw constructor may remain.

7. Harden derived projections

   - `game/players.rs`: use saturating folds for team-life sum and aggregate sum.
   - `game/preview.rs`: calculate preview deltas through `LifeChange::between`; expose the signed difference as `i64`, whose possible range remains exactly representable by JavaScript numbers.
   - `analysis/resource.rs`: replace raw snapshot subtraction in `grown_life_deltas` with the typed difference, returning only positive exact magnitudes.
   - `types/events.rs`: document that `LifeChanged.amount` is a signed bounded event projection, while the resolved journal retains the exact event-domain magnitude.

8. Add regressions

   In `swarm_combat_witness.rs`:

   - Build two unblocked `i32::MAX`-power attackers through `GameScenario`.
   - Call `adversarial_swarm_witness_with_counters`.
   - Assert a certified lethal result, `candidate_clone_applies == 1`, and unchanged input state.
   - This is the positive reach guard proving the reducer completed the exact AI production branch.

   In `cr733_resolved_commands_p2.rs`:

   - Test a loss replacement that expands `i32::MAX` to `u32::MAX`.
   - Assert:
     - stored life saturates at `i32::MIN`;
     - `life_lost_this_turn == u32::MAX`;
     - emitted `LifeChanged` remains negative;
     - the journal stores the exact negative `LifeChange`;
     - replay produces the same state.
   - Add the symmetric `u32::MAX` gain case.
   - Add legacy JSON round-trip and out-of-domain rejection.
   - Add extreme team-total, set-life-difference, preview-difference, and `i32::MIN` double-life assertions.
   - Retain small-value siblings proving normal arithmetic is unchanged.

9. Verify

   - Run `cargo fmt --all`.
   - If Tilt is available:
     `./scripts/tilt-wait.sh --timeout 240 clippy test-engine card-data`
   - If Tilt is unavailable:
     `cargo clippy --all-targets -- -D warnings`
     `cargo test -p phase-engine`
     `./scripts/gen-card-data.sh`
   - Confirm no parser/card-support delta and no generated artifact diff.
   - Re-run `rg "as i32|-[[:space:]]*.*life|life.*-[[:space:]]*"` over the touched life paths and justify every remaining conversion.
   - Finish with `git status --short`; it must contain only the planned implementation changes during execution.

## Verification Matrix

| Claim | Changed seam | Production entry | Revert-failing assertion | Hostile/sibling and reach guard | Coverage |
|---|---|---|---|---|---|
| Cumulative combat loss cannot panic below `i32::MIN` | `LifeChange`, `apply_resolved_player_edit` | AI swarm witness → simulated attacker/blocker actions → combat damage → post-replacement life loss | Two max-power attackers return a lethal certificate; reverting restores the panic | `candidate_clone_applies == 1`; ordinary 3/3 swarm remains exact | No parser/support change |
| A single replacement-expanded loss never reverses sign | `apply_life_loss_after_replacement` | `apply_life_loss` → `replace_event` → `Execute` | `u32::MAX` loss journals negative and emits a negative event | One live loss doubler proves the replacement matcher/applier ran; zero-loss sibling emits no command | Unchanged |
| Gain and loss share one safe numeric model | `LifeChange::{gain,loss}` | direct gain/loss and lifelink authorities | `u32::MAX` gain reaches `i32::MAX`, never becomes loss | Ordinary `+4`/`-2` event tests remain exact | Unchanged |
| Replay retains final post-replacement magnitude | `ResolvedPlayerEdit::Life` | resolved journal replay | Original and replayed state/history match for extreme changes | Unknown player and zero command still fail; malformed oversized JSON is rejected | Unchanged |
| Paused replacement delivery retains recipient and amount | typed pending assignment and existing pending replacement | `ChooseReplacement` resume | Existing two-replacement tests deliver exactly the selected final event once | Two noncommuting replacement sources; first branch is `PendingReplacement` consumption | Unchanged |
| Extreme set/exchange/double operations do not overflow intermediate subtraction | shared typed difference dispatcher | respective effect resolvers | Endpoints resolve without panic or direction reversal | `i32::MIN` double, `i32::MAX ↔ i32::MIN` difference, normal exchange sibling | Unchanged |
| Team and analysis snapshots cannot overflow | `team_life_total`, preview, `grown_life_deltas` | SBA/cost checks, action preview, loop analysis | Extreme snapshots return saturated/exact-direction results | Two team members at the same bound; positive and negative snapshot siblings | Unchanged |
| Life-cost affordability cannot succeed through sign-wrapped conversion | `life_costs` comparison | casting/activation pay-life validation | Amount above representable positive team life is insufficient | Ordinary payable cost remains payable; `CantLoseLife` still prohibits before mutation | Unchanged |

## `add-replacement-effect` Checklist Disposition

- `ReplacementEvent`: unchanged; `LoseLife` and `GainLife` already exist.
- `ReplacementCondition`: unchanged.
- Registry/matcher/applier: unchanged; existing amount modifications remain authoritative.
- Parser/routing: unchanged.
- `apply_post_replacement_effect`: unchanged; this bug is final event delivery, not a replacement side effect.
- `engine.rs` routing: unchanged.
- Pipeline verification: added through real combat and replacement-executed life loss.
- Provenance verification: existing multi-replacement resume tests retained.
- Optional replacement and candidate-count behavior: unchanged and covered by existing replacement tests.
- Serialization: explicitly tested because resolved and pending payload types change.
- Skill anchor self-check: all referenced replacement symbols exist at the base SHA.

## Premise and Probe Limitations

- The issue provides no serialized game state, deck list, or attachment, so the exact 179-creature board and precise final offending assignment cannot be measured.
- No throwaway test or implementation probe was added because this planning stage is prohibited from editing files. The issue’s production panic is the positive runtime reach evidence; the proposed implementation must add the discriminating production tests above before the fix is accepted.
- `docs/MagicCompRules.txt` is absent. CR numbers appearing in existing code were not re-certified during planning; implementation must fetch and grep the authoritative local rules before adding or modifying annotations.
- The plan follows the repository’s established bounded-`i32` projection policy rather than introducing arbitrary-precision life totals. Exact post-replacement event-domain magnitude is retained in `LifeChange` and the journal; stored life and `LifeChanged` are explicit saturated projections.
- The requested base is clean, and the planning stage left it unchanged. No files, commits, pushes, PRs, issue comments, or other publications were created.