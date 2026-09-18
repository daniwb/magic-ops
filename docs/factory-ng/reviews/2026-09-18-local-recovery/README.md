# Local Factory recovery — September 18

The user authorized fixing the two disabled-worker proposals and eleven retained
integration failures. All immutable tickets, accepted observations, failed
receipts and original gates are retained. Repairs use the existing reviewed
resolution interface, which binds the original patch and ticket hashes and
rechecks the original semantics on the final composition.

## Completed prerequisite and stalled proposals

The full sharded gate still hard-coded `/usr/local/go/bin/go`. The reviewed
Faith's Shield integration resolves Go from the managed environment instead,
retaining all six shards and cardfns vet/tests. Full integration pushed
`6fc9cd5c0f46c87e6909b2edf0cba75d9d0938c9`.

Codex-3 and Codex-4 were enabled temporarily for the original saved proposals.
Their bounded repairs passed focused checks and full production integration:
`2026-09-18T143915Z-wave-0337badb2f54-1789742355287522600-integration.json`.
Pre-War Formalwear's Engine dependency and Silverflame Ritual both reconcile as
completed. Both worker enable flags were restored to false after their work.

## Reviewed engine repairs

Nine accepted candidates conflicted with newer engine changes. The isolated
composition preserves the newer target-slot types, flying/graveyard routing,
token-copy links and added card types, referent tracking and independent effect
dispatch while restoring each original accepted behavior and named test.

The dynamic attack-count candidate published a second attack event to collect
group triggers, unintentionally firing legacy callbacks twice. It now collects
and deduplicates matched ability pointers from the original per-attacker events,
retains their matching event, then stacks each group trigger once. The original
dynamic-damage check and all previously failing handler selectors pass.

The destroy-unless-pay candidate unconditionally changed the payer for all
targeted destroy triggers. Converted target-controller-pay abilities now carry
an explicit marker; legacy you-may-pay handlers and explicit payer overrides
keep their semantics. The original payment/decline test and all three colored
mana handler regressions pass.

`merge-resolutions.json` records each reviewed patch and its provenance.
`record-resolution.py` exports a clean reviewed commit. `integrate-reviewed.py`
runs the remaining original accepted observations plus three exact missing-Go
integration failures through the original semantic and complete production gates.
`wave-inputs.json`, `integration-result.json` and the referenced immutable
integration receipt are the authorities for the final wave outcome.

Canonical source was not edited directly; all source changes were prepared in
`/tmp/factory-ng-recovery-sep18-eeRTY6/source`. Deployment remains disabled.

## Main recovery wave passed

The fourteen-observation wave passed all included original semantic contracts,
reparse/import, build, game tests, focused cards and full six-shard/cardfns gates.
It pushed `1ad149466a306abcdf73f91f1a852cc4357fa14c`. Twelve tickets completed,
including both regressions and the three exact missing-Go failures.
Receipt: `2026-09-18T144240Z-wave-4a94606e3eba-1789742560346323218-integration.json`.

Two candidates were correctly excluded: the flying-creature source-power and
attached-Aura fight repairs required base objects unavailable to the integrator's
three-way fallback. Neither was counted as completed. A follow-up checkout
rebased them onto the twelve-ticket composition, preserving the newly integrated
Pre-War Formalwear graveyard routing. The original patches remain as evidence;
the manifest now references distinct `-followup.patch` artifacts for these two.

## Final two repairs passed

The two-candidate follow-up passed its original semantics and full production
gate and pushed `87e117e0eba8b403abf40d7c8f56143cc6df174e`.
Receipt: `2026-09-18T144620Z-wave-6cd2c6e30806-1789742780618136482-integration.json`.
All thirteen originally requested repairs have therefore passed full integration,
along with four additional tickets affected by the discovered Go-path failure
(Faith's Shield prerequisite plus the three exact-path retries). Historical failed
receipts remain intact. Codex-3/4 are disabled again, automatic Factory operation
continues, and no live deployment was performed.

Closing audit at 14:48:46 UTC: watchdog `healthy: true`, no problems, zero
unsuperseded integration failures, seven runnable tickets, and canonical checkout
clean. Controller reconciliation reports every requested repair completed.
