# Hand-size repair: existing parser ambiguity

The failed v2 conversion test parses:

`Storm Seeker deals damage to target player equal to the number of cards in that player's hand.`

A direct `cards.NewParser().Parse(text, "Instant")` probe returned:

- `MatchedPattern: storm_keyword`
- one static `storm` ability
- no parse errors, status `auto`

`patternStorm` in `backend/cards/patterns_keywords.go` matches `(?i)^Storm\b`,
so it consumes a card-name prefix as though the entire sentence were the Storm
keyword. The more specific `damage_target_player_equal_cards_in_hand` pattern
is never selected. This explains the nil SpellEffect in the v2 test; changing
amount conversion cannot fix an ability parsed as a static keyword.

The original conversion test is retained. It was not weakened by changing the
card name or injecting a synthetic parsed ability. A separate parser-boundary
repair needs to preserve real Storm clauses/reminders and allow this damage
sentence to reach the existing hand-size pattern. That parser file is outside
the failed Engine ticket's allowed scope. Probe source is retained alongside
this note; it was run in the isolated copy-recovery checkout.
