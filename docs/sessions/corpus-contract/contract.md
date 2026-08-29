# Proposed Magic corpus contract v1

Status: proposed for Factory NG architecture review; not yet accepted.

## 1. Inputs

A measurement run MUST pin:

- `project_id`, Magic Git SHA, and dirty-tree state;
- upstream corpus file raw SHA-256 and upstream metadata;
- `population_policy_id` and hash;
- `normalizer_id` and hash;
- analyzer/linter/executor-ledger versions and hashes;
- canonical source-unit manifest hash and count;
- representation snapshot hash (carddb or successor);
- gate-policy version.

Changing any field creates a different run identity. Results from different
runs MAY be compared, but MUST NOT be unioned as if they share a population.

## 2. Source and evidence units

`source_unit` is one Oracle card face. Required fields are:

```json
{
  "source_unit_id": "oracle:<scryfallOracleId>:<side>",
  "parent_key": "MTGJSON AtomicCards key",
  "face_name": "printed face name",
  "side": "a|b|none",
  "layout": "...",
  "oracle_text": "verbatim",
  "source_text_sha256": "...",
  "types": [],
  "subtypes": [],
  "legalities": {},
  "included_by_policy": true
}
```

Missing Oracle IDs use the `fallback-v1:<sha256>` rule in `report.md`.
Duplicate IDs are fatal. Card names are labels, never identities.

An `assertion` is a located semantic unit within a face: keyword, cost,
trigger, condition, choice, target, effect, duration, replacement, restriction,
or linked reference. It has source byte span, verbatim text, role, and stable
content identity. Reminder/non-semantic spans are explicitly typed.

## 3. Analyzer output

For every included face, analyzers MUST emit:

- a lossless normalized source view and span map;
- all assertions and their parent/ordering/reference relationships;
- representation mapping or explicit unsupported/raw evidence per assertion;
- normalized findings with detector version and confidence/authority class;
- executor/test ledger links where mapped;
- face-level recognized, expressible, playable verdicts plus reason codes.

Unknown, unsupported, ambiguous, or raw content is data. It MUST NOT be dropped,
mapped to an unrelated default, or hidden only in logs.

## 4. Invariants

1. **Population conservation:** every run accounts for every source unit in the
   pinned population exactly once.
2. **Text conservation:** every semantic source span is covered by one or more
   explicitly related assertions; unexplained gaps and destructive overlaps
   fail recognition.
3. **Meaning conservation:** every assertion is either faithfully represented
   or explicitly unsupported/raw with the original span.
4. **Execution closure:** playable assertions link through the actual runtime
   dispatch path to an executor and a discriminating test receipt.
5. **Monotonicity:** playable implies expressible; expressible implies
   recognized.
6. **No proxy authority:** parser status, registry membership, handler
   presence, compilation, or a green broad suite is never sole proof.
7. **Scope conservation:** all members of a root scope survive merges, splits,
   retries, and reclassification as immutable before members and explicit
   after partitions.
8. **Determinism:** identical pinned inputs produce byte-identical manifests
   and finding keys. Ties use lexical stable IDs.
9. **No LLM identity authority:** models may propose clusters or explanations;
   deterministic code validates source IDs, counts, membership, closure, and
   deltas.
10. **Honest partials:** any unresolved assertion makes the face non-playable;
    supported assertions may still be reported separately.

## 5. Finding and root-cause model

```json
{
  "finding_id": "sha256(canonical finding fields + member locator)",
  "root_cause_key": {
    "layer": "source|map|representation|engine|test|integration",
    "detector": "stable detector id",
    "semantic_role": "condition|effect|cost|...",
    "canonical_family": "validated family id",
    "required_behavior_version": "hash or null",
    "normalizer_version": "..."
  },
  "member": {
    "source_unit_id": "...",
    "source_text_sha256": "...",
    "span": [0, 42],
    "assertion_id": "..."
  },
  "observed": "machine reason code",
  "evidence_hashes": []
}
```

Free text is explanatory, not identity. A proposed class becomes ticketable
only after a deterministic predicate reproduces every member and adjacent
negative fixtures bound it. Mixed `required_behavior` values MUST split.
Aliases and supersessions are append-only relations. Member removal requires a
recorded transition to fixed, independently fixed, reclassified, invalid, or
explicitly unsupported.

## 6. Dependency computation

For snapshot `S`, store the complete unresolved gap set `G_S(u)` per face (and,
where needed, per assertion). Produce:

- exact-set bundle counts;
- inclusion-minimal dependency bundles;
- pairwise co-occurrence counts and an explicitly versioned association score;
- sole-blocker sets;
- marginal unlock sets for a stated built set/order;
- full member manifests for every aggregate.

Greedy priority is a policy view, not identity. Weighting by formats, popularity,
cost, or risk MUST be a named versioned policy and MUST preserve raw counts.

## 7. Immutable root-ticket scope manifest

Every Map or Engine root ticket MUST embed or content-address:

```json
{
  "scope_schema": "magic.scope/v1",
  "snapshot_id": "...",
  "project_sha": "...",
  "representation_snapshot_hash": "...",
  "analyzer_bundle_hash": "...",
  "root_cause_key": {},
  "required_behavior": {"version": "sha256", "text": "..."},
  "members": [{
    "source_unit_id": "...",
    "source_text_sha256": "...",
    "assertion_id": "...",
    "span": [0, 0],
    "oracle_excerpt_hash": "...",
    "before_reason_codes": [],
    "gap_set": []
  }],
  "adjacent_negative_members": [],
  "predicted_unlock_members": [],
  "dependency_bundle": [],
  "generator_command": [],
  "generator_hash": "...",
  "scope_hash": "sha256(canonical object without this field)"
}
```

The ticket also pins work type, allowed/prohibited paths, required Skill hash,
tests/gates, dependencies, and terminal/refusal policy, but those belong to the
TicketSpec envelope. The scope manifest itself is immutable. Current status is
stored as a separate append-only result/partition manifest.

## 8. Before/after result contract

Before work, the harness MUST reproduce the root cause for all members and
record global honesty baselines. After applying the candidate on its resulting
commit, it MUST rerun the same analyzers over the original scope and the
defined regression population.

Result partitions are mutually exclusive and exhaustive:

- `confirmed_fixed_by_change`;
- `already_fixed_independently`;
- `still_same_root_cause`;
- `reclassified_root_cause`;
- `invalid_input`;
- `explicitly_unsupported`.

Each transition stores before/after reason codes and evidence hashes. The
partition union MUST equal the original member set. Duplicates are fatal.

Map completion additionally requires source/text conservation, representation
schema/linter success, positive and negative mapping fixtures, zero new global
honesty findings, and no undeclared Engine behavior.

Engine completion additionally requires one atomic behavior contract,
existing-capability search, real-dispatch and revert-sensitive behavioral
tests, runtime reachability, dependent Map consumption, and zero regression.
An Engine implementation may be marked `implemented_pending_consumption`; it
does not close until at least one dependent Map scope confirms use and all root
scope residuals are accounted for.

## 9. Gates

Minimum deterministic gates:

1. identity/schema validation;
2. population and text conservation;
3. root-cause reproducibility and homogeneous behavior contract;
4. representation closed-vocabulary/linter validation;
5. emitter-to-runtime reachability ledger;
6. discriminating focused tests (revert/mutation check where practical);
7. affected-package and project regression suites;
8. swallow/silent-loss and gap-marker non-regression;
9. original-scope remeasurement and exhaustive partition validation;
10. predicted-versus-actual member reconciliation;
11. fresh-context review of the pinned diff/result digest;
12. integration remeasurement on the landed commit.

Infrastructure failure yields no semantic verdict and preserves the attempt.
Candidate/heuristic detector findings cannot alone close or condemn a member.

## 10. Outputs

Every measurement produces content-addressed population, assertion, finding,
dependency, metric, and command-result manifests. Every ticket attempt adds
immutable before/after results. Human reports are projections from those data,
not competing authorities.
