# Factory NG corpus-contract research report

## Executive finding

The repository has enough machinery to seed a truthful corpus contract, but no
single current tool proves playability. `scripts/paragraph/classify.py` defines
one corpus filter, `reparse.py` exposes structured misses,
`coverage_planner.py` retains per-card miss sets, `swallow_audit.py` detects
several kinds of lost meaning, `primitive_inventory.py` looks for
parsed-but-inert verbs, and the Go tests exercise selected runtime paths. The
existing `backend/tools/report`, however, calls every `status:auto` record with
an ability "playable". Repository history records at least 12 parse-but-inert
classes and hundreds of swallowed fragments among such records. Its 44.881%
current result is therefore a legacy proxy, not the proposed metric.

The proposed contract makes the source face the population unit, a located
semantic assertion the audit unit, and a root-cause class the ticket unit. It
keeps `recognized`, `expressible`, and `playable` separate and monotone:

`playable => expressible => recognized`.

No status, parser success, registry entry, handler presence, or test-file name
alone establishes any of those implications.

## Evidence snapshot

- Magic SHA: `cccfbef6b4e3e397e4fe70d5aff44fd9c6d410dd`.
- magic-ops SHA: `df264369d5246b4b1b8d7575a9b1cd1b885efd4a`.
- `corpus/AtomicCards.json.gz`: MTGJSON `5.3.0+20260809`, dated
  `2026-08-09`, raw SHA-256
  `6a0235edf58fdd6947a84a4d5f8f27aeea899b179e46a14fd6356df368afbcfd`.
- Atomic top-level names: 35,013. Existing classifier filter: 34,049 faces,
  33,219 distinct `name` values. The 830 difference demonstrates that name is
  not a safe face identity.
- Committed `backend/data/carddb`: 30 JSON files, deterministic file-list hash
  `69b27883561e2b41f62db6b8cb5e47816a2fd4c6fb33747ea95a35f3436eb350`,
  30,102 records.
- Reproduction of `backend/tools/report` classification: 2,418 handler, 563
  spell-handler, 9,443 parsed, 1,049 vanilla, 37 manual, 8,827 partial, and
  7,765 blank. Its proxy says 13,510/30,102 (44.881%) playable.
- Current `corpus/swallow-audit-report.md`: 11,452 auto cards, 67
  candidate findings, with 915 handler-backed cards suppressed. The report
  itself warns that per-card scoping under-reports.
- Current `corpus/build-plan.md`: 21,175 blocked cards. Its greedy order retains
  only five examples per item in JSONL, and its refined leading-token buckets
  are approximations, so it is useful ranking evidence but not a closure
  manifest.
- `docs/paragraph-schema-v2.md` records 12 parse-but-inert classes affecting
  roughly 1,015 ability instances. `docs/phase-rs-factory-analysis.md` later
  records six auto-used inert candidates found by inventory inspection. These
  are direct counterexamples to parser/registry success as playability.

## Authoritative unit and identity

The authoritative population unit should be an **Oracle source face**, not a
printing, carddb row, paragraph, or card name. A face is the smallest source
object with its own rules text while still carrying the type, layout, side,
legality, and parent-card context needed to interpret it.

Each snapshot materializes a canonical `source_unit_id`:

1. prefer `identifiers.scryfallOracleId + ":" + side` when present;
2. otherwise use `sha256(canonical JSON of parent atomic key, faceName, side,
   layout, text, types, subtypes)` with an explicit `fallback-v1:` prefix;
3. fail snapshot compilation on duplicate IDs; never append an unstable array
   index to resolve a collision.

Paragraphs, modes, costs, conditions, and effect atoms are subordinate located
units. Their stable identity is `(source_unit_id, source_text_sha256,
normalizer_version, start_byte, end_byte, role)`. A new text hash creates a new
source revision; it never silently retargets old evidence.

The **snapshot identity** is a content-addressed descriptor containing raw
upstream hash and metadata, filter-policy version/hash, normalizer version,
sorted canonical source-unit manifest hash, and unit count. Git SHA is recorded
but is not a substitute for corpus content identity.

The existing classifier filter is evidence, not yet a settled policy: it drops
funny cards, six layouts, and eleven types (including Battle), whereas
`coverage_planner.py` applies additional legality and layout rules only to one
of its input pools. Factory NG must use one compiled population manifest for
all analyzers.

## Detecting loss and incomplete behavior

Silent loss is detected by source-accounting, not absence of parser errors.
Every non-reminder source span must be covered exactly once by a typed node, an
explicit unsupported node retaining the verbatim span, or documented
non-semantic material. Overlaps and uncovered spans fail recognition. The
existing heuristic swallow detectors remain useful secondary alarms; they do
not replace span conservation.

Parsed-but-inert behavior is detected by a generated reachability ledger from
each emitted semantic kind/verb through registry/adaptation and real runtime
dispatch to an executor, plus a discriminating test receipt. Static text,
activation costs, choices, durations, conditions, and replacement effects must
be audited as first-class roles. `primitive_inventory.py` is a useful seed but
its own documentation correctly calls its flags candidates: quoted references
and switch arms are not proof of execution.

Partial support is explicit whenever any located assertion is unsupported,
raw, ambiguously mapped, inert, untested, or fails an honesty/runtime gate. The
face is not playable, even if other assertions work or a handler exists.
Partial partitions remain visible and clusterable.

## Stable root causes and scope conservation

A normalized finding has a stable structured key, not a free-text label:

`(layer, detector, semantic_role, canonical_family, required_behavior_version,
normalizer_version)`.

Evidence members are stored separately and never embedded as the identity.
Aliases may merge old keys into a new canonical key, but merges preserve every
member and provenance edge. Splits create explicit residual partitions; they do
not rewrite history. Catch-all/leading-token buckets from the current planner
are discovery groups until a validated root-cause rule partitions them.

For every face `u`, let `G(u)` be its complete set of unresolved canonical gaps.
Co-occurrence is the multiset of exact gap sets and the pairwise count/weighted
count derived from them. For a proposed built set `B`, the marginal unlock of
gap `g` is `{u | G(u) is nonempty and G(u) subseteq B union {g}}` minus already
unlocked units. Minimal dependency bundles are the distinct inclusion-minimal
gap sets `G(u)` (or explicitly versioned weighted variants), with all member
faces retained. The current greedy planner approximates this and is retained
only after it emits full member sets, deterministic tie-breaking, and snapshot
metadata.

## Ticket success evidence

A Map ticket succeeds only if the pinned before classifier reproduces its
scope, the mapping change passes positive and adjacent-negative fixtures, every
original member is remeasured, recognized/expressible deltas match the member
partition, no new loss appears outside scope, and all residuals are linked or
terminally accounted for.

An Engine ticket succeeds only if one atomic behavior has real-path,
revert-sensitive tests, executor reachability passes, dependent Map fixtures
consume it, every predicted member is remeasured, regressions are zero, and
residuals are conserved. A merged primitive with no dependent face becoming
truthfully playable is implemented code, not a closed capability.

Both tickets store immutable before and after result manifests, command,
tool/version hashes, exit status, stdout/stderr artifact hashes, repository
SHAs, and per-member transitions. Aggregate delta never substitutes for the
member list.

## Tool disposition

| Tool | Disposition | Reason |
|---|---|---|
| `classify.py` | repair/retain | Deterministic and corpus-wide; must consume the common population manifest and emit located assertions. |
| `reparse.py` and slot parsers | repair/retain | Best current source of structured misses; must emit stable finding schema, spans, and total source accounting. |
| `coverage_planner.py` | repair/retain | Correct direction on full miss sets and marginal unlock; must stop using approximate buckets as ticket roots and retain all members/bundles. |
| `swallow_audit.py` | retain as alarm | Valuable detectors and historical yield; currently candidate-level and under-reporting, so not sole authority. |
| `primitive_inventory.py` | repair/retain | Good generated inventory/refusal input; static evidence must be joined to runtime reachability and test receipts. |
| `backend/tools/report` | retain as legacy view, replace for NG metrics | Tier/status inventory is useful; its `playable` formula is unsound. Rename that field before reuse. |
| carddb linter, gap-marker test, shape tests | retain/strengthen | Useful honesty gates; shape tests must be mapped to semantic contracts and real dispatch paths. |
| handler per-card tests | retain as evidence, audit | Presence is not proof; require indexed, revert-sensitive behavior claims. |
| `scan_silent_static.py` | retire after detector migration | Hard-coded external corpus path, heuristic, ticket-writing side effect, and secrets/network coupling; move detector into pure audit. |
| `playtest_all.py` | retire from corpus authority; redesign as smoke/fuzz evidence | Non-deterministic bots and API errors cannot prove card semantics; it also couples ticket filing and credentials. |
| phase.rs exports/workflow | comparative evidence only | Useful typed-condition data and review patterns; its workflow and schema are not Magic authority. |

## Recommendations

1. Compile one immutable population manifest before TicketSpec v1.
2. Add source-span conservation and explicit unsupported nodes before claiming
   recognized coverage.
3. Generate a semantic-contract ledger joining emitters, representation,
   runtime consumers, and discriminating tests.
4. Upgrade planner output to full, content-addressed scopes and exact dependency
   bundles before it creates tickets.
5. Rename all legacy `playable` output until it meets the proposed formula.
6. Treat the numerical thresholds and filter policy listed in
   `open-questions.md` as unmeasured decisions, not facts.

## Important commands

Commands were read-only and run from `/opt/development/magic-new` unless noted:

```text
git -C /opt/development/magic-new rev-parse HEAD
git -C /opt/development/magic-ops rev-parse HEAD
sha256sum corpus/AtomicCards.json.gz corpus/Keywords.json
gzip -cd corpus/AtomicCards.json.gz | jq -r '.meta, (.data|length)'
python3 -c '<filter-equivalent corpus population and canonical hash measurement>'
find data/carddb ... | sort -z | xargs -0 sha256sum | sha256sum
python3 -c '<backend/tools/report-equivalent classification over carddb>'
```

Exact expanded measurement commands are recorded in `manifest.json`.
