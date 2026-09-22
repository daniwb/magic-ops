# Audited Engine repairs and factory handoff — September 8

All four corrections passed full production integration and were pushed at
`8bc157460b32e83008a0d6b176c03285f5d87826`. No live deployment was performed.
The canonical checkout is clean. The [integration receipt](../../../runs/2026-09-08T162342Z-wave-122f1228e4f4-integration.json)
records every gate; `publication.json` records the four published successors
and observation receipts.

Four bounded corrections implement the gaps demonstrated by the eight-miss
review. The isolated candidate branch starts at `6642351731`; `manifest.json`
binds each immutable corrected TicketSpec, patch, candidate commit and focused
test selector. `observations.json` lists the corresponding accepted operator
observations. These are operator repairs, not evidence of autonomous model
throughput or measured model-token usage.

| Correction | Representation and runtime behavior | Verification |
| --- | --- | --- |
| Dynamic counters | Existing `amount_count` preserves zero after mill/count; omitted static amount still defaults to one; monstrosity zero still sets its designation. | Ordered mill/count execution, positive and zero counts, unrelated graveyard, unknown count and defaults. |
| Triggering spell mana value | New count `event_subject_mana_value` feeds existing `pt_amount_count`; existing keyword grant composes with the pump. Trigger context preserves announced X after the original spell leaves the stack. | Zero and positive value, repeated triggers, end-of-turn expiry, countered X spell and existing power-only behavior. |
| Up to N targets | Explicit `min_targets=0,max_targets=3` survive conversion; common casting validation rejects excessive/duplicate/illegal targets before spending. Bounded spells revalidate selected targets at resolution. | Native definition through normal and granted alternate casting, zero/one/three/four targets, duplicates, no rejected-cast mutation, resolution legality and legacy required targets. |
| Player damage | New `player_damaged` event reports actual post-prevention damage. Enchanted-source filtering and existing `defending_player` qualification connect the damaged player to target choice. | Combat/noncombat, prevention, unrelated sources/life loss, owner hand, target control changes, converter-to-trigger-to-resolution path. |

Nine new test functions pass. The full `game` and `cards` packages pass on the
combined candidate. Normal integration additionally checks each candidate,
reparses/imports the corpus, builds, runs focused gates and the six-shard suite.
All these gates passed without excluded candidates. Final integration and
publication evidence is recorded in `publication.json`.

The corrected target-count successor explicitly replaces the incorrect
one-to-three premise with zero-to-three. Existing immutable tickets are
retained. Source contracts are reused by resumed Map work; Engine integration
alone does not establish that every ability of the six audited cards works.

The accompanying factory changes and their 116 Python tests are documented in
[the discovery and handoff report](../factory-discovery-and-handoff-repair.md).
They are active, and an unrelated completed Engine dependency has already
resumed automatically as an A-Radha Map ticket. Actual card acceptance,
remaining integration failures, dashboard statistics and sustained throughput
measurement remain separate obligations.

Post-publication verification: the live controller marks all four successors
completed and their predecessors superseded (`controller-reconciliation.json`).
Canonical HEAD and origin/main match, the tree is clean, and the dashboard
responds HTTP 200. A knowledge-service lookup for `emitPlayerDamaged` refreshed
to the integrated revision and returned the new exact symbol with
`index_stale=false` (`post-integration-knowledge.json`). Dependent Map work
remains subject to the bounded reserve and normal complete-card gates.
