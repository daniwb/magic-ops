# September 11: unresolved ticket diagnostics

At inspection, 103 unresolved ticket failures: 95 worker/infrastructure failures and eight integration failures. These are retained failed jobs, not a service-outage count. No failure was cleared or retried by this investigation.

## Integration failures

| Ticket | Failed check / cause | Recovery status |
| --- | --- | --- |
| ticket:map.plan-copy-sage-of-the-skies-30d5d8211c/v4 | Merge conflict in scripts/paragraph/reparse.py | Map repair limit reached (2/2); complete-card verification is still required. |
| ticket:map.plan-damage-skullcage-3f854ae5df/v4 | Unregistered effect: damage_unless_hand_count | Map repair limit reached (2/2); complete-card verification is still required. |
| ticket:map.plan-exile-sphere-of-annihilation-032fa4cd5d/v4 | Unregistered effect: exile_mv_le_source_counters_multizone | Map repair limit reached (2/2); complete-card verification is still required. |
| ticket:map.plan-put-counters-selfcraft-mechan-ac7fb28b1a/v4 | Unregistered effect: put_counter_and_draw_card | Map repair limit reached (2/2); complete-card verification is still required. |
| ticket:map.plan-regrow-retrieve-b33ea3ed9d/v4 | Unregistered effect: return_from_graveyard_dual_filter_hand | Map repair limit reached (2/2); complete-card verification is still required. |
| ticket:map.plan-sacrifice-promise-of-tomorrow-f7fb65fa2a/v4 | Unregistered effect: sacrifice_self_return_exiled | Map repair limit reached (2/2); complete-card verification is still required. |
| ticket:map.plan-tap-tideforce-elemental-ecc1126789/v4 | Unregistered effect: tap_or_untap_target_choice | Map repair limit reached (2/2); complete-card verification is still required. |
| ticket:map.plan-tap-word-of-binding-e0c3cca63f/v4 | Unregistered effect: tap_variable_amount_x | Map repair limit reached (2/2); complete-card verification is still required. |

## Tideforce Elemental evidence

Its v4 candidate inserts `out.add('tap_or_untap_target_choice')` inside `registered_effects()` in the Python parser. That locally declares support absent from the Go registry. The full production vocabulary gate rejected the generated card, so this candidate was not enabled.

The integrated dependency test `backend/game/factory_ng_9c8e817ef6_test.go` manually supplies `EffectValue["mode"]` on a copied ability and calls `resolveActivatedAbility`. The Map candidate emits an empty effect value. The runtime helper returns without acting when mode is absent. Therefore simply adding a registry entry is insufficient: conversion and the public per-activation player-choice path need a behavioral repair and an end-to-end regression. Existing gates and the exhausted two-generation repair budget remain intact.

## Worker failures

28 of the 95 current worker-failure logs retain the exact old `canonical source must be clean` preflight error. Source waits were repaired previously; old failures are retained evidence. Other receipts include malformed or absent edit blocks and an unmatched SEARCH block. Some jobs retained an older receipt after a newer preflight exit. The new dashboard suppresses that stale receipt as the current failure and exposes the job reason, attempts and log path instead.

## Changes

- Preserve job reasons, attempt counts, repair/dependency blockers and log paths in the SQLite read projection.
- Project bounded failed-check excerpts; prioritize actual errors over unrelated logs.
- Select per-ticket exclusions from combined integration receipts. A merge-excluded ticket must not inherit another candidate's vocabulary failure.
- Version the disposable projection so existing immutable receipts gain diagnostics without altering them.
- Show actual failed checks directly on the Details Summary tab, and show recovery limits on work rows.
- Rename the KPI to “Unresolved ticket failures” with separate worker/infrastructure and integration totals.

The newer vocabulary handoff work was already present at session start. Its six tests pass, including rejection of a fabricated Python registry. This session did not author or change that work.

Validation and activation results are appended below.

## Validation

- Twelve dashboard-index tests passed, including projection migration, stale-receipt exclusion, exact failed-gate excerpts, preserved attempts/blockers, and per-ticket wave exclusions.
- Node rendering checks passed for Tideforce's actual receipt, recovery limits, HTML escaping, an excluded merge candidate and a no-receipt job. These are DOM-stub checks, not a full-browser screenshot test.
- The six pre-existing vocabulary regressions passed.
- Live attention data returned in 0.97 seconds (136 KB in this sample), retaining all 103 failures and Tideforce's exact failed-check excerpt.
- Fresh watchdog audit retained only the eight unresolved integration failures; the earlier dead-PID/unknown-queue warnings cleared. Canonical source was clean with no unfinished Git operation.

- Dispatcher Go tests (`go test ./...`) and final binary build passed.
- Activated under the dispatcher-admin scoped lock. Previous PID 3067957; successor PID 2912620. Binary backup is `/tmp/factory-ng-problems-sep11/dispatcher-v4.previous`. Live HTML and the data/detail endpoints verified the new label, failed-check evidence, unchanged 103-failure total, and Tideforce's preserved 1 worker / 2 integration attempts.
- No game code, ticket, receipt, retry budget or live game deployment was changed. The eight integration defects remain unresolved; this session fixes their visibility and documents the behavioral repair needed for Tideforce.
