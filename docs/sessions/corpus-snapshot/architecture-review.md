# CorpusSnapshot v1 architecture review

Reviewed: 2026-08-27  
Verdict: `ACCEPT_WITH_REVISIONS`

All declared artifact hashes match. The supplied validator passes, and the
session's two-run comparison reports byte-identical manifests and audits. No
coverage or production-ticket claim was made.

## Measured results accepted

| Candidate projection | Faces | Parents | Architectural use |
|---|---:|---:|---|
| `classifier-compatible-v1` | 34,049 | 33,219 | legacy comparison only |
| `schema-non-funny-v1` | 34,576 | 33,707 | current diagnostic non-funny projection |
| `paper-product-v1` | 33,678 | 32,822 | provisional legality proxy only |

The raw inventory contains 35,958 faces. AtomicCards exposes no authoritative
digital/rebalanced fields, so those dimensions are correctly reported as
`unknown_not_exposed`.

The identity audit is decisive:

- zero missing Scryfall Oracle IDs in this snapshot;
- six duplicate `oracleId + side` keys;
- 70 Oracle IDs appearing in multiple content-derived parent groups;
- some collided rows have different text hashes.

Therefore `oracleId + side` is not a unique source-row identity.

## Architecture decisions accepted

1. Maintain one universal source inventory containing every upstream row,
   including excluded rows and their evidence.
2. Population policies are named, versioned projections over that inventory;
   exclusions are reason-coded membership decisions, never deletion.
3. Retain `classifier-compatible-v1` only for historical comparison.
4. Use the non-funny projection as the initial diagnostic working surface.
5. Do not adopt the legality-based `paper-product-v1` as production authority.
   Use MTGJSON `AllPrintings` as the pinned product/printing authority and
   derive the production projection from its explicit fields.
6. Model two linked identities:
   - `oracle_face_id`: semantic Oracle object plus side/revision relations;
   - `source_occurrence_id`: unique upstream product/parent/face occurrence.
7. Oracle text hash is revision evidence, not the sole durable identity.
8. Cross-snapshot splits, merges, regrouping, and aliases are append-only
   migration relations.

## Required revisions

1. The current member schema and descriptors are prototypes because
   `source_unit_id` is non-unique. They must not be promoted unchanged to v1.
2. Replace three duplicated full included-member manifests with:
   - one canonical universal inventory;
   - compact projection membership/reason manifests referencing occurrence IDs.
3. Full excluded rows must be mechanically recoverable, not represented only
   by counts and three Markdown/JSON examples.
4. Acquire and measure pinned MTGJSON `AllPrintings` before settling the
   production projection or occurrence identity. Do not add a second data
   provider merely to fill fields already present in MTGJSON.
5. Strengthen validation to require unique `source_occurrence_id`, projection
   union/conservation against the universal inventory, and policy membership
   recomputation.
6. Do not include `prototype/__pycache__` in canonical artifact hashes.
7. Store large generated JSONL compressed or content-addressed outside normal
   Git history; keep descriptors, schemas, hashes, and small fixtures in Git.
   The experimental directory currently occupies about 108 MB.
8. A clean worktree is required for an accepted production snapshot generator.
   Research snapshots may record dirty state and remain explicitly provisional.

## Next bounded investigation

Validate MTGJSON `AllPrintings` as the single source for stable printing/card
identifiers, set/product membership, paper/digital availability, rebalanced
identity, parent/face relationships, and Oracle IDs. `source_occurrence_id`
starts as MTGJSON `uuid`; `oracle_face_id` starts from `scryfallOracleId` plus
semantic face linkage. Compare it with AtomicCards on a bounded fixture
containing the six collisions, reversible cards, digital/rebalanced cards,
Battles, split/adventure/DFC cards, and funny cards. Produce the dual-identity
mapping and universal-inventory schema; do not yet build coverage or tickets.
