# TicketSpec v1 repair architecture review

Reviewed: 2026-08-27  
Verdict: `REVISION_REQUIRED`

The repair materially improves the first prototype and now reports an honest
`candidate` rather than sending unproven work to a model. The live parser
adapter, complete per-face gap inventories, distinct scope sets, full-source
byte spans, root mission edge, persistent history fixture, and exact-code
negative tests are useful foundations. Stages 4–7 must nevertheless remain
closed because the emitted bundle is not yet content-addressed end to end and
readiness is not derived by the declared sole evaluator.

## Independently reproduced

- `python3 compiler/compile.py` exits zero.
- `python3 compiler/validate.py` reports `OK`.
- `python3 compiler/test.py` reports 16 passing assertions while correctly
  recording a failed Engine creation gate.
- `go test ./game -run '^TestExecuteDrawEffect_TargetPlayer$' -count=1`
  fails with `cannot draw from empty library`.
- Inspiration has only `verb_unmapped:p_draw`; Comparative Analysis also has
  `keyword_unsupported`, so only Inspiration is a predicted whole-face unlock.
- The rejected prototype remains byte-identical and no model route or Map
  implementation ran.

## Accepted repair work

- current full-text parser execution, including a face absent from carddb;
- complete assertion records, UTF-8 source spans, source hashes, and gap sets;
- independent root-cause, sole-blocker, and predicted-unlock collections;
- typed root mission and `decomposes_to` ticket edge;
- real session-local Map Skill with constrained paths and refusal verdicts;
- stable full ticket identity and persistent duplicate-history fixture;
- explicit pending hybrid route, local/online token dimensions, and
  non-destructive 200k/500k budget semantics;
- honest lifecycle refusal while a creation-time behavior gate is red.

## Blocking findings

1. **Cross-artifact hashes are not enforced.** The validator accepts a ticket
   whose `scope_hash` was replaced by 64 zeroes. It likewise does not recompute
   and compare `graph_hash` or `evidence_pack_hash`. Content addressing is
   therefore descriptive rather than authoritative.
2. **The declared sole readiness evaluator is not the authority.**
   `compile.py` constructs predicate truth values and assigns
   `final_lifecycle` directly. `validate.py:evaluate_readiness` exists but is
   not called by compilation or validation. Most predicates are initialized
   `true` rather than derived from their corresponding checks.
3. **The Engine receipt is not proven.** Its only behavior command fails
   because the test creates empty libraries. This appears to be a test-fixture
   defect, not evidence that target-player drawing is absent, but a failing
   behavior test cannot support an Engine-proven readiness predicate.
4. **Schemas remain shallow at normative boundaries.** Ticket readiness,
   Skill receipt, work profile, attempt policy, gates, projection, graph
   nodes/edges, evidence analyses/receipts, routing, telemetry, Engine receipt,
   result partitions, and predicate records are still generic `object` or
   `array` values. The embedded objects are separately validated in some
   cases, but the TicketSpec schemas themselves do not express the promised
   strong nested contract.
5. **Creation-gate truth is authored, not executed and bound.** The compiler
   writes results such as `passed`/`failed`; it does not run every command and
   derive the gate record with exit code, timestamp, output digest, and command
   digest. The test harness runs only part of the declared creation surface.
6. **Receipt semantics are incomplete.** File hashes are checked, but the
   Engine receipt contains untyped prose and symbol names without mechanical
   symbol/reachability verification. Repository receipts and projection
   descriptor/membership hashes are not fully cross-checked against the
   artifacts they claim to bind.
7. **The session manifest is stale after an ordinary rerun.** The documented
   rerun commands rewrite outputs and `test-results.json`, but do not rebuild
   `manifest.json`; its artifact hashes can therefore cease to describe the
   current bundle.

## Required focused correction

1. Make `validate.py` recompute and enforce every ticket artifact hash and add
   named negative tests for each mismatch.
2. Move predicate derivation into one readiness evaluator that consumes actual
   validation/gate results; prohibit all other lifecycle assignment paths.
3. Repair or replace the Engine test fixture so the target player can draw two
   cards, then require the behavior assertion to distinguish target from
   controller.
4. Replace generic normative objects/arrays with referenced, closed schemas
   for all nested TicketSpec structures.
5. Execute creation gates through one runner and persist command, exit,
   timestamps, stdout/stderr digest, repository state, and result. Readiness
   must consume those records rather than compiler literals.
6. Mechanically verify Engine symbols/reachability and all projection,
   repository, policy, Skill, and evidence receipts.
7. Make finalization part of the normal deterministic run and validate the
   manifest against all final bytes without self-invalidating reruns.

## Readiness verdict

Do not run model stages 4–7. Preserve this repair as the second prototype: it
proved that the factory can refuse a candidate honestly and it established the
correct two-member scope. TicketSpec v1 is accepted conceptually but not yet
accepted as an executable contract. The next action is one narrow deterministic
correction pass, followed by adversarial review; only then may the golden Map
debug run begin.
