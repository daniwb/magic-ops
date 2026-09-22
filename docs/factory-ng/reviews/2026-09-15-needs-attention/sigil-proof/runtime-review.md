# Sigil full-card proof: discovered prerequisites

The first exact fresh-corpus proof failed (`initial-runtime-gates.json`): the active
legacy handler overrides the parsed record, auto-selects its target and only listens
to the older combat event. It cannot satisfy the required noncombat damage/player
choice/revalidation behavior. The public ResolveCombatDamage path additionally never
emits that combat event, while the normal phase path emits it from attacker power
even after prevention.

The bounded operator scope now includes retirement of the Sigil handler binding and
a generic actual-damage notification correction. Both combat paths emit the combat
notification once from the existing post-prevention emitter; the old duplicate
phase publication is removed, and group amounts use actual player damage.

The full-card test retains all original assertions and exercises both the real
ExecuteCurrentPhase path and the public direct resolver. It uses the original
freshly parsed abilities, public attachment/damage/target-choice/resolution APIs,
and no handler-disable environment override. The failed exact-profile model trial
remains historical evidence; an operator correction is not a successful model trial.

The group aggregator uses a temporary actual-combat collector rather than total
player damage: synchronous combat observers may deal additional noncombat damage,
which must not inflate the group. A new Game regression proves this distinction
and the prevented-damage case. The owned candidate check was stopped before this
change; all gates restart from the final source.
