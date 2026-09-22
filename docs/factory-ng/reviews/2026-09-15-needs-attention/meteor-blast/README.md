# Meteor Blast recovery

The reviewed retry emitted malformed replacement delimiters. Its proposed converter
connection also lacked real paid-X target validation; `CastXSpell` previously did
not check declaration count, duplicates or target legality before paying.

The correction connects only a fixed integer damage amount + any-target + paid-X
count atom. It registers the existing executor, adds explicit `ExactTargetsFrom`
metadata, and validates a copy carrying declared X through the shared target validator
before spending. Legacy spells without this metadata retain their behavior. Public
cast tests cover X=0/1/2, amount and paid mana on the stack, duplicates/illegal/wrong
counts without spending, one recipient leaving, and dynamic-damage negative cases.

All original candidate gates passed (`gates.json`). The local review driver initially
assumed every Engine candidate receives a vocabulary-handoff gate. The production
runner adds that gate only when ability_effects.go changes. The driver now verifies
the complete exact original command list instead of a hard-coded gate count;
`pre-work-type-gates.json` retains the earlier all-green gate evidence. No production
gate was removed. The candidate passed full production integration and pushed
`62f895ca4499af76b0bef13a486ba8c9eefaf4ae`; receipt
`../../../runs/2026-09-15T210349Z-engine-operator-meteor-blast-recovery-sep15-v1-1789506229829282334-integration.json`.
