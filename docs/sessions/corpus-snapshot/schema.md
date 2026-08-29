# Proposed CorpusSnapshot v1 schema

## Descriptor (`magic.corpus-snapshot/v1`)

Required fields: `schema`, `snapshot_id`, `policy_id`, `policy_sha256`, `normalizer_id`, `normalizer_sha256`, `raw_corpus_sha256`, `member_count`, `parent_count`, `sorted_member_manifest_sha256`, and `member_manifest`.

`snapshot_id` is SHA-256 of canonical raw-corpus hash, policy hash, normalizer hash, and member-manifest hash. It is a snapshot descriptor identity, not a claim that the provisional source identity is accepted.

## Member (`magic.corpus-snapshot-member/v1`)

Required fields are `source_unit_id`, `identity_kind`, `scryfall_oracle_id`, `parent_id`, `parent_key` (label only), `face_name` (label only), `side`, `layout`, `oracle_text`, `source_text_sha256`, `types`, `subtypes`, `legalities`, `legality_class`, `printings`, `funny`, `digital`, `rebalanced`, `included_by_policy`, and `exclusion_reason_codes`.

Names and AtomicCards array positions are prohibited identity inputs. `source_unit_id` is provisionally `oracle:<oracle-id>:<side>` when present; the audit proves it needs an additional stable occurrence discriminator before adoption. `parent_key` is retained only as an upstream label. `parent_id` in the prototype is content-derived and therefore not a durable cross-snapshot ID.

Digital/rebalanced fields are tri-state dimensions. `unknown_not_exposed` is mandatory when the pinned source lacks authority; missing must never be normalized to false.

## Canonicalization

JSON is UTF-8, key-sorted, compact, newline-terminated. JSONL has one canonical member per line sorted lexically by `(source_unit_id, parent_id, source_text_sha256)`. Counts include rows, not unique provisional IDs; duplicates are reported and preserved. Exclusion reason codes are sorted and may overlap. Parent rollups count unique `parent_id` values.

## Required validation

A validator must verify schemas, raw hash, policy/normalizer hashes, member count, parent count, byte-canonical member ordering, member-manifest hash, descriptor snapshot hash, audit conservation, and second-run equality. Identity collisions are fatal for adopting an identity scheme but are preserved findings in this experiment.

## Cross-snapshot migration

A later schema must carry append-only `same_as`, `supersedes`, `split_from`, and `merged_from` relations with old/new snapshot IDs and evidence hashes. Text changes under a stable Oracle object are revisions, not new identity. Oracle splits/merges, side changes, parent regrouping, and fallback changes require explicit migration records.
