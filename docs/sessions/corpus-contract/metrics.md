# Corpus metrics v1

Status: proposed definitions; current numeric values are not yet measurable
without the contract tooling described here.

## Population and notation

For one pinned snapshot, `U` is the set of included source faces. For face `u`,
`A(u)` is the complete set of semantic assertions produced by lossless source
accounting. `w(u)` defaults to 1. Any other weighting is a separately reported,
versioned policy view.

All primary coverage numbers report numerator, denominator, percentage,
snapshot ID, population policy, and reason-code histogram. Never report only a
percentage.

## Recognized

An assertion `a` is recognized iff:

1. its exact source span is retained;
2. its semantic role and structural relationships are classified;
3. no semantic token in its span is silently discarded or defaulted contrary
   to the source;
4. uncertainty is explicit as typed raw/unsupported evidence.

A face is recognized:

`R(u) = source_accounting_complete(u) AND forall a in A(u): recognized(a)`.

Explicitly unsupported meaning can be recognized. An unclassified but retained
raw blob is evidence, not recognition, unless its role and boundaries are
known under the accepted schema policy.

`recognized_coverage = sum(R(u)) / |U|`.

Also report assertion coverage:

`recognized_assertion_coverage = recognized assertions / all assertions`.

## Expressible

An assertion is expressible iff it is recognized and the typed project
representation can encode its full behavior, including subjects, targets,
quantities, conditions, choices, ordering, duration, zones, costs,
replacements, and references, without lossy raw fields or semantic defaults.

`E(u) = R(u) AND forall a in A(u): typed_lossless_mapping(a)`.

Handler-only behavior is not representation-expressible merely because Go can
implement it. If the architecture chooses to count handlers in a broader
"implementable" metric, that MUST be a separately named metric.

`expressible_coverage = sum(E(u)) / |U|`.

## Playable

An assertion is playable iff it is expressible and:

- its represented kinds and parameters reach a real runtime consumer;
- relevant costs, choices, triggers, conditions, durations, replacements, and
  state changes are enforced, not merely stored;
- a discriminating test mapped to its behavior contract traverses the real
  dispatch path and would fail if the behavior were removed or materially
  inverted;
- all applicable honesty and runtime gates pass.

A face is playable:

`P(u) = E(u) AND forall a in A(u): runtime_supported(a) AND
all_applicable_face_gates(u)`.

`playable_coverage = sum(P(u)) / |U|`.

This intentionally excludes a parsed-but-inert record, an auto record with a
swallowed condition, a handler whose test does not cover all assertions, and a
primitive registered without consumption proof.

## Partial support

For face `u`:

`supported_fraction(u) = playable assertions / |A(u)|`.

This is diagnostic only and MUST NOT be averaged into playable coverage without
also showing face-level coverage. Report faces by exact status vector:

`(recognized, expressible, playable)` plus unresolved reason codes. By
invariant, only `000`, `100`, `110`, and `111` are valid.

## Silent loss, inertness, and gap metrics

- `uncovered_semantic_spans`: count and member set of semantic source spans
  without assertions.
- `destructive_overlap_spans`: incompatible assertion overlaps.
- `swallow_findings`: candidate alarms by detector; never mixed into confirmed
  loss without adjudication authority.
- `confirmed_silent_loss_faces`: faces with a mechanically proved conservation
  violation.
- `inert_assertions`: mapped assertions lacking runtime reachability.
- `untested_runtime_contracts`: reachable behaviors lacking a qualifying test.
- `gap_prevalence(g) = |{u: g in G(u)}|`.
- `sole_blocker(g) = |{u: G(u) = {g}}|`.

## Co-occurrence and dependency bundles

Raw pairwise co-occurrence:

`cooccur(g,h) = |{u: {g,h} subseteq G(u)}|`.

Also report Jaccard as a secondary, versioned view:

`J(g,h) = cooccur(g,h) / |{u: g in G(u) OR h in G(u)}|`.

An exact bundle is one distinct nonempty set `G(u)` with its complete member
list. A minimal bundle is an inclusion-minimal such set among the chosen
population. Multiplicity is retained; supersets are not discarded, because
their members still require additional work.

For built set `B`:

`unlocked(B) = {u: G(u) nonempty AND G(u) subseteq B}`.

`marginal_unlock(g | B) = unlocked(B union {g}) - unlocked(B)`.

For bundle `D`:

`marginal_unlock(D | B) = unlocked(B union D) - unlocked(B)`.

Greedy order recomputes marginal sets after every selection, uses lexical gap
key for ties, and stores full sets. An item chosen to break a zero-gain
deadlock has marginal unlock zero; frequency is not mislabeled as unlock.

## Ticket outcome metrics

Let original immutable scope be `S`, and after partitions be `F` fixed by this
change, `I` independently fixed, `Q` still same cause, `X` reclassified, `V`
invalid, and `N` explicitly unsupported.

Required invariant:

`S = disjoint_union(F, I, Q, X, V, N)`.

- `confirmed_delta = |F|` (plus weighted view if declared).
- `scope_accounting_ratio = |F union I union Q union X union V union N| / |S|`;
  MUST equal 1 before an attempt can finish.
- `scope_completion_ratio = |F union I union V union N| / |S|`.
- `residual_ratio = |Q union X| / |S|`.
- `prediction_precision = |F intersect predicted_unlock| / max(1, |F|)`.
- `prediction_recall = |F intersect predicted_unlock| / max(1,
  |predicted_unlock|)`; label zero-denominator cases explicitly.
- `collateral_regressions`: newly non-recognized, non-expressible, non-playable,
  or changed adjacent-negative members outside the intended transition. Must be
  zero for ordinary completion.

`delta > 0` is progress, not closure. An Engine ticket additionally reports
`dependent_consumption_count` and cannot close at zero.

## Current compatibility baselines

These are reproducible legacy/tool counts, not values of the proposed metrics:

| Measure | Value | Why not authoritative |
|---|---:|---|
| Existing classifier-filter faces | 34,049 | Filter policy is inconsistent with planner import rules and still undecided. |
| Committed carddb records | 30,102 | Name-keyed representation rows are not the source population. |
| Legacy report `playable` | 13,510 / 30,102 (44.881%) | Counts handler presence and auto parse status without complete semantic/runtime proof. |
| Current auto swallow-audit population | 11,452 | Subset/proxy; 915 handler-backed suppressed and audit says it under-reports. |
| Current swallow candidates | 67 | Heuristic candidates, not adjudicated confirmed loss. |
| Current planner blocked pool | 21,175 | Combines pools/filters and uses approximate refined buckets. |

Until the new ledger exists, Factory NG MUST label these `legacy_proxy` or
`candidate`, never `recognized`, `expressible`, or `playable`.
