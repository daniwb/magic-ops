# Eight search misses: six requirements, four Engine follow-ups

Audited canonical revision `6642351731e0c336cd220a861dd14fc212e7d192` in an
isolated clone on September 8. This assesses current implementation, not what
was available at every historical ticket's older pin. No live ticket, engine
source, integration or deployment was changed.

The misses are not eight missing primitives. Three are versions of the same
Tidal Surge demand. Every distinct requirement has reusable engine code;
four concrete gaps remain across the six cards. This small selected sample
does not establish the fraction of all Engine tickets that are unnecessary.

| Card | Evidence and classification | Next action |
|---|---|---|
| Rakdos Roustabout | Existing `recipient_from=attacked_defender` works through blocked-event stack push and resolution for both player and planeswalker. | Reuse for Map/composition work. Check actual block declaration, combat removal and last-known recipient before claiming full correctness. |
| Sea God's Scorn | Generic union targeting accepts creatures and enchantments; chosen-target bounce already returns either to its owner. | Reuse both. Its 0..3 target limit depends on the same correction as Tidal Surge. |
| Tidal Surge, v1/v2/v3 | Casting rejects zero targets and accepts four. Existing test only executes two selected targets directly. | One target-cardinality correction through schema/converter/casting, with 0..3 acceptance tests. Correct old ticket's 1..N premise and missing casting-file scope in a successor. |
| Siegfried, Famed Swordsman | Existing sequence mills first, counts own graveyard creatures and multiplies by two. Two creatures give four counters, but zero gives one. | Fix zero-amount handling. No new graveyard-count or multiplication primitive. |
| Sigil of Sleep | Given a player-damage event, existing target choice filters by the damaged player and bounce returns a stolen creature to its owner. Actual noncombat player damage on the tested executor emits neither damage event. | Correct event emission and enchanted-trigger wiring; verify resolution legality. Reuse target choice. The earlier claim that event context needs a new framework was too broad. |
| Skittering Cicada | Existing event-mana-value pump gives +X/+0; keyword grant works. Symmetric dynamic P/T evaluation exists, but its count vocabulary lacks event mana value. | Connect event mana value to that evaluator and compose existing keyword/pump atoms. Preserve +X/+0 users. |

The counter bug illustrates why helper-level tests are insufficient:
`resolveDynamicAmountFull` turns `amount_count` into `amount=0` and removes
the count specification. `executePutCounterEffect` therefore skips its own
dynamic-count guard, then clamps the resolved zero to one. The positive case
passes. A direct test of the private counter helper can miss the public-path
failure.

For Sigil, do not blindly publish `EventDealsPlayerDamage` for noncombat
damage: current subscribers use its combat-only meaning, including monarch.
The correction needs explicit damage-kind semantics and tests protecting
those subscribers. Existing `PendingTriggerTarget` already carries event
referents; a new global event-history framework is not established as necessary.

## Evidence and reproducibility

- [Structured classification](fts5-miss-audit.json) links all eight versions
  to their original query, immutable failed receipt and current disposition.
- [Follow-up work orders](fts5-miss-followups.json) define source scope and
  acceptance checks. These are drafts, not runnable TicketSpecs or queue edits.
- [Diagnostic probes](fts5-miss-audit-probes.go.txt) and
  [final test output](fts5-miss-audit-tests.log) cover seven new probes plus
  the existing attacked-defender test: eight tests passed.
- Passing diagnostic probes reproduce observed defects as well as working
  behavior; this is **not** eight card-acceptance tests or evidence that the
  defects have been fixed. [Initial output](fts5-miss-audit-initial-tests.log)
  retains the two findings that corrected preliminary source-only assumptions.
- [Service lookups and local source resolution](fts5-miss-audit-lookups.json)
  and [request trace](fts5-miss-audit-lookups.jsonl): 13 explicit symbol/operation
  queries all found candidates; all 14 selected candidates resolved in the
  pinned clone. No direct knowledge SQL was used for this investigation.

To reproduce, copy the retained probe text to
`backend/game/fts_miss_audit_test.go` in an isolated checkout of the revision
above, then run from `backend`:

```sh
/opt/development/magic-ops/scripts/go-cache-run.sh test ./game -run '^TestFTSMissAudit|^TestFactoryNGDamageToAttackedDefender$' -count=1 -v
```

These probes construct runtime objects to isolate the disputed capabilities.
They do not prove fresh parser/converter wiring, all six complete cards,
last-known-information behavior or all resolution-time targeting restrictions.
Those are explicit acceptance checks in the follow-ups, not silently assumed.

## Consequence for the factory

A miss should produce a bounded investigation outcome with selected source
symbols and a behavioral counterexample. It should not become an instruction
to implement the generated capability name. The same applies to a hit: a
similar symbol is evidence to inspect, not proof that the entire contract works.

For this set, proceed with reuse plus four corrected Engine work items:
target cardinality, counter zero handling, event-mana-value P/T connection,
and player-damage event wiring. Keep separate complete-card acceptance for
each card. The first item serves two cards because both demonstrably require
the same casting constraint, not because their text looks similar.

The existing production repair records misses and actual source reads; this
audit does not install an automatic semantic classifier or automatically
supersede old tickets. A future runnable successor must carry this evidence,
correct scope and acceptance tests, while preserving the immutable history.
