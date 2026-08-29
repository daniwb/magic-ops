# Open questions for Factory NG architecture review

Nothing in this file should be silently resolved by implementation.

## Decisions required

1. **Population policy.** Should the authoritative Magic population include
   every non-funny AtomicCards face, only paper-legal faces, or a product
   capability subset? The existing tools disagree: `classify.py` excludes
   selected layouts/types (including Battle) but not legality; the planner adds
   legality and normal-layout restrictions only for not-yet-imported faces.
2. **Digital/rebalanced cards.** Are `A-`/Alchemy cards in scope, separately
   reported, or excluded? This materially changes counts and grammar.
3. **Multi-face aggregation.** Primary metrics here use faces. Should the UI
   also publish parent-card playability where all in-scope faces must pass?
4. **Oracle identity fallback.** Confirm Scryfall Oracle ID plus side as the
   preferred identity and the content-derived fallback rule. Decide how to
   handle upstream Oracle-ID corrections across snapshots.
5. **Reminder text.** Which reminder spans are non-semantic for recognition?
   Some reminder text states parameter semantics the engine must implement.
   A versioned allow policy is needed; blanket parenthesis dropping is unsafe.
6. **Raw nodes and recognition.** The proposal says a bounded raw node is not
   recognized unless its role is known. Confirm whether L1 spine recognition
   should count separately rather than weaken the primary metric.
7. **Handler accounting.** The proposal excludes handler-only cards from
   representation `expressible`. Decide whether to define a separate
   `implemented/playable_via_handler` metric and what complete per-assertion
   test receipts it requires.
8. **Test sufficiency.** Approve the minimum discriminating-test standard and
   when automated revert/mutation checks are practical. Existing shape and
   per-card tests are not indexed to assertion contracts today.
9. **Executor reachability authority.** Static call/dispatch analysis will have
   false positives and negatives in a dynamic Go engine. Decide which runtime
   instrumentation or trace fixture is required to promote candidate
   reachability to proof.
10. **Cross-card/global rules.** Some behaviors (cleanup hand size, layers,
    replacement ordering) cannot be proved per face in isolation. Define how
    global engine-contract receipts attach to all dependent assertions.
11. **Atomic Engine behavior boundary.** Approve the rule for splitting one
    behavior contract from a required refactor or jointly necessary mechanism.
    Same grammar label is not sufficient.
12. **Root-cause adjudication.** Decide which deterministic predicates are
    authoritative and when model-assisted clusters require human approval
    before ticket compilation.
13. **Bundle priority.** Choose whether first production ranking uses raw
    marginal face count only, risk/cost-adjusted benefit, format weighting, or
    multiple visible rankings. No empirical cost model exists yet.
14. **Closure treatment of unsupported.** Does explicit unsupported count as
    root-scope completion (as proposed) while remaining outside playable
    coverage? Define who may authorize that terminal state.
15. **Independent fixes.** Set the rule for attributing a member fixed between
    baseline and candidate. It should not inflate a ticket's confirmed delta.
16. **Snapshot drift during work.** Decide whether tickets always close against
    their original snapshot plus a fresh-head comparison, and how changed or
    removed source units are partitioned.
17. **Global regression population.** Full corpus remeasurement is preferred,
    but runtime behavioral testing may be sampled. Approve the minimum global
    gates for Map versus Engine tickets.
18. **Legacy status migration.** Decide whether to rename
    `backend/tools/report`'s `playable` immediately to `legacy_served`, or only
    ensure Factory NG never imports it under the new name.
19. **Content hashes and dirty state.** The research session observed unrelated
    working-tree changes. Ticket compilation should pin content hashes in
    addition to Git SHA; approve whether dirty source inputs make compilation
    invalid or merely create a content-addressed development snapshot.
20. **Artifact authority/storage.** Choose canonical JSON/JSONL schemas and
    storage (Git, object store, dispatcher DB references). Human Markdown must
    remain a projection, not the only member ledger.

## Measurements still required

- Recompute population counts under each proposed inclusion policy, including
  paper legality, digital variants, layouts, and parent-card aggregation.
- Measure collision/missing rates for `scryfallOracleId + side` and test
  cross-snapshot stability. The current file has identifiers, but the session's
  first UUID probe used a nonexistent top-level `uuid`, demonstrating why the
  schema must be explicit.
- Build span-conservation output and measure true unaccounted/overlapping text;
  current swallow audit is heuristic and says it under-reports.
- Adjudicate the current 67 swallow findings and measure precision/recall using
  labeled negatives.
- Validate every current `primitive_inventory` inert candidate via runtime
  paths; its static flags are explicitly candidates.
- Index existing tests to behavior contracts and measure how many executable
  assertions have qualifying real-path, revert-sensitive coverage.
- Compute the first truthful recognized/expressible/playable numerators. No
  current repository count satisfies these definitions.
- Recompute exact gap sets using a single population and analyzer version; the
  current 21,175 planner pool mixes sources and approximates catch-all buckets.
- Compare greedy single-gap ordering with minimal bundle ordering and quantify
  how often the current deadlock frequency fallback has zero immediate unlock.
- Measure root-cause cluster stability across adjacent corpus snapshots.
- Estimate Map/Engine ticket cost and completion probability by root-cause and
  bundle size before adopting cost-adjusted priority.
- Audit handler tests for complete Oracle-assertion coverage, not just file
  presence.
- Determine the real false-positive/negative rate of static executor
  reachability and select the necessary runtime trace instrumentation.

## Known disagreements preserved

- Historical `docs/STATUS.md` and `backend/tools/report` use parser/handler tier
  as playability; the proposed contract rejects that meaning based on later
  inert/swallow evidence.
- `paragraph-schema-v2.md` permits graded conformance and raw fields, while the
  proposed primary `recognized`/`expressible` metrics are strict. Graded L0-L3
  remains valuable as a separate diagnostic series.
- Historical phase.rs analysis suggested not copying provenance receipts for a
  solo operator, while Factory NG now requires content-addressed scope and
  result receipts. Architecture review must decide the acceptable operational
  cost; this report recommends receipts because scope loss is a stated NG
  failure mode.
- Existing planner groups some catch-alls by leading token and calls them build
  items. This report treats them as discovery buckets until behavior-homogeneous
  predicates exist.
