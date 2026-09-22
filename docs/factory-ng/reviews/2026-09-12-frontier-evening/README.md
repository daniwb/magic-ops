# Eight additional measured verb families

The user requested more categories to supply the idle Codex workers. A fresh
read-only census in an isolated clone at
`06a4c7e69744423dadf606c5107767f48fcb84e0` examined 16,976 review cards in
113.28 seconds. There were 10,686 cards with one remaining miss and 4,178
with two. Existing enabled families had 37 unaccounted one-miss candidates
when compared with current ticket history. The following excluded families
had another 165:

| Parser family | Existing runtime family | New candidates |
|---|---|---:|
| token_copy | token_copy | 36 |
| add_mana | add_mana | 28 |
| regenerate | regenerate / regenerate_target | 27 |
| p_sacrifice | edict_sacrifice | 25 |
| remove_counter | remove_counter | 21 |
| draw_eq | draw | 11 |
| p_discard_hand | discard | 9 |
| goad | goad | 8 |

All eight are now in the explicit producer allowlist. Tickets retain pinned
Oracle text and the complete-card gate, with family-specific requirements for
player choice, live counts, targets, restrictions, copy exceptions and duration.
Regeneration explicitly distinguishes self from the separately registered
targeted effect. Registry membership does not imply that every argument shape
works; unsupported behavior must still produce an atomic Engine dependency.

No unknown/static/replacement catch-all category was enabled. `p_gain_life`
also remains excluded: that parser label includes both life gain and loss, so
mapping the entire label to one effect would misstate its semantics. Missing
registered-runtime families such as `counter_unless` and `switch_pt` remain
excluded. No historical production keys or retry counters were reset. The
existing two-miss same-family pilot retains its two-active-ticket bound.

The configured producers now read
`measurements/producer-frontier-2026-09-12-evening.jsonl`; its counts are pinned
measurements, not promised card activations. The underlying census, registry
metadata and eight generated preflight TicketSpecs are in this directory.
Preflights invoke actual producer construction and exact-card revalidation,
pinning discovery to one measured member per new family; they were not enqueued.

Validation: nine frontier tests, twelve scan/controller performance tests,
twelve existing Go runtime shape tests, and eight actual TicketSpec preflights
passed. Tests reject missing registration, existing history and mixed misses
for every added family. Python compilation and whitespace checks passed.
An initial new test fixture used a plain lambda in place of a configurable mock;
that fixture was corrected before validation passed and activation occurred.

The producer script and plan configuration were atomically replaced under
dispatcher-admin after validation. No controller restart, worker preference,
quota, integration gate or game deployment change was needed for this expansion.
The preceding reserve-scheduling repair is documented separately.

Live proof: the expanded producer queued Brenard, Ginger Sculptor in the
`token_copy` family at 21:37:44 UTC. Claude leased it at 21:38:00 UTC while
codex-2 and codex-3 worked on Engine dependencies. `activation.json` retains
the snapshot. The latest completed queue snapshot still had zero runnable
tickets with admission/target both ten; the target has not yet been filled.
This proves new-family production and worker dispatch, not completed-card yield.
