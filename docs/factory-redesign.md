# Factory redesign: atomic capabilities and measurable attempts

Status: implementation branch; production rollout is intentionally paused.

## Problem

The staged pipelines made execution much cheaper, but a `REPARSE-MAP` ticket
can still group examples by an outer miss label while the examples require
unrelated engine behavior. A free-text `missing_prim` then loses the binding
between paragraph, required behavior, engine implementation, and parser retry.
This caused contradictory engine packs and duplicate primitives.

## Durable contract

`capabilities` stores one atomic engine behavior. `ticket_capabilities` is a
many-to-many dependency table: a ticket may need several capabilities and one
capability may unlock several tickets. A capability specification contains:

- one canonical `required_behavior`;
- exact card and oracle paragraph evidence;
- the same required behavior on every source miss;
- adjacent negative examples that must not change;
- estimated unlock, when known.

The dispatcher rejects mixed `required_behavior` values with HTTP 422. Reusing
a capability key merges source evidence; a conflicting behavior receives 409.
Legacy `missing_prim` and VOCAB paths remain available during migration.

## Pipeline lifecycle

1. Map pipeline either emits edits, an ordinary non-engine verdict, or one
   `CAPABILITY_JSON` object.
2. `capability-contract.py` registers and validates that object.
3. Missing/invalid contracts go to `capability_review`; no engine round runs.
4. A valid contract starts `reparse/capability-<id>` using the canonical spec.
5. After the integrator lands it, `/capability/complete` records the branch and
   commit and requeues dependent tickets only when all their capabilities are
   implemented.
6. A successful map retry marks ready dependencies `mapped`.

## Attempt ledger

Every map and engine invocation records:

- ticket and capability IDs;
- worker, pipeline, and model;
- ops SHA, gameplay SHA, and prompt-pack SHA;
- start/finish time and normalized outcome/failure kind;
- input/output/cache tokens;
- gate metrics such as miss counts.

Attempt rows are append-only in normal operation. `/attempt/finish` only
transitions a running attempt once, preventing later results from overwriting
the evidence used for comparisons.

## Migration

Do not infer capability contracts from legacy `missing_prim` strings.
`capability-migration-report.py` lists those tickets as
`needs_atomic_discovery`. Rediscover them from current oracle paragraphs and
current misses; old reply text may be supporting evidence but is not authority.

## Rollout

1. Commit and review this branch.
2. Merge or deliberately supersede the uncommitted live circle/MCP changes.
3. Back up the dispatcher database and deploy the schema/API migration.
4. Keep production claims paused; run the dispatcher against a copied DB.
5. Replay historical tickets 3481, 3482, 3484, and 3467 without pushes.
6. Confirm mixed tickets stop at capability review and atomic tickets create
   exactly one engine branch.
7. Run one canary lane with pushes disabled, then one production lane.
8. Compare confirmed unlocks, false parks, rework, tokens, and wall time before
   increasing concurrency.

## Test policy during the canary

Workers retain current gates until the contract flow is proven. Removing the
duplicate full suite is a later optimization: focused worker gates plus one
integrator batch suite should only be enabled after affected-package selection
has its own regression evidence.
