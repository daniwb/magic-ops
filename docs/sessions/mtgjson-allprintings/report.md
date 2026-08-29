# MTGJSON AllPrintings validation report

Date: 2026-08-27  
Status: complete  
Pinned release: MTGJSON `5.3.0+20260827` (`2026-08-27`)

## Recommendation

Accept pinned MTGJSON `AllPrintings` as Factory NG's single occurrence and
product authority. Use `source_occurrence_id = mtgjson:<uuid>`. Maintain a
separate semantic grouping `oracle_face_id =
oracle:<scryfallOracleId>:<side-or-none>`, but never treat it as unique among
printings. Preserve `otherFaceIds`, original/rebalanced links, and projection
membership as relations over the universal occurrence inventory.

The proposed model is therefore accepted with one clarification: “semantic
face” is the explicit MTGJSON `side` (`a` through `e`) when present and the
literal `none` when absent. It is not inferred from a name, delimiter, or array
position. `scryfallOracleId + semantic-face` groups occurrences; UUID identifies
them.

## Measured corpus

The official compressed AllPrintings payload contains 869 sets and 122,669
occurrences: 113,597 rows in set `cards` collections and 9,072 rows in set
`tokens` collections. Every occurrence has a distinct non-null `uuid` and a
non-null `scryfallOracleId`. There are 38,626 distinct Oracle IDs. The largest
Oracle group has 950 occurrences, and 3,280 Oracle IDs occur with more than one
explicit side.

The source has 10,494 directed `otherFaceIds` edges. All targets exist, every
edge is reciprocal, no edge is a self-edge, and an occurrence has at most four
targets. Explicit sides include `a` (5,241), `b` (5,217), `c` (5), `d` (2),
and `e` (2); 112,202 occurrences have no side. This falsifies any assumption
that multi-side data is limited to two faces.

UUID uniqueness is measured only within this pinned release. MTGJSON documents
UUID as its card identifier, but this session did not compare multiple
AllPrintings releases; durable cross-snapshot stability remains an explicit
open question.

## Product and population findings

`availability` is present on every occurrence. Membership counts are 113,072
paper, 69,549 MTGO, 22,096 Arena, 10 Dreamcast, and 12 Shandalar; memberships
overlap. `isOnlineOnly` is explicitly true on 9,597 occurrences and omitted on
the other 113,072. Set-level `isOnlineOnly` is present on all 869 sets (61 true,
808 false).

The initial named projections are:

| Projection | Rule | Occurrences |
|---|---|---:|
| `universal-occurrences-v1` | every `cards` and `tokens` row | 122,669 |
| `paper-occurrences-v1` | `paper` is in `availability` | 113,072 |
| `digital-occurrences-v1` | any of Arena, MTGO, Dreamcast, or Shandalar is in `availability` | 74,527 |
| `nonpaper-occurrences-v1` | `paper` is absent from `availability` | 9,597 |

These are overlapping evidence-preserving views, not deletion policies.
`paper` versus `nonpaper` conserves the universal inventory exactly. The
digital view intentionally overlaps paper because many products exist in both.

Occurrence provenance needs UUID plus set code, collector number, language,
availability, finish, and relevant upstream identifiers, joined to set name,
type, release date, parent code, and online-only flags. `(setCode, number,
language)` is not an identity: 7,854 such keys have multiple rows, commonly
because faces, finishes, promos, or other variants coexist.

## Rebalanced relations

There are 235 rows with `isRebalanced=true`, 234 rows exposing
`originalPrintings`, and 362 rows exposing `rebalancedPrintings`. Their lists
form 394 edges in each direction. Every target UUID exists and all 394
rebalanced-to-original edges have the reverse original-to-rebalanced edge.
The schema therefore models these fields as occurrence relations and does not
derive them from card names such as the `A-` prefix.

## Edge-case behavior

Compact fixtures preserve examples for tokens, funny cards, Battles,
reversible cards, split, adventure, transform, modal DFC, meld, double-faced
tokens, and unusual multi-side objects. Measured occurrence counts include:

- 9,072 rows sourced from token collections (3,079 also classified by token
  type/layout), 10,848 funny/memorabilia rows, and 56 Battles;
- 162 reversible-card, 515 split, 918 adventure, 2,130 transform, 656 modal
  DFC, 72 meld, and 240 double-faced-token rows;
- 43 unusual multi-side rows, including relationships with up to four other
  faces and explicit sides through `e`.

Tokens demonstrate why collection provenance must be retained: not every row
from a set's `tokens` collection has layout/type markers that a downstream
classifier would call “token.” Funny status likewise requires preserving both
card and set evidence rather than deleting rows.

## AtomicCards compatibility findings

AtomicCards was downloaded from the same official release, so the comparison
is global-release compatible. The previous six duplicate `oracleId + side`
identities correspond to three Oracle IDs. Each maps to eight distinct
AllPrintings UUID occurrences across `TDM` and `PTDM`, with four `a` and four
`b` occurrences. UUID resolves the collision without deduplication.

All 70 previous cross-parent Oracle-ID cases exist in AllPrintings. Sixty-seven
have two AtomicCards rows and three have four. AllPrintings represents them as
printing occurrences linked by UUID and semantic Oracle/side grouping, so the
Atomic parent grouping is compatibility structure, not identity authority.

## Determinism and limits

The prototype reads official XZ payloads directly and emits only compact,
key-sorted, newline-terminated JSON. A second complete generation produced
byte-identical generated outputs, and the validator passed both conservation
and identity checks. No full generated inventory or upstream payload is stored
in the repository.

This validation does not calculate recognized, expressible, playable, or
coverage metrics. It does not prove UUID continuity across releases, decide
long-term handling of upstream deletions, or choose whether token collections
belong in the first production projection.

