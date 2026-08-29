# MTGJSON AllPrintings architecture review

Reviewed: 2026-08-27  
Verdict: `ACCEPT_WITH_REVISIONS`

All declared artifact hashes match and the supplied validator passes. The
session used same-release official AllPrintings and AtomicCards payloads,
performed a byte-identical rerun, retained only compact evidence, and deleted
the temporary upstream payloads.

## Accepted measurements

- MTGJSON release: `5.3.0+20260827`, date `2026-08-27`.
- 869 sets and 122,669 source occurrences: 113,597 card-collection rows plus
  9,072 token-collection rows.
- UUID: 122,669 present, 122,669 distinct, zero collisions in the snapshot.
- Scryfall Oracle ID: present on every occurrence; 38,626 distinct values.
- 10,494 directed `otherFaceIds` edges: zero dangling, self, or non-reciprocal
  edges; sides extend through `e`, not merely `a`/`b`.
- 235 rebalanced rows; all 394 original/rebalanced relation edges resolve and
  have the reverse evidence edge.
- Availability is present everywhere: 113,072 paper occurrences and 74,527
  occurrences on at least one measured digital platform, with overlap.
- The prior six Atomic identity collisions and all 70 cross-parent cases are
  preserved as distinct UUID occurrences rather than deduplicated.

## Architecture decisions accepted

1. MTGJSON remains the single corpus provider.
2. Pinned `AllPrintings` is the occurrence, product, availability, face-link,
   and rebalanced-relation authority.
3. `source_occurrence_id = mtgjson:<uuid>` is accepted within a pinned
   snapshot. Cross-snapshot continuity is measured and migration-recorded,
   never assumed silently.
4. `oracle_face_id` is a structured pair of Scryfall Oracle ID and nullable
   explicit MTGJSON side. It groups semantic content; it is not an occurrence
   identity. Serialization retains `side: null` rather than relying on a
   sentinel string as the authoritative representation.
5. One universal occurrence inventory preserves every cards/tokens row.
6. Named projections are complete membership/reason manifests over that
   inventory. Paper and nonpaper are complementary; digital is an overlapping
   availability view. Individual platform values remain visible.
7. Names, array positions, and `(set, number, language)` are labels/provenance,
   never identity.
8. AtomicCards remains a same-release compatibility regression input while the
   old pipeline is migrated; it is not source authority.
9. Large inventories live compressed and content-addressed outside ordinary
   Git history. Git retains schema, descriptors, generators, and compact
   fixtures.

## Required revision: occurrence inventory is not the work population

Factory corpus coverage, root-cause prevalence, marginal unlock, and ticket
scope operate on semantic Oracle faces/revisions, not printing occurrences.
Otherwise heavily reprinted cards would receive disproportionate weight.

The data model therefore has two linked snapshots:

```text
AllPrintings source occurrence inventory (122,669 in this release)
    -> group/audit by structured oracle_face_id
    -> canonical Oracle corpus snapshot (one semantic face revision each)
    -> named product eligibility derived from occurrence availability
    -> assertions, findings, root causes, and ticket scopes
```

An Oracle face is admitted only after its occurrence group is checked for
consistent current rules text, type/layout semantics, side, and revision. A
group with conflicting semantic payloads becomes an explicit source anomaly;
the generator must not choose an arbitrary printing. Tokens remain in the
universal occurrence inventory and receive a separate token-template projection
rather than inflating printed-card coverage.

## Remaining gates before TicketSpec

1. Build and validate the canonical Oracle-face snapshot from AllPrintings.
2. Measure UUID continuity against at least one retained adjacent MTGJSON
   release; record additions, removals, stable UUID content changes, and any
   reuse.
3. Audit semantic groups for multiple current text/type/layout hashes and define
   deterministic resolution or quarantine reason codes.
4. Define initial gameplay projections over Oracle faces: paper/nonpaper,
   funny/memorabilia, normal game cards, and token templates.
5. Define publication policy: identity/schema/conservation failures block;
   non-critical upstream relationship anomalies remain ingestible only in an
   explicit quarantined snapshot status.
6. Select the compressed content-addressed storage/retention mechanism before
   emitting the full production inventory.

No further provider-selection investigation is needed.
