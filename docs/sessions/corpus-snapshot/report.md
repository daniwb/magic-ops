# CorpusSnapshot v1 prototype report

Status: complete read-only experiment; architecture decisions remain open. Measured 2026-08-27 against MTGJSON AtomicCards `5.3.0+20260809` (metadata date `2026-08-09`), raw SHA-256 `6a0235edf58fdd6947a84a4d5f8f27aeea899b179e46a14fd6356df368afbcfd`.

No recognized, expressible, or playable coverage was calculated. Full counts, breakdowns, examples, and manifests are machine-authoritative in `policy-comparison.json`, `identity-audit.json`, and `manifests/`.

## Population evidence

| Candidate | Included faces | Included parents | Excluded faces | Intended tradeoff |
|---|---:|---:|---:|---|
| `classifier-compatible-v1` | 34,049 | 33,219 | 1,909 | Exact compatibility with `scripts/paragraph/classify.py`; excludes Battles and several product/layout families even when otherwise usable. |
| `schema-non-funny-v1` | 34,576 | 33,707 | 1,382 | Broadest non-funny AtomicCards surface; adds 527 faces over classifier compatibility, including planar/scheme/vanguard/Battle/product objects. |
| `paper-product-v1` | 33,678 | 32,822 | 2,280 | Requires at least one `Legal`, `Restricted`, or `Banned` format status and excludes funny cards; smaller, but legality metadata is an imperfect paper/product proxy. |

Classifier exclusions are overlapping reason codes: `funny` 1,382; layouts planar 207, reversible_card 73, scheme 102, vanguard 107; types Battle 39, Conspiracy 29, Hero 21, Phenomenon 21, Plane 184, Scheme 102, Stickers 49, Vanguard 107. The broad candidate excludes only `funny`. The paper/product candidate records `funny` 1,382 and `no_paper_format_status` 2,232; overlap explains why reason counts exceed excluded faces.

The broad candidate includes 898 faces with no legal format and 47 with only banned/restricted status; the paper candidate retains 33,631 with some legal status, 34 banned/not-legal, and 13 restricted-only. Battles are visible rather than silently decided: classifier includes 0, broad includes 36 non-funny, paper includes 36.

Layout and type histograms, legality classes, three bounded examples per dimension value, exclusion examples, and parent rollups are in `policy-comparison.json`. Complete members remain in JSONL, not Markdown.

## Digital and rebalanced limitation

AtomicCards contains no `isDigital`, `isOnlineOnly`, `isRebalanced`, availability, or equivalent face field. Every candidate therefore reports both dimensions as `unknown_not_exposed`, never false. `printings` is retained as evidence but was not converted into an unpinned set-code heuristic. Consequently, this pinned file alone cannot meet a definitive paper-versus-digital/rebalanced partition. The paper candidate is explicitly a legality-status proxy, not a resolved digital policy.

## Identity audit

The proposed `scryfallOracleId + side` key has no missing Oracle IDs among 35,958 raw faces and distinguishes all faces in 902 multi-face parent groups, but it is not globally unique:

- 6 duplicate source keys exist (three Oracle objects, both `a` and `b`), involving duplicated parent forms for Marang River Regent, Scavenger Regent, and Bloomvine Regent.
- 70 Oracle IDs occur in more than one content-derived parent group. Many are a normal single-face object plus a reversible-card side; examples include Etali, Command Tower, Steam Vents, and Ulamog.
- Some duplicate side keys have different text hashes, so blind deduplication would lose source evidence.

This falsifies `oracleId + side` as a standalone v1 source-row identity for this AtomicCards snapshot. It remains a useful semantic Oracle-object locator. A row identity needs either an upstream stable parent/product occurrence identifier from a richer pinned source or a deterministic occurrence discriminator that does not use name or array position.

Fallback-v1 is defined for missing Oracle IDs from a content-derived parent key plus side, layout, mana cost, text, and types. It is deterministic but content-sensitive, so it is only a local locator and must not masquerade as durable cross-snapshot identity. Renames are stable when Oracle ID persists; Oracle text revisions retain the Oracle key and are exposed by `source_text_sha256`; Oracle splits/merges, side changes, and parent regrouping require explicit alias/supersession migration evidence.

## Determinism

The generator was run twice with identical corpus, policy code, repository state, and arguments. `diff -qr` over `manifests/` and `cmp` over both audit JSON files returned no difference. All canonical JSON uses sorted keys and compact UTF-8; JSONL members sort by source ID with deterministic tie fields.

## Recommendation for architecture review

Do not choose one population by preference yet. Adopt the descriptor/member schema and reason-code conservation pattern, but keep all three policy manifests as measured alternatives. Before accepting a population, pin a richer upstream input that exposes digital/rebalanced and stable printing/parent occurrence identity. Do not ship `oracleId + side` alone as source-unit identity; treat the 6 collisions and 70 cross-parent cases as acceptance-test fixtures for the revised identity.

The broad non-funny policy is the best diagnostic superset, classifier-compatible is the exact legacy comparison baseline, and paper-product is only a provisional legality proxy. A final production policy can be a named projection from the diagnostic superset once architecture resolves product-object layouts, Battles, digital/rebalanced authority, and parent semantics.

## Exact measurement commands

See `manifest.json.commands`; commands are stored as argument arrays. Production repositories/services/databases/tickets/workers/branches were not mutated. Only this output directory and temporary rerun/patch directories were written.
