# Stale-park sweep — 2026-07-27

Parked/blocked tickets whose claimed-missing primitive/shape now matches
the current catalogs (grep probe, read-only — NOTHING requeued). Flow:
Sonnet batch-prechecks these 8 claims; confirmed ones get requeued by a
human/dispatcher. Sweep basis: 66 tickets with missing_prim set.

- **#33** [blocked] DSL: [LTC] Isengard Unleashed — parse_error
  - claimed missing: `controller-damage-multiplier-until-eot`
  - catalog match: all-words: - `groupdamagemultiplierbycontroller(gs *game.gamestate, self *game.card, targetplayeridx int, multi
- **#177** [blocked] DSL: [KHM] Weathered Runestone — parse_error
  - claimed missing: `library-zone-cast-and-enter-restriction`
  - catalog match: all-words: "you may cast this card from exile" printed directly on the card itself (misthollow griffin class) —
- **#295** [blocked] DSL: [SNC] Errant, Street Artist — parse_error, missing_activated
  - claimed missing: `target-spell-on-stack-activated-ability`
  - catalog match: all-words: - `copyactivatedabilityonstack(gs *game.gamestate, sourcecardid string, newcontroller int, newtarget
- **#313** [wait] DSL-BUNDLE: [put_counter] Wall of Shards + Adaptive Training Post + Zimone's Hypothesis
  - claimed missing: `cumulative_upkeep_with_non_mana_cost`
  - catalog match: all-words: - do not use this for braidoffire-shaped "cumulative upkeep whose cost is a benefit with no real dow
- **#430** [blocked] DSL-SPLIT: Devourer of Destiny (from #8423)
  - claimed missing: `exile-target-permanent-on-cast`
  - catalog match: all-words: "you may cast spells with flash and/or flying from the top of your library" (errant and giada, vocab
- **#1070** [blocked] DSL-SPLIT: Inalla, Archmage Ritualist (from #9010)
  - claimed missing: `may-pay-mana-arbitrary-action-trigger`
  - catalog match: all-words: - **engine addition this required:** `unlesspayaction` is the arbitrary-action counterpart to `unles
- **#1074** [blocked] DSL-SPLIT: Prototype Portal (from #9010)
  - claimed missing: `token-copy-of-exiled-card`
  - catalog match: all-words: - `exiledyingcreaturewithlinkedtokencopy(gs *game.gamestate, self *game.card, filter deathreplacemen
- **#1142** [blocked] DSL-SPLIT: Prime Speaker Vannifar (from #9094)
  - claimed missing: `activated-ability-sacrifice-cost`
  - catalog match: all-words: - `registerencoreability(gs *game.gamestate, self *game.card, cost game.manacost) *game.activatedabi

Assessment: strong #33/#295/#1074; plausible #313/#1070/#1142; weak #177/#430.
Rerun: this sweep is deterministic — rerun after every vocab batch lands.
