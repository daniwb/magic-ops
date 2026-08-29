# TicketSpec v1 prototype architecture review

Reviewed: 2026-08-27  
Verdict: `REVISION_REQUIRED`

All declared files and hashes exist, the compiler is byte-idempotent, and its
own 11 tests report green. The selected grammar family is promising and a
direct repository check confirms a current `verb_unmapped:p_draw` miss for
Inspiration plus an existing target-player draw executor/test. Nevertheless,
the emitted ticket is not evidence-complete and must not remain `ready`.

## Useful work accepted

- separate factory envelope and Magic scope/result schema families;
- explicit `map` work type, prohibited Engine paths, non-destructive budget
  policy, and seven-stage pending workflow;
- deterministic ticket/scope artifact generation;
- two exact positive Oracle-face members and adjacent negative examples;
- printing occurrences do not affect scope size;
- quarantine and relation-not-required fields are present;
- immutable scope and pending exhaustive result partition are represented.

These are prototype inputs to the repaired TicketSpec, not accepted v1
schemas or a production-ready ticket.

## Blocking findings

1. **Baseline is asserted, not reproduced.** The compiler scans Oracle text
   with its own exact-line regex and hard-codes `mapped: 0`. It never runs the
   current paragraph parser/analyzer for either positive member.
2. **Complete gap sets are not computed.** The ticket labels the draw gap as
   each face's complete gap set without analyzing every clause. Comparative
   Analysis contains a Surge clause, so predicted whole-face unlock cannot be
   assumed.
3. **Engine evidence is not a receipt.** `backend/cardfns draw action` is free
   text. The actual repository contains `executeDrawEffect`, target-player
   wiring, `TestExecuteDrawEffect_TargetPlayer`, and registry/converter paths;
   the ticket must pin exact files/symbols/content hashes and a runnable test.
4. **Gates are placeholders.** Every command is
   `defined_by_later_checkpoint`; a `ready` ticket must carry executable
   discriminating, honesty, regression, and remeasurement commands.
5. **Projection hash is not the projection hash.** It hashes an ID and admitted
   count, not the complete membership/policy artifact. Count equality cannot
   detect member substitution.
6. **Skill hash is synthetic.** It hashes a proposed label/description rather
   than an existing, versioned Skill contract.
7. **Repository evidence is weak.** `repository_hash` is a hash of a commit
   string and does not bind relevant dirty content or exact inspected files.
8. **Assertion spans are not source spans.** The second-line member uses
   `start: 0`; locators are line-relative while the contract requires a defined
   byte span in the full semantic source revision.
9. **Schemas are structurally shallow.** Required nested objects are mostly
   untyped `object`/`array` values with no `$ref`; key readiness fields and
   member constraints are optional or unenforced.
10. **Schema validation is incomplete.** Only ticket and scope are validated.
    The fallback checks only that schema IDs exist.
11. **Tests overstate assurance.** Hash validation checks only the ticket-ID
    prefix; the mixed-behavior fixture merely removes a locator; cycle fixtures
    do not validate edge schemas; duplicate checking is an in-memory set rather
    than an immutable open/history identity ledger.
12. **Root graph semantics are incomplete.** The mission identifier is not a
    typed graph node/edge, so the promised visualizable main-ticket structure
    is not yet represented.

## Required repair

The next compiler revision must:

1. introduce a deterministic analyzer adapter that runs the current parser on
   full Oracle text, including faces not currently imported into carddb;
2. emit every clause/assertion result and the complete gap set per member;
3. calculate root-cause scope separately from true sole-blocker/predicted
   whole-face unlock;
4. produce content-addressed Engine capability receipts and executable gates;
5. use actual projection, Skill, repository/file, analyzer, and policy
   artifacts/hashes;
6. define full-source byte offsets and source-text hashes;
7. strengthen all schemas with `$defs`/`$ref`, required fields, enums, formats,
   and cross-artifact contract validation;
8. validate every output and make each negative fixture fail for its named
   reason;
9. model a root/main mission node and its ticket edge explicitly;
10. emit lifecycle `candidate` until every readiness receipt passes.

## Readiness verdict

Do not run model stages 4–5 on this ticket. The selected family may remain the
golden Map candidate after deterministic repair. TicketSpec v1 is not yet
accepted; the corpus foundation remains accepted and unchanged.
