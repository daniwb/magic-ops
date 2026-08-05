# Card Test Sample — 25 Cards

Generated 2026-07-31 as a test sample. 25 cards drawn from `backend/data/carddb/`, split into four
groups requested for testing: 5 cards blocked on a missing engine primitive, 5 "Hard" and 5 "Medium"
unproduced cards, and 10 cards that are already produced (served today by either a Go handler or a
data record).

**Note on "Hard"/"Medium":** this codebase has no stored per-card difficulty field (no such column
exists anywhere — carddb records, the handler registry, or the dispatcher ticket DB). Per your
direction, the 10 cards below are simply unproduced (`status: "review"`, no handler, no engine
support yet) sampled from the card database, and split into two arbitrary groups of 5 — ordered
loosely by eyeballed complexity (number of unparsed clauses / interacting abilities), not by any
ground-truth label. Treat the Hard/Medium tags as a rough sort, not ground truth.

Card cost is written in standard mana notation (e.g. `{3}{U}{U}`); text is the literal Oracle-style
text stored in the card record.

---

## Group 1 — Missing Primitive (5 cards)

Each of these has a working handler in `backend/cardfns/` for everything it *can* do, with an
explicit `MISSING_PRIMITIVE:` comment marking the one clause the engine can't support yet.

### 1. Imskir Iron-Eater
- **Cost:** `{6}{B}{R}`
- **Text:** Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)
  When Imskir enters, you draw X cards and you lose X life, where X is half the number of artifacts
  you control, rounded down.
  {3}{R}, Sacrifice an artifact: Imskir deals damage equal to the sacrificed artifact's mana value to
  any target.
- **Missing primitive:** `self_cost_reduction` — Affinity is a dynamic "costs {1} less per artifact
  you control" reduction applied while the card is still in hand being cast. The engine has no
  by-name registry for a permanent's own cast-time cost reduction, and a `CardHandler` only runs once
  the card is already on the battlefield, so this clause can't be implemented from `cardfns` alone.
  (`backend/cardfns/ImskirIronEater.go`)

### 2. Fractured Sanity
- **Cost:** `{3}{U}`
- **Text:** Each opponent mills fourteen cards.
  Cycling {1}{U} ({1}{U}, Discard this card: Draw a card.)
  When you cycle this card, each opponent mills four cards.
- **Missing primitive:** `sorcery_cycling_trigger_effect` — the "when you cycle this card" trigger
  fires from a non-battlefield zone (discarded as a cycling cost, never enters the battlefield). The
  engine only registers a sorcery's triggered abilities on cast or on a permanent entering — neither
  path runs for a cycled sorcery, so the cycle-event trigger is never installed. Requires engine-level
  support in `backend/game/keyword_abilities.go`. (`backend/cardfns/FracturedSanity.go`)

### 3. Ringsight
- **Cost:** `{U}{B}{1}`
- **Text:** The Ring tempts you. Search your library for a card that shares a color with a legendary
  creature you control, reveal it, put it into your hand, then shuffle.
- **Missing primitive:** `ring_tempts_you` — the engine has no "The Ring tempts you" mechanic
  (LOTR Ring-bearer / Temptation track) modeled at all. Same gap as Boromir, Warden of the Tower. The
  search effect itself is fully wired. (`backend/cardfns/Ringsight.go`)

### 4. Psychic Frog
- **Cost:** `{U}{B}`
- **Text:** Whenever this creature deals combat damage to a player or planeswalker, draw a card.
  Discard a card: Put a +1/+1 counter on this creature.
  Exile three cards from your graveyard: This creature gains flying until end of turn.
- **Missing primitive:** `graveyard_exile_cost` — the third ability needs an activation cost that
  exiles N cards from the controller's graveyard. `game.ActivationCost` has no such field (only
  Discard, Sacrifice, ExileSelf, etc.); adding one is an engine change out of scope for `cardfns`.
  (`backend/cardfns/PsychicFrog.go`)

### 5. Nether Traitor
- **Cost:** `{B}{B}`
- **Text:** Haste
  Shadow (This creature can block or be blocked by only creatures with shadow.)
  Whenever another creature is put into your graveyard from the battlefield, you may pay {B}. If you
  do, return this card from your graveyard to the battlefield.
- **Missing primitive:** `shadow keyword` — `game.Keyword` has no "Shadow" entry, and combat legality
  (who can block/be blocked) lives entirely in `backend/game/`, which this task must not touch. Haste
  and the reanimation trigger are unaffected by the gap. (`backend/cardfns/NetherTraitor.go`)

---

## Group 2 — "Hard" unproduced cards (5 cards)

`status: "review"`, no handler registered, sampled and ranked as more structurally complex
(multiple unparsed clauses and/or interacting abilities).

### 6. Xanathar, Guild Kingpin
- **Cost:** `{4}{U}{B}`
- **Text:** At the beginning of your upkeep, choose target opponent. Until end of turn, that player
  can't cast spells, you may look at the top card of their library any time, you may play the top
  card of their library, and you may spend mana as though it were mana of any color to cast spells
  this way.
- **Status:** review — 0 abilities parsed. Parser note: "Could not parse: At the beginning of your
  upkeep, choose target opponent..." (whole ability is one unparsed block).

### 7. Lluwen, Imperfect Naturalist
- **Cost:** `{2}`
- **Text:** When Lluwen enters, mill four cards, then you may put a creature or land card from among
  the milled cards on top of your library.
  {2}{B/G}{B/G}{B/G}, {T}, Discard a land card: Create a 1/1 black and green Worm creature token for
  each land card in your graveyard.
- **Status:** review — 0 abilities parsed, 2 separate unparsed clauses (ETB mill/reorder, and a
  hybrid-mana activated ability with a discard cost).

### 8. Birthing Pod
- **Cost:** `{3}{G}`
- **Text:** ({G/P} can be paid with either {G} or 2 life.)
  {1}{G/P}, {T}, Sacrifice a creature: Search your library for a creature card with mana value equal
  to 1 plus the sacrificed creature's mana value, put that card onto the battlefield, then shuffle.
  Activate only as a sorcery.
- **Status:** review — 2 abilities parsed, but the core tutor-and-upgrade ability is unparsed
  (Phyrexian-mana cost + sacrifice cost + relative-mana-value search + timing restriction all in one
  clause).

### 9. Falkenrath Forebear
- **Cost:** `{2}{B}`
- **Text:** Flying
  This creature can't block.
  Whenever this creature deals combat damage to a player, create a Blood token.
  {B}, Sacrifice two Blood tokens: Return this card from your graveyard to the battlefield.
- **Status:** review — 1 ability parsed (flying/can't-block), 2 unparsed clauses forming a
  self-contained recursion loop (damage trigger creates a resource, graveyard ability spends that
  resource to reanimate itself).

### 10. Mister Negative
- **Cost:** `{5}{W}{B}`
- **Text:** Vigilance, lifelink
  Darkforce Inversion — When Mister Negative enters, you may exchange life totals with target
  opponent. If you lost life this way, draw that many cards.
- **Status:** review — 0 abilities parsed. Parser note: "Could not parse: Darkforce Inversion...";
  conditional life-total swap feeding into a variable draw is a compound, state-dependent effect.

---

## Group 3 — "Medium" unproduced cards (5 cards)

`status: "review"`, no handler registered, sampled as more self-contained / lower interaction count.

### 11. Thran Turbine
- **Cost:** `{1}`
- **Text:** At the beginning of your upkeep, you may add {C}{C}. This mana can't be spent to cast
  spells.
- **Status:** review — 0 abilities parsed. Single triggered mana ability with a spend restriction the
  parser doesn't model.

### 12. Back to Nature
- **Cost:** `{1}{G}`
- **Text:** Destroy all enchantments.
- **Status:** review — 0 abilities parsed. One-line mass-destruction effect; simplest text in this
  sample, still unparsed as written.

### 13. Kor Cartographer
- **Cost:** `{3}{W}`
- **Text:** When this creature enters, you may search your library for a Plains card, put it onto the
  battlefield tapped, then shuffle.
- **Status:** review — 0 abilities parsed. Standard ETB land-tutor shape.

### 14. Covert Technician
- **Cost:** `{2}{U}`
- **Text:** Ninjutsu {1}{U} ({1}{U}, Return an unblocked attacker you control to hand: Put this card
  onto the battlefield from your hand tapped and attacking.)
  Whenever this creature deals combat damage to a player, you may put an artifact card with mana
  value less than or equal to that damage from your hand onto the battlefield.
- **Status:** review — 1 ability parsed (Ninjutsu), 1 unparsed damage-triggered cheat-into-play
  effect.

### 15. Tomb of the Spirit Dragon
- **Cost:** `{0}` (Land)
- **Text:** {T}: Add {C}.
  {2}, {T}: You gain 1 life for each colorless creature you control.
- **Status:** review — 1 ability parsed (basic mana ability), 1 unparsed conditional lifegain
  ability.

---

## Group 4 — Already produced (10 cards)

Mix of handler-tier (served by a Go file in `backend/cardfns/`) and record-tier (served directly as
a data record in `backend/data/carddb/`, no handler) cards, including two that were deliberately
collapsed from a handler down to a record.

### 16. Circuit Mender
- **Cost:** `{3}` (Artifact Creature — Insect, 2/3)
- **Text:** When this creature enters, you gain 2 life.
  When this creature leaves the battlefield, draw a card.
- **Outcome:** Record-tier. Originally a 27-line handler; **collapsed to a data record**
  (`backend/data/carddb/c.json`, `task-1656`) because both triggers are standard shapes — the
  handler only existed because the regex parser couldn't read "when this creature leaves the
  battlefield." Handler retired, no `CircuitMender.go` remains. `status: "manual"`. Tested by
  `backend/cards/shape_behavior_test.go`; see `docs/review.md` Appendix A.3.

### 17. Omnath, Locus of Creation
- **Cost:** `{W}{U}{R}{G}` (Creature, 4/4)
- **Text:** When Omnath enters, draw a card.
  Landfall — Whenever a land you control enters, you gain 4 life if this is the first time this
  ability has resolved this turn. If it's the second time, add {R}{G}{W}{U}. If it's the third time,
  Omnath deals 4 damage to each opponent and each planeswalker you don't control.
- **Outcome:** Record-tier. Handler used to implement only the ETB draw; **collapsed to a full
  AbilityDSL record** in `backend/data/carddb/o.json` (phase 3, per `docs/migration-plan.md`).
  `status: "manual"`. Tested by `backend/cards/collapsed_records_test.go`.

### 18. Serra Angel
- **Cost:** `{3}{W}{W}` (Creature, 4/4)
- **Text:** Flying
  Vigilance (Attacking doesn't cause this creature to tap.)
- **Outcome:** Record-tier, pure data — no handler has ever existed for this card. Defined directly
  in `backend/cards/starter.go:135` as stats + keywords; the engine implements what Flying/Vigilance
  mean once, in the combat rules. `status: "auto"`. Reference case in `docs/review.md` Appendix A.1.

### 19. Abaddon the Despoiler
- **Cost:** `{2}{U}{B}{R}` (Creature, 5/5)
- **Text:** Trample
  Mark of Chaos Ascendant — During your turn, spells you cast from your hand with mana value X or
  less have cascade, where X is the total amount of life your opponents have lost this turn.
- **Outcome:** Handler-tier. Served by `backend/cardfns/task302_abaddonthedespoiler.go` (registered in
  `_handlers.json` as `"card"`), with a matching behavioral test.

### 20. Academy Manufactor
- **Cost:** `{3}` (Creature, 1/3)
- **Text:** If you would create a Clue, Food, or Treasure token, instead create one of each.
- **Outcome:** Handler-tier. Served by `backend/cardfns/AcademyManufactor.go`, registered in
  `_handlers.json`.

### 21. Tavern Scoundrel
- **Cost:** `{1}{R}` (Creature, 1/3)
- **Text:** Whenever you win a coin flip, create two Treasure tokens.
  {1}, {T}, Sacrifice another permanent: Flip a coin.
- **Outcome:** Handler-tier. Served by `backend/cardfns/TavernScoundrel.go`, registered in
  `_handlers.json`.

### 22. Cayth, Famed Mechanist
- **Cost:** `{1}{W}{U}{R}` (Creature, 3/3)
- **Text:** Fabricate 1 (When this creature enters, put a +1/+1 counter on it or create a 1/1
  colorless Servo artifact creature token.)
  Other nontoken creatures you control have fabricate 1.
  {2}, {T}: Choose one — Populate. / Proliferate.
- **Outcome:** Handler-tier. Served by `backend/cardfns/CaythFamedMechanist.go`, registered in
  `_handlers.json`.

### 23. Chaos Wand
- **Cost:** `{3}` (Artifact)
- **Text:** {4}, {T}: Target opponent exiles cards from the top of their library until they exile an
  instant or sorcery card. You may cast that card without paying its mana cost. Then put the exiled
  cards that weren't cast this way on the bottom of that library in a random order.
- **Outcome:** Handler-tier. Served by `backend/cardfns/ChaosWand.go` — part of the `task-7275`
  cast-from-zone bundle, registered in `_handlers.json`.

### 24. Hordewing Skaab
- **Cost:** `{4}{U}` (Creature, 3/3)
- **Text:** Flying
  Other Zombies you control have flying.
  Whenever one or more Zombies you control deal combat damage to one or more of your opponents, you
  may draw cards equal to the number of opponents dealt damage this way. If you do, discard that many
  cards.
- **Outcome:** Handler-tier. Served by `backend/cardfns/HordewingSkaab.go` — part of the `task-7266`
  draw bundle, registered in `_handlers.json`.

### 25. Aang, Airbending Master
- **Cost:** `{4}{W}` (Creature, 4/4)
- **Text:** When Aang enters, airbend another target creature. (Exile it. While it's exiled, its
  owner may cast it for {2} rather than its mana cost.)
  Whenever one or more creatures you control leave the battlefield without dying, you get an
  experience counter.
  At the beginning of your upkeep, create a 1/1 white Ally creature token for each experience counter
  you have.
- **Outcome:** Handler-tier. Served by `backend/cardfns/AangAirbendingMaster.go`, registered in
  `_handlers.json`.
