# Canonical Oracle-face snapshot architecture review

Reviewed: 2026-08-27  
Verdict: `ACCEPT_WITH_REVISIONS`

All declared hashes match, the external compressed inventory exists with the
declared hash, and the supplied validator passes. The same pinned AllPrintings
payload used by the preceding experiment was reproduced byte-for-byte; two
generation runs produced identical outputs.

## Accepted measurements

- 122,669 occurrences map exactly once into 41,979 structured Oracle-face
  groups.
- 41,973 groups have one agreed semantic revision; six are quarantined.
- The largest group has 948 occurrences but contributes one semantic work
  member.
- Paper: 40,882 faces; nonpaper: 1,097; exact universal total: 41,979.
- Digital union: 32,887; Arena: 16,926; MTGO: 31,826; Dreamcast: 10;
  Shandalar: 12. These availability projections may overlap paper.
- Token-collection provenance reaches 5,957 semantic groups.
- All occurrence relations resolve. Derived evidence contains 6,588 distinct
  other-face edges and 510 original/rebalanced edges.
- Six semantic groups conflict: layout on six, with text/power/toughness also
  conflicting on three. No arbitrary occurrence was selected.
- 142 semantic source groups expose different other-face target sets across
  their printing occurrences.

## Architecture decisions accepted

1. The canonical work population is the structured Oracle-face snapshot, not
   AllPrintings occurrences or AtomicCards name rows.
2. Reprints carry product evidence but never multiply coverage, prevalence,
   marginal unlock, or ticket scope.
3. Keep all 41,979 groups in the universal semantic inventory. Quarantine is a
   status, not deletion.
4. Define `source-admitted-oracle-faces-v1` as the initial source-ready
   projection: semantic revision is canonical and required identity/conservation
   gates pass. It contains 41,973 faces in this pinned snapshot.
5. The six semantic-conflict groups remain visible and ineligible for ordinary
   Map/Engine ticket production until resolved or explicitly exceptioned.
6. Paper/nonpaper and per-platform availability rules are accepted as evidence
   projections. The proposed normal-game projection remains non-authoritative.
7. Token provenance is a separate projection. Sharing an Oracle semantic key
   with card-collection evidence does not create a second work identity; the
   provenance dimensions remain attached to the same semantic face.
8. Large canonical inventory storage remains compressed/content-addressed;
   descriptors, hashes, schemas, generators, and fixtures belong in Git.

## Required relation revision

`otherFaceIds` is occurrence/product-configuration evidence. The 142 differing
target sets prove that the union across printings is not automatically an
intrinsic semantic Oracle-face relation. Preserve every occurrence edge and
derive semantic relations only under a versioned rule that distinguishes, at
minimum:

- intrinsic multi-face game objects such as transform, modal DFC, meld, split,
  adventure, and other rules-relevant compositions;
- product pairings such as reversible-card print configurations;
- missing/partial relation evidence.

Until that rule exists, the deterministic union is an evidence view, not
canonical semantic truth. Tickets whose premise depends on parent/other-face
composition require a relation-ready receipt; unrelated single-face tickets do
not need to wait.

## Readiness verdict

The corpus foundation is ready for **TicketSpec v1 design and a read-only
ticket compiler prototype** using only source-admitted groups and explicit
projection hashes. It is not yet ready for unsupervised production ticket
generation.

TicketSpec must carry:

- source snapshot, Oracle-face inventory, projection, adapter, and policy
  hashes;
- structured Oracle-face key and semantic revision hash for every member;
- quarantine/relation-readiness status;
- immutable original member manifest and complete result partitions;
- no occurrence-weighted priority or closure metric.

Before production rollout, resolve the relation derivation policy, choose the
artifact retention mechanism, and measure cross-release UUID/content movement.
These no longer block TicketSpec schema work.
