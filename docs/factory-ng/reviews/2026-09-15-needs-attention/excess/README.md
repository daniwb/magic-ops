# Sequence excess damage recovery

Accepted candidate: `docs/factory-ng/runs/2026-09-15T195152Z-engine-operator-excess-damage-recovery-sep15-v1.json`.
All six candidate gates passed, including the original named test and complete
Game/Cards suite. The suite took 243 seconds under the local two-Go-worker cap.

Normal full integration passed nine checks, including the original semantic
selector, reparse/import, build, Game, focused checks, full six-shard suite and
push. Receipt:
`docs/factory-ng/runs/2026-09-15T195327Z-engine-operator-excess-damage-recovery-sep15-v1-1789502007732412258-integration.json`.
Pushed result: `581e6c1f2b8d64180e4248fa2e14ecf6bf0d461d`.
The original Engine ticket is an explicit integration parent so the controller
can reconcile it completed. No job-state edit or additional provider call.

The new `damage_by_chosen_source_power_record_excess` instruction accepts the
ordered controlled-source/opponent-recipient pair. It uses live power and the
existing damage pipeline, reporting actual excess after prevention/redirection.
`create_token` reads `count_spec: {count: excess_damage_dealt_this_way}` within
the same sequence. Zero or unresolved counts create no tokens. Custom token
specification preserves both Elf and Warrior subtypes and green color.

Coverage includes marked damage, lethal/sublethal/excess, partial and total
prevention, source protection, deathtouch, Infect, missing source, no retaliation,
separate resolution state, unchanged card definitions, and public conversion /
casting with counters plus a continuous power effect added after casting.
Only the Engine dependency is discharged; Map completion remains downstream.
