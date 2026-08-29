# Factory NG corpus-contract architecture review

Reviewed: 2026-08-27  
Reviewer context: Factory NG architecture session  
Source artifacts: preserved unchanged; all five artifact hashes match
`manifest.json`

## Verdict

`ACCEPT_WITH_REVISIONS`

The session established a sound foundation and found the central legacy error:
no existing metric proves playability. The contract's conservation rules,
content-addressed evidence, exact gap sets, and before/after member partitions
are accepted into Factory NG. Numerical coverage remains unknown until the
contract tooling exists.

## Accepted

1. The corpus is a pinned measurement population, not a ticket queue.
2. Source face, located semantic assertion, normalized root cause, and ticket
   are distinct units.
3. `recognized`, `expressible`, and `playable` are separate, with
   `playable => expressible => recognized` for the structured Map path.
4. Parser/`auto` status, handler presence, registry membership, compilation,
   or a broad green suite alone never proves playability.
5. Population, text/meaning, execution, and scope conservation are mandatory.
6. Unknown and unsupported source meaning remains typed, located evidence.
7. Root-cause identity is structured; member lists are immutable evidence, not
   embedded in free-text ticket identity.
8. Exact gap sets, sole blockers, co-occurrence, dependency bundles, and
   marginal unlock retain complete source-member manifests.
9. Map and Engine completion requires exhaustive remeasurement of the original
   scope and an exact before/after partition.
10. Engine code without dependent Map consumption may be
    `implemented_pending_consumption`, but the capability remains open.
11. Human Markdown is a projection; content-addressed machine artifacts are
    authoritative.

## Required revisions

1. `prediction_precision` and `prediction_recall` are mislabeled in
   `metrics.md`. Use:
   - precision = `|F intersect predicted| / |predicted|`;
   - recall = `|F intersect predicted| / |F|`.
2. Split the proposed `scope_completion_ratio` into unambiguous views:
   - `scope_accounting_ratio`: every original member has exactly one state;
   - `scope_fixed_ratio`: fixed by this change or independently fixed;
   - `scope_terminal_ratio`: fixed, invalid, or explicitly unsupported with
     authorized evidence;
   - `residual_ratio`: still same cause or reclassified open work.
   This prevents "unsupported" from looking implemented while still allowing
   a root mission to be fully accounted.
3. The proposed Oracle-face identity is provisional until collision, missing-ID,
   and cross-snapshot measurements pass. Do not ship the exploratory manifest
   hash as the v1 snapshot identity.
4. Distinguish `structured_expressible/playable` from
   `handler_implemented/playable_via_handler`. A handler is an intentional
   architecture tier, not automatically a failure of the whole product metric,
   but it needs complete assertion and behavioral receipts.
5. A static reachability ledger produces candidates. Runtime trace or an
   equivalent discriminating execution receipt is required for proof where
   dynamic dispatch makes static authority incomplete.
6. The session SHA is historical evidence. At review time Magic HEAD was
   `6d85a3d649103d8f3a50fb6436ed266c77b0942a`, not the pinned
   `cccfbef6b4e3e397e4fe70d5aff44fd9c6d410dd`; the raw corpus hash remained
   identical. No session count is silently rebased to current HEAD.

## Decisions still required before implementation

Resolve in this order, using measurement rather than preference where possible:

1. population policy: paper/product scope, digital/rebalanced cards, layouts,
   Battles, and parent-card rollups;
2. source identity and cross-snapshot migration policy;
3. reminder-text semantic policy and strict recognition levels;
4. handler metric and receipt standard;
5. execution/test proof authority, including global engine contracts;
6. terminal authority for `explicitly_unsupported`;
7. dirty-source snapshot policy and artifact storage.

Ranking weights, cost-adjusted priority, and runtime sampling policy can wait
until the first truthful manifests and ticket attempts provide data.

## Next bounded slice

Build a read-only `CorpusSnapshot v1` prototype for two or three candidate
population policies. It must emit only identities, inclusion/exclusion reason
codes, parent/face relationships, text hashes, collision/missing-ID reports,
and content hashes. Do not build ticket production or claim coverage yet. The
result will settle decisions 1–2 with actual counts and examples.
