# Canonical Oracle-face snapshot schema

Canonical JSON is UTF-8, key-sorted, compact, and newline-terminated. The complete
snapshot is JSONL compressed with XZ and sorted by the structured key
`(scryfallOracleId, side)`, with null sorting before explicit side values.

## Oracle face

`magic.oracle-face/v1` contains `oracleFaceKey` with the upstream Oracle UUID and
structurally nullable `side`, plus a derived `oracleFaceId` display projection.
Identity never uses name, set, collector number, language, or row order.
`occurrenceIds` is the complete sorted membership and `availabilityUnion` is the
union over those occurrences. `dimensions` preserves collection, set-type,
layout, card-type, and funny/memorabilia evidence.

`canonicalSemanticRevision` audits and retains: rules text, type, types,
subtypes, supertypes, layout, mana cost, color identity, keywords, power,
toughness, and loyalty. Array fields are order-normalized. Missing and null are
both represented as JSON null because MTGJSON's accepted card model does not
assign distinct semantics to omission here. A revision is present only if every
occurrence agrees on every audited value. Otherwise status is `quarantined`, the
revision is null, and sorted `quarantineReasons` name each conflicting field.
Printing labels and product metadata may vary harmlessly and are not canonical
semantic fields.

## Relations

`magic.oracle-face-relation/v1` is a directed tuple of relation type, source
Oracle-face ID, and target Oracle-face ID. `other_face` is derived from
occurrence `otherFaceIds`; `derived_from_original` and
`has_rebalanced_printing` preserve original/rebalanced evidence. Occurrence
targets must exist and map to exactly one structured face. Union edges are not
silently synthesized in the source. Per-printing target-set disagreement is
reported separately with all distinct target sets. Sides `c` through `e` are
valid and validated identically to `a`/`b`.

## Membership

Every face record contains one `{included, reasonCodes}` decision for each
projection. Universal includes every valid Oracle-face group, including
quarantine. Paper is availability-union membership; nonpaper is its exact
complement. Platform views and the digital union overlap paper. Token templates
require at least one `tokens` collection occurrence. The normal-game candidate
uses explicit, reviewable exclusions for token provenance, funny/memorabilia,
and non-ordinary layouts; it is not production policy. Quarantine is a semantic
status, not an implicit projection deletion.

## Publication gates

Every occurrence maps exactly once; IDs and structured keys are unique; all
relation targets resolve; projection decisions conserve universal membership;
paper/nonpaper partition exactly; source, adapter, schema, and output hashes
match; canonical output validates; and a second run is byte-identical.
