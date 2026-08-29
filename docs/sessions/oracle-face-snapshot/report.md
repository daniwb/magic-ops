# Oracle-face snapshot derivation report

Pinned source: official MTGJSON `AllPrintings` `5.3.0+20260827`, dated
2026-08-27. The downloaded 96,749,620-byte XZ payload reproduced the previously
accepted SHA-256 exactly, so these measurements are a legitimate same-release
continuation.

## Recommendation

Accept the structured Oracle-face population and projection mechanics with
quarantine retained. Do not publish the six conflicted groups as canonical
semantic revisions until their upstream/layout cases are reviewed, and do not
make the proposed normal-game candidate authoritative. Treat the 142 groups
whose printing occurrences expose different face-relation target sets as a
separate relation-evidence quarantine question; the prototype preserves the
union and every distinct observed target set.

## Findings

- All 122,669 occurrences have valid UUID/Oracle identity and map exactly once
  into 41,979 structured semantic face groups.
- 41,973 groups have one agreed semantic revision; six are quarantined.
- Conflicts are typed: layout (6 groups), text (3), power (3), and toughness
  (3). A group can carry more than one reason. Bounded evidence is in
  `group-audit.json`; complete memberships remain in the compressed snapshot.
- Reprint multiplicity is removed from work counts. The largest group has 948
  occurrences but exactly one semantic member.
- Paper contains 40,882 faces and nonpaper 1,097, totaling universal 41,979.
  The overlapping digital union contains 32,887. Arena has 16,926, MTGO
  31,826, Dreamcast 10, and Shandalar 12.
- Token provenance yields 5,957 token-template faces. The candidate normal-game
  policy includes 33,124 and excludes 8,855 with reasons on every record.
- Derived semantic relations contain 6,588 distinct other-face edges and 510
  distinct original/rebalanced edges. No occurrence relation target dangles.
  Structured sides include three `c`, one `d`, and one `e` groups.
- Funny/memorabilia is retained as a dimension and candidate exclusion reason,
  never used to delete universal membership.

The complete 41,979-record membership/reason manifest is an XZ-compressed,
content-addressed JSONL artifact outside normal Git history. Compact fixtures
cover conflicts, the maximum reprint group, sides through `e`, rebalanced,
tokens, funny/memorabilia, Battle, and split/adventure/DFC/meld layouts.

No recognized, expressible, playable, parser, or ticket metric was computed.
No production code, corpus, dispatcher, worker, service, ticket, or canonical
NG document was changed.
