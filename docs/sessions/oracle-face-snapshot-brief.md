# Factory NG Canonical Oracle-Face Snapshot — Dedicated Session Brief

Status: ready for a separate Codex session  
Provider decision: MTGJSON only  
Output directory: `/opt/development/magic-ops/docs/sessions/oracle-face-snapshot/`

## Mission

Build and validate a read-only prototype that derives Factory NG's canonical
semantic Oracle-face snapshot from a pinned MTGJSON `AllPrintings` release.
This snapshot becomes the future population for corpus assertions, root-cause
prevalence, marginal unlock, and ticket scopes. Printing occurrences remain
linked evidence and must not multiply work counts.

Read completely before acting:

- `/opt/development/magic-ops/AGENTS.md`
- `/opt/development/magic-ops/docs/sessions/mtgjson-allprintings/architecture-review.md`
- `/opt/development/magic-ops/docs/sessions/mtgjson-allprintings/schema.md`
- `/opt/development/magic-ops/docs/sessions/corpus-contract/architecture-review.md`
- `/opt/development/magic-ops/docs/factory-ng-plan.md`

## Source and safety

Use official MTGJSON `AllPrintings` only. Pin version/date, URL, compressed
bytes, SHA-256, adapter/schema hashes, and retrieval time. Prefer the release
already measured (`5.3.0+20260827`) if its recorded payload can be reproduced;
otherwise pin the newly retrieved release and state that counts are not a
same-release continuation. Check disk before download/expansion, stream the XZ
where practical, keep large payloads outside Git, and delete temporary payloads
after a verified rerun.

## Required derivation

Start from these already accepted identities:

```text
source_occurrence_id = mtgjson:<uuid>
oracle_face_key      = (scryfallOracleId, nullable explicit MTGJSON side)
```

For every Oracle-face group:

1. retain the complete occurrence-ID membership and availability union;
2. audit current rules text, type, types/subtypes/supertypes, layout, mana cost,
   color identity, keywords, power/toughness/loyalty, and face relationships;
3. distinguish harmless printing metadata variation from semantic conflict;
4. produce one canonical semantic revision only when the accepted fields agree
   under a deterministic rule;
5. quarantine disagreement with typed reason codes and full evidence; never
   choose the first/newest/most-common row silently;
6. derive Oracle-level face relations from occurrence `otherFaceIds` and check
   relation consistency across printings;
7. preserve rebalanced/original relations between semantic groups;
8. prove that reprints contribute one semantic work member, not N members.

Do not use name, set, collector number, language, or occurrence order as
semantic identity. Serialize absent side structurally as null; any string ID is
only a canonical projection of the structured key.

## Required projections

Produce complete membership/reason manifests over semantic Oracle faces for:

- `universal-oracle-faces-v1`;
- `paper-oracle-faces-v1` — at least one linked occurrence has paper
  availability;
- `nonpaper-oracle-faces-v1` — no linked occurrence has paper availability;
- per-platform availability plus an overlapping digital union;
- `normal-game-oracle-faces-candidate-v1` with every proposed exclusion visible
  and reason-coded, not silently accepted as production policy;
- `token-templates-v1`, derived using source collection provenance and audited
  separately from ordinary printed-card coverage;
- funny/memorabilia dimensions as evidence, not deletion.

Paper/nonpaper must partition the universal semantic population exactly.
Platform/digital views may overlap paper.

## Required measurements and gates

- total occurrence rows consumed and unique semantic face groups;
- group-size distribution and maximum group size;
- counts and examples for every semantic conflict reason;
- missing/invalid Oracle IDs or sides;
- occurrence-to-face conservation: every occurrence maps exactly once;
- canonical-face uniqueness;
- face-relation target integrity and multiplicity through sides `c`–`e`;
- projection recomputation and conservation;
- deterministic canonical bytes and byte-identical second run;
- current-release UUID/content comparison only if a legitimately pinned prior
  AllPrintings payload is available; otherwise report longitudinal continuity
  as unmeasured rather than fabricating a comparison.

## Boundaries

- Do not change production code, canonical corpus files, dispatcher state,
  workers, services, tickets, or canonical NG documents.
- Do not calculate recognized, expressible, playable, or parser coverage.
- Do not build TicketSpec or generate tickets.
- Do not make the candidate normal-game projection authoritative.
- Do not add another data provider.
- Do not store full uncompressed inventories in normal Git history.

## Required artifacts

Write under the output directory:

- `report.md` — findings, conflict taxonomy, and recommendation;
- `source-manifest.json` — pinned MTGJSON and repository provenance;
- `group-audit.json` — counts, distributions, conflicts, and bounded examples;
- `relation-audit.json` — semantic face and rebalanced relations;
- `projection-audit.json` — exact projection counts and conservation;
- `schema.md` — canonical Oracle-face snapshot/member/relation/membership schema;
- `open-questions.md` — decisions requiring architecture review;
- `prototype/` — deterministic generator and validator;
- `fixtures/` — compact groups covering conflicts, high reprint count,
  multi-side, rebalanced, token, funny, Battle, split/adventure/DFC/meld;
- `manifest.json` — hashes, commands, rerun result, status, and temporary
  payload cleanup status.

Large generated inventories, if needed for validation, remain compressed and
content-addressed outside Git and are represented here by descriptors/hashes.
Session status is `complete`, `incomplete`, or `blocked`.

End with:

`READY_FOR_ORACLE_FACE_ARCHITECTURE_REVIEW`

## Return path

The user returns to the Factory NG architecture chat and asks it to review
`/opt/development/magic-ops/docs/sessions/oracle-face-snapshot/`.
