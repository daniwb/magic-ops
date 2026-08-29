# Representative TicketSpec examples

These are design examples, not live tickets and not claims that the named
families remain unfixed. Hashes shown as placeholders would be compiler-filled.

## Example A: Map root cause — swallowed intervening condition

### Immutable scope manifest (abridged)

```json
{
  "scope_schema": "magic.scope/v1",
  "snapshot_id": "mtgjson:5.3.0+20260809:6a0235...bcfd:policy-TBD",
  "project_sha": "cccfbef6b4e3e397e4fe70d5aff44fd9c6d410dd",
  "representation_snapshot_hash": "69b278...b350",
  "root_cause_key": {
    "layer": "map",
    "detector": "span-conservation/condition-v1",
    "semantic_role": "condition",
    "canonical_family": "unless-pay-upkeep-cost",
    "required_behavior_version": "sha256:<behavior>",
    "normalizer_version": "source-v1"
  },
  "required_behavior": {
    "text": "Preserve and type the full unless-pay condition and its payment consequence; do not emit the unconditional payload.",
    "version": "sha256:<behavior>"
  },
  "members": [
    {"source_unit_id":"oracle:<id>:none","source_text_sha256":"<hash>","assertion_id":"<id>","span":[0,84],"before_reason_codes":["CONDITION_SPAN_UNMAPPED"],"gap_set":["map:unless-pay-upkeep-cost"]}
  ],
  "adjacent_negative_members": [
    {"source_unit_id":"oracle:<id2>:none","why":"ordinary one-time unless-pay counter clause must retain its different timing/choice semantics"}
  ],
  "predicted_unlock_members": ["oracle:<id>:none"],
  "dependency_bundle": ["map:unless-pay-upkeep-cost"],
  "scope_hash": "<compiler-filled>"
}
```

The real compiler includes every reproduced member; it never truncates to
examples. The existing swallow report's `creature unless you pay` cluster (17
cards) is discovery evidence, not automatically this scope: it must first be
partitioned by identical grammar and behavior.

### Compiled Map ticket (abridged)

```yaml
schema: magic.ticket/v1
work_type: map
title: Map one validated unless-pay upkeep-condition grammar family
premise:
  snapshot: <snapshot-id>
  reproduced_members: <exact count and manifest hash>
required_skill: implement-map-class@<hash>
allowed_paths:
  - scripts/paragraph/**
  - backend/cards/**
  - focused mapping fixtures
prohibited:
  - new engine behavior
  - name-keyed card special cases
  - dropping or auto-accepting the payment condition
success:
  - all original members remeasured and exhaustively partitioned
  - positive fixtures map condition, amount, payer, timing, and consequence
  - adjacent negatives unchanged
  - source-span conservation passes
  - no new swallow or gap-marker findings
  - actual recognized/expressible transitions listed by source_unit_id
refuse_when:
  - members require different required behaviors
  - representation or runtime capability is missing
  - pinned premise no longer reproduces
```

If engine support is missing, this Map attempt returns a structured dependency
contract and partitions affected members; it does not silently broaden itself
into Engine work.

## Example B: Engine root cause — represented primitive has no consumer

The historical `delve` finding is a useful shape: phase-analysis says 24 auto
uses existed while `CalculateDelve` had no callers. This is comparative
historical evidence only; premise verification decides whether it is current.

### Immutable scope manifest (abridged)

```json
{
  "scope_schema": "magic.scope/v1",
  "snapshot_id": "<snapshot-id>",
  "project_sha": "cccfbef6b4e3e397e4fe70d5aff44fd9c6d410dd",
  "root_cause_key": {
    "layer": "engine",
    "detector": "executor-reachability-v1",
    "semantic_role": "cost",
    "canonical_family": "delve-cost-payment",
    "required_behavior_version": "sha256:<behavior>",
    "normalizer_version": "source-v1"
  },
  "required_behavior": {
    "text": "During casting, permit exiling graveyard cards to pay one generic mana each, with choice, timing, and zone movement enforced through the real casting path.",
    "version": "sha256:<behavior>"
  },
  "members": ["<all mapped delve assertion receipts, not examples>"],
  "adjacent_negative_members": [
    "colored mana must not be paid by delve",
    "non-delve spells must not receive the option",
    "cards leave the caster's graveyard exactly once"
  ],
  "predicted_unlock_members": ["<exact dependent faces whose other gap set is empty>"],
  "dependency_bundle": ["engine:delve-cost-payment"],
  "scope_hash": "<compiler-filled>"
}
```

### Compiled Engine ticket (abridged)

```yaml
schema: magic.ticket/v1
work_type: engine
title: Wire atomic delve cost-payment behavior through the casting path
required_skill: implement-engine-capability@<hash>
preconditions:
  - existing-capability search receipt
  - all members share the same required behavior hash
  - dependent Map representations are expressible
allowed_paths:
  - backend/game/**
  - backend/cards converter/registry extension points named by the Skill
  - focused behavioral tests
success:
  - focused test traverses real cast/payment dispatch
  - mutation/revert of the new wiring makes the focused test fail
  - executor reachability ledger turns green for the behavior contract
  - colored-cost and non-delve adjacent negatives remain green
  - full required regression/honesty gates pass
  - dependent Map scope is remeasured and exact playable transitions recorded
  - every original member is in one terminal/residual partition
intermediate_verdict:
  implemented_pending_consumption: allowed, but capability remains open
refuse_when:
  - an existing live capability already satisfies the behavior
  - members conflate distinct choice/timing/zone semantics
  - correct support requires an architectural refactor outside ticket policy
```

## Example C: Co-occurring Map and Engine gaps

Assume faces have these complete gap sets:

```text
u1: {map:condition-X}
u2: {map:condition-X, engine:choice-Y}
u3: {engine:choice-Y}
u4: {map:condition-X, engine:choice-Y, engine:duration-Z}
```

At built set `{}`:

- marginal unlock of `map:condition-X` is `{u1}`;
- marginal unlock of `engine:choice-Y` is `{u3}`;
- bundle `{map:condition-X, engine:choice-Y}` unlocks `{u1,u2,u3}`;
- `u4` remains explicitly residual on `engine:duration-Z`.

The factory may prioritize either atomic ticket, or create a root mission with
both dependencies, but MUST NOT claim two-card unlock for either single ticket.
After both land, the root result partitions `u1/u2/u3` by the change that
actually caused their transition and retains `u4` with its full provenance.

## Required before/after receipts in every example

```json
{
  "before": {
    "project_sha": "...",
    "snapshot_id": "...",
    "scope_hash": "...",
    "command_receipts": [],
    "member_states_hash": "...",
    "global_honesty_baseline_hash": "..."
  },
  "after": {
    "candidate_or_landed_sha": "...",
    "command_receipts": [],
    "partitions": {
      "confirmed_fixed_by_change": [],
      "already_fixed_independently": [],
      "still_same_root_cause": [],
      "reclassified_root_cause": [],
      "invalid_input": [],
      "explicitly_unsupported": []
    },
    "partition_union_equals_scope": true,
    "collateral_regressions": [],
    "member_states_hash": "..."
  }
}
```
