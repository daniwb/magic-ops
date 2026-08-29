# Proposed universal occurrence inventory

## Design

One immutable snapshot contains every MTGJSON occurrence from every set's
`cards` and `tokens` collections. Named, versioned projections reference those
occurrences and carry inclusion/exclusion reasons. Unknown or anomalous rows
remain in the universal inventory.

```text
source_snapshot
  -> set
      -> source_occurrence --represents--> oracle_face
                           --other-face--> source_occurrence
                           --derived-from--> source_occurrence
  -> projection --membership--> source_occurrence
```

## Source snapshot (`magic.mtgjson-source-snapshot/v1`)

Required fields: schema, snapshot ID, MTGJSON version, metadata date, retrieval
time, download URL, media/format (`json.xz`), compressed byte count, compressed
SHA-256, repository provenance, canonicalizer ID/hash, and status.

`snapshot_id` is a hash of provider, MTGJSON version/date, payload SHA-256,
adapter hash, and schema version. Retrieval time is provenance and is excluded
from content identity.

## Set (`magic.mtgjson-set/v1`)

Required fields: snapshot ID, code, name, type, release date, online-only flag,
foil/nonfoil flags, foreign-only/partial-preview state when exposed, parent
code, base/total set sizes, and languages. Preserve omitted optional values as
null; do not coerce them to false.

## Source occurrence (`magic.mtgjson-occurrence/v1`)

Required fields:

- `source_occurrence_id = mtgjson:<uuid>` and raw `uuid`;
- source snapshot ID, source set key/code, and source collection (`cards` or
  `tokens`);
- collector number, language, availability, finishes, and identifiers;
- name and faceName as labels only;
- layout, side, text and text hash, types/subtypes/supertypes;
- `isOnlineOnly`, `isRebalanced`, and other exposed evidence without defaulting
  omitted values;
- zero or more typed relation targets from `otherFaceIds`,
  `originalPrintings`, and `rebalancedPrintings`.

Invariants: UUID is required and unique within the snapshot; every occurrence
is retained exactly once; source collection and set provenance are required;
names and array positions are forbidden identity inputs. Collector number and
language are provenance fields, not a compound identity.

## Oracle face (`magic.oracle-face/v1`)

`oracle_face_id = oracle:<scryfallOracleId>:<semantic-face>`, where
`semantic-face` is the explicit MTGJSON `side` or `none` when side is absent.
The raw Oracle ID and raw nullable side are retained separately.

This ID groups semantic content across occurrences. It is not unique per
printing and does not replace UUID. Text hashes are revision evidence, not
identity. If an upstream row ever lacks an Oracle ID, its oracle-face link is
null; no name-, text-, or position-derived semantic identity is invented.

## Relations (`magic.mtgjson-occurrence-relation/v1`)

Required fields: snapshot ID, relation type, source occurrence ID, target
occurrence ID, and evidence field.

Relation types:

- `other_face` from `otherFaceIds`;
- `derived_from_original` from `originalPrintings`;
- `has_rebalanced_printing` from `rebalancedPrintings`.

Relations are stored directionally exactly as exposed. Validation checks target
existence, self-links, duplication, and reciprocal consistency but does not
silently synthesize or remove a missing reverse edge. Meld and multi-side
objects may have more than one other-face target.

## Projection membership (`magic.inventory-membership/v1`)

Required fields: snapshot ID, policy ID/hash, source occurrence ID, included,
and sorted reason codes. A projection manifest contains exactly one decision
per universal occurrence. Its validator recomputes the rule and verifies
conservation.

Initial policies:

- `universal-occurrences-v1`: include all rows;
- `paper-occurrences-v1`: include when availability contains `paper`;
- `digital-occurrences-v1`: include when availability intersects
  `{arena, mtgo, dreamcast, shandalar}`;
- `nonpaper-occurrences-v1`: include when availability excludes `paper`.

These policies overlap except for the complementary paper/nonpaper partition.
Token, funny, set type, and layout remain queryable dimensions; no production
exclusion policy is selected by this session.

## Canonicalization and gates

JSON is UTF-8, key-sorted, compact, and newline-terminated. JSONL inventories
are sorted lexically by source occurrence ID. Relation rows sort by relation
type, source ID, target ID. Membership rows sort by policy ID then occurrence
ID. Large inventories are compressed/content-addressed outside normal Git
history; descriptors and compact fixtures stay in Git.

Required gates verify payload hash and metadata, UUID presence/uniqueness,
referential integrity, universal count conservation, exactly one membership
decision per occurrence/policy, policy recomputation, canonical byte form,
artifact hashes, and byte-identical rerun output.

Cross-snapshot changes use append-only `same_as`, `supersedes`, `split_from`,
`merged_from`, and `removed_from_source` records with old/new snapshot IDs and
evidence hashes. They must never be inferred from names alone.

