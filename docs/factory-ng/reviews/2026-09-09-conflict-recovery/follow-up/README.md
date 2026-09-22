# Follow-up recovery, September 9

The user requested action on the five unresolved lineages after the status
check. Work is isolated in the checkout recorded in `clone.txt`, pinned to
`base.txt`. This is an operator correction, with no additional worker/provider runs started
by this recovery and no resets of model attempts or integration-repair counters.

## Scope and original evidence

`originals.json` binds the five latest failed tickets and their receipts by
SHA-256. The immutable originals remain intact. `ticket.json` is the explicit
finite operator composition: it preserves every original gate command and
semantic obligation, and documents the small additional prerequisite files.
It is stored outside automatic worker admission.

- Hand-size damage preserves the v2 real Storm Seeker parse/conversion/runtime
  assertion as well as the v1 ability and v3 conversion assertions. The Storm
  keyword now matches a complete keyword/reminder clause, allowing the existing
  damage pattern to match the card-name prefix. Amount conversion is restricted
  to `target_hand_size`.
- Self-pump v3 finished during this session with a formatting failure. Its
  retained tests are formatted and run against the already-existing explicit
  `target_ref=self` behavior, with the missing-target, group and all guards.
- Exiled mana value is recorded after an actual battlefield-to-exile move,
  in the existing sequence scratch map. An active-walk marker prevents later
  standalone effects reading leftover state; a new walk resets the map. Reads
  within one resolution are repeatable, and a new exile instruction resets
  that referent. Tests cover nonzero/zero value, mana/color filters, repeated
  reads, later unrelated effects and an actual put-counters consumer.
- Destroyed artifacts are counted at the actual graveyard transition using
  their controller and all card types. Counted targets share the same destroy
  function, preserving indestructible and regeneration handling. Damage uses
  the ordinary damage pipeline, with a source-only prevention regression.
  Historical helper tests remain, but their pre-destruction snapshot is only
  counted after an actual graveyard move.
- Sacrifice-unless-discard uses the existing `PendingChoice` presentation and
  `ResolvePendingChoice` API. Invalid player/card/count selections retain the
  choice. Valid discard and decline/sacrifice remain covered by both the
  original tests and the public choice/trigger paths.

The recovered discard and per-player-destruction damage executors receive
registry entries in a new init file, with new shape coverage. The frozen
registry literal is unchanged. Parser, choice-dispatch and sequence-lifetime
prerequisites are explicitly included in the operator ticket's scope; no
historical ticket scope is silently widened.

## Validation and landing

**All five remaining lineages are completed and pushed.** The original
15-lineage review now has 15 recovered and zero unresolved lineages.

`gates.json` and `gate-*-output.json` record all nine passing candidate gates,
including the complete Game/Cards suite. The accepted correction receipt is
`docs/factory-ng/runs/2026-09-09T192452Z-operator-conflict-recovery-followup.json`.
Its durable patch contains the code and tests; no worker/provider run was
started by this recovery. The pre-existing self-pump worker finished its
failed v3 during the investigation, and that receipt remains intact.

Normal integration acquired the existing scoped lock after the prior factory
wave finished. The correction applied cleanly to newer main. All five original
semantic selectors and new shape checks passed again, followed by reparse,
import, build, full Game, focused production checks and the six-shard suite.
The build took 161.4 seconds and the shard suite 202.1 seconds.

Integration receipt:
`docs/factory-ng/runs/2026-09-09T193506Z-engine-operator-conflict-recovery-sep09-v1-1788982506257851206-integration.json`.
Result: `474e2ba6b06b7ae132afd3dcb8c9298dc507f7e5`, pushed, with no exclusions.
All five original lineage IDs are parents of that receipt and reconciled to
completed automatically. No mutable job-state override was used.

`final-summary.json` verifies the exact original gate commands in the
integration receipt, all five completed jobs, unchanged attempt counters,
original ticket/receipt hashes, the earlier ten-recovery commits' ancestry,
matching remote main, and clean canonical source at 19:49:30 UTC.
No live deployment occurred. These are Engine recovery outcomes; whole-card
Map/verification completion remains a separate downstream result.
