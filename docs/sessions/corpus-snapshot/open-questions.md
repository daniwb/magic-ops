# CorpusSnapshot architecture questions

1. Which richer pinned MTGJSON/Scryfall artifact is authoritative for digital-only, rebalanced, availability, set/product, and stable printing occurrence metadata?
2. Is the canonical source row an Oracle semantic face, a product/printing face, or both linked units? The six `oracleId + side` collisions show one unit cannot silently stand in for both.
3. What stable occurrence discriminator replaces AtomicCards name keys and array position for duplicate parent forms?
4. Should reversible-card copies of ordinary Oracle objects be separate source rows, aliases, or product projections? Seventy Oracle IDs cross parent groups.
5. Are Battles, planar cards, schemes, vanguards, conspiracies, dungeons, attractions, contraptions, stickers, heroes, and funny cards in the diagnostic population, production population, or named projections?
6. Is a paper/product policy based on format legality acceptable, or must it be based on pinned set/product availability metadata? What authority handles banned/restricted but real paper cards?
7. Are excluded funny faces still retained in a universal source inventory with policy decisions layered on top, or absent from the base snapshot?
8. What is the canonical parent-card definition and rollup behavior for split, aftermath, adventure, transform, modal DFC, meld, reversible, and multi-side (`c`) objects?
9. Who authorizes cross-snapshot alias/split/merge migrations when upstream Oracle objects or sides change?
10. Is dirty repository state permitted for snapshot generation if every dirty path is recorded, or must an accepted snapshot run from clean pinned worktrees?
11. Should collision findings block snapshot creation, block only identity adoption, or cause deterministic disambiguation with a typed reason?
12. Must policy manifests include excluded rows as full machine manifests as well as included members? This prototype preserves exact exclusion counts/examples but writes complete included member manifests only.
