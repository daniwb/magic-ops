# Five-card staged continuation trial — September 8, 2026

Later September 8 decision: the user authorized ordinary Claude routing to
staged with agentic as an evidence helper. See [the new policy](../staged-first-routing/README.md).
This exact-profile cohort remains unassisted; its pending results do not prove
the ordinary assisted route meets the token target.

Authorized by the user after comparing recent staged and agentic receipts.
This is a continuation trial for five audited cards, not a from-scratch cost
claim. Earlier Map, Engine and repair receipts are retained as a separate
baseline. The 200k–500k target is raw processed Claude tokens per complete card;
it is not a quota-weighted or monetary measure.

The frozen [manifest](manifest.json) contains Siegfried, Sigil of Sleep,
Skittering Cicada, Rakdos Roustabout and Sea God's Scorn, exact Oracle text,
previous tickets, known dependency status, and complete-card checklists.
Tidal Surge is excluded because it exhausted its existing Map repair budget.

The factory admits at most two active trial jobs through the regular controller.
The secondary Claude worker can handle this cohort's Map work as well as Engine
work. Trial TicketSpecs use `profile_policy: exact` and only
`claude-staged@1.0.0`; dependencies and successors retain cohort identity and
routing. Ordinary Map work is not newly promoted to this worker. Primary
agentic remains available; this trial does not automatically use it or change
the global default. A specific missing-evidence investigation would need a
separately attributed ticket, not an invisible fallback.

Each card starts with a fresh, pinned Map successor. After that Map integrates,
the factory emits a separate test-only Engine ticket requiring the actual
corpus card to pass through fresh Python parsing, CardDefinition conversion,
and public game actions/target selection/resolution. A parser eligibility
result or accepted patch is not a completed card. Named behavior tests,
package tests, and the normal full integration gates remain required. Trial
verification failures remain visible; the harness's existing bounded correction
and repair limits are not reset. No live deployment is enabled.

[status.json](status.json) is regenerated during factory producer sweeps. It
contains every trial observation, failed attempts, known and unavailable
counters, historical costs, model time, changed files, and integration state.
Run `python3 scripts/factory-ng-staged-trial.py --report` from magic-ops for a
fresh report. Shared historical dependencies may appear for multiple cards;
do not add those per-card baseline totals as if they were unique spending.
The report does not include this operator session's tokens or deterministic
build/test time, which have no comparable model-usage counter in the receipts.

The decision remains pending until the card tests and costs are reviewed.
Five continuation cases cannot establish an unseen-card median or sustained
100 cards/day. Keep the quota-week measurement as a separate outstanding item.

Validation: seven new cohort tests, 65 controller tests, 19 reliability tests,
eight repair-lineage tests and 15 staged-runner tests passed (114 total), plus
all five enabled profile definitions. Controller tests use an isolated source
checkout to avoid racing ongoing integration. Worker and producer configuration
before this trial is saved in the adjacent `before-*.json` files; restore only
trial-specific fields under dispatcher-admin lock, preserving later changes.
