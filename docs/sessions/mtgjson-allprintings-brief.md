# Factory NG MTGJSON AllPrintings Validation — Dedicated Session Brief

Status: ready for a separate Codex session  
Decision already made: remain with MTGJSON as the single corpus provider  
Output directory: `/opt/development/magic-ops/docs/sessions/mtgjson-allprintings/`

## Mission

Validate pinned MTGJSON `AllPrintings` as Factory NG's occurrence/product
authority and produce the revised dual-identity and universal-inventory schema.
AtomicCards is a derived compatibility input, not identity authority.

Read completely before acting:

- `/opt/development/magic-ops/AGENTS.md`
- `/opt/development/magic-ops/docs/sessions/corpus-snapshot/architecture-review.md`
- `/opt/development/magic-ops/docs/sessions/corpus-snapshot/schema.md`
- `/opt/development/magic-ops/docs/factory-ng-plan.md`

## Source and safety

Use official MTGJSON downloads/documentation only. Pin raw download hash,
MTGJSON version, metadata date, format, and retrieval time. Prefer a compressed
format and stream it where practical. Check free disk before downloading or
expanding; stop with a structured blocker rather than risking disk exhaustion.
Do not place a large upstream payload or generated full inventory in normal Git
history. Temporary payloads may live outside the repository and must be listed
in the session manifest with cleanup/recovery status.

If AtomicCards is compared globally, it must be from the same MTGJSON release.
Otherwise limit comparison to explicitly labeled fixtures and do not imply
cross-release equality.

## Required validation

Measure, rather than assume:

1. uniqueness, presence, and stability role of MTGJSON `uuid`;
2. `scryfallOracleId`, `side`, `otherFaceIds`, and multi-face relationships;
3. `availability`, set metadata, `isOnlineOnly`, and paper/digital projection;
4. `isRebalanced`, `originalPrintings`, and `rebalancedPrintings` relations;
5. product/set/collector-number fields needed for occurrence provenance;
6. behavior of tokens, funny cards, Battles, reversible cards, split,
   adventure, transform/modal DFC, meld, and unusual multi-side objects;
7. the six AtomicCards identity collisions and the 70 cross-parent Oracle-ID
   cases from the previous experiment;
8. deterministic canonicalization and byte-identical rerun output.

Proposed starting model to validate:

```text
source_occurrence_id = mtgjson:<uuid>
oracle_face_id       = oracle:<scryfallOracleId>:<semantic-face>
occurrence --represents--> oracle face
occurrence --other-face--> occurrence
rebalanced --derived-from--> original occurrence(s)
population policy = named projection over one universal occurrence inventory
```

Reject or revise any part that the data falsifies. Never use name or array
position as identity.

## Boundaries

- Do not change production code, corpus files, dispatcher state, workers,
  services, tickets, branches, or canonical NG documents.
- Do not calculate recognized, expressible, or playable coverage.
- Do not generate production tickets.
- Do not add Scryfall as a second authority; its identifiers inside MTGJSON are
  data fields, not a second ingestion pipeline.
- Preserve anomalies and unknowns; do not silently deduplicate.

## Required artifacts

Write under the output directory:

- `report.md` — findings and recommendation;
- `source-manifest.json` — pinned download and repository provenance;
- `field-audit.json` — field presence/counts/anomalies;
- `identity-audit.json` — UUID and dual-identity validation;
- `fixture-comparison.json` — required edge-case and Atomic collision fixtures;
- `schema.md` — proposed universal inventory, relations, and projections;
- `open-questions.md` — unresolved architecture decisions;
- `prototype/` — deterministic bounded generator/validator;
- `fixtures/` — compact machine-readable evidence only;
- `manifest.json` — artifact hashes, commands, rerun result, status, and temp
  payload cleanup status.

Status is `complete`, `incomplete`, or `blocked`. End with:

`READY_FOR_MTGJSON_ARCHITECTURE_REVIEW`

## Return path

The user returns to the Factory NG architecture chat and asks it to review
`/opt/development/magic-ops/docs/sessions/mtgjson-allprintings/`.
