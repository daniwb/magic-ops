# Legacy test-name collision recovery

One indivisible candidate preserves the three original reviewed capability contracts
and every distinct original gate. Existing same-name tests assert different earlier
capabilities; their assertions remain intact and call new shape coverage.

- Return-from-graveyard now consumes `with_counters` before battlefield registration
  and ETB publication, composing with self/tapped. Other destinations and no-counter
  returns remain covered.
- Minimum-power targeting composes thresholded artifact/enchantment/creature branches.
  Undefined power is excluded, including threshold zero; plain union and old maximum
  threshold remain covered. Public casting rejects illegal targets before spending.
- Target-player graveyard exile uses the registered sequence effect and public
  casting/resolution, checking both possible players, every original graveyard member,
  untouched other exile zone and battlefield. The older all-graveyards test remains.

`legacy-spell-fixture-gates.json` retains the initial fixture failure: the legacy
spell-only definition format did not convert the effect. The final test uses the
current effect-sequence format. All eight candidate gates pass in `gates.json`.
The single candidate passed normal full production integration and pushed
`3472d84ef99a5803a1bbb294c5cf4f5bd0f773a0`; receipt
`../../../runs/2026-09-15T205506Z-engine-operator-legacy-shapes-recovery-sep15-v1-1789505706221104833-integration.json`.
All three original parents reconcile from this fully green receipt.
