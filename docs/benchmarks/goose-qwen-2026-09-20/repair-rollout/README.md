# Qwen staged repair/evidence production rollout — 2026-09-20

User authorized testing and enabling the previously identified fixes. Production worker remains qwen-goose-staged@1.0.0 with Goose, strix_halo, halogen-qwen3.8-flash-next, thinking enabled and 32,000 completion tokens.

## Enabled changes

- One NEED source continuation no longer consumes the correction allowance. Maximum: one initial call, one continuation, one protocol OR compile/test correction (three total). No fourth model call.
- The harness supplies eight bounded database/API lookups and verifies declarations against the ticket checkout. Zone, Player, Target, Primitive, regEffect, RemoveCard, AddCard and NewCard are covered. Missing index rows fall back to structural parsing in five known source files. A database outage suppresses further HTTP queries and uses that fallback.
- API evidence is limited per phase to eight queries, 480 source lines and 32 KB of rendered source. Model tool authority remains empty. Source resolution traces are retained; repair evidence is refreshed from the current candidate.
- Source returned by NEED is retained for the subsequent correction, instead of reverting to the original packet.
- Parser failures receive the existing strict diagnostic/exact-source correction prompt. No fuzzy application or gate weakening.
- A scoped-file inventory (at most 40 paths / 12 KB) marks existing files versus absent/unreadable paths and identifies missing required named test declarations. This last refinement was added after the compile replay exposed a missing-test failure hidden by the initial compiler error.

Profile metadata and worker description updated under dispatcher-admin. New processes read changes automatically; no controller restart or active worker termination. live-packet-proof.txt confirms a real new production packet already included the API supplement. The existing runner can finish older in-flight attempts under its prior loaded policy.

## Deterministic validation

Retained regression logs cover repair after NEED, parser diagnostics, exactly one correction, no fourth call, current source vs stale index data, traversal rejection, source limits, database outage fallback, scoped-file/test inventory and production routing. The old control assertion expecting the retired pre-Goose profile was updated to verify Goose plus a drain-only legacy route. Enabled profiles validate and changed files pass diff whitespace checks. The canonical checkout remained clean.

Suites run include test_goose_staged, test_factory_ng_qwen_evidence, test_factory_ng_staged, test_factory_ng_verification, test_factory_ng_patch_repair, test_factory_ng_packet_delivery, test_factory_ng_profiles and test_factory_ng_control. Logs cover overlapping suites, so their test counts should not be added as unique tests.

## Real frozen-ticket replays

The real runner cloned each original ticket revision and retained every original gate. The initial NEED reply and the following failed patch were replayed verbatim from historical artifacts; exactly one new real Goose correction was requested. This tests correction of known failures, not a new full three-call generation benchmark. Receipts/candidates live under this benchmark directory, outside Factory intake; no benchmark patch was integrated.

| Case | New real call | Outcome |
| --- | --- | --- |
| Attacker owner-choice library placement v2: compiler/type errors | 19,976 input / 15,554 output tokens; replay wall time 896.955 s | Correction applied; former type errors cleared. Required named test absent, so original gate rejected candidate. |
| Referent object to library top v1: malformed registry FILE block | 1,202.581 s replay wall time; completion usage unavailable | Provider call hit its 1,200-second timeout. Partial output rejected; no accepted candidate. |

The compile candidate was reconstructed from the frozen source plus both actual patches to verify the new test-declaration preflight; it correctly identifies the missing selector (compile/test-declaration-preflight.txt). That inventory refinement passed regression tests but has not been re-evaluated with another long model replay. Both original replays predate it. No recovered-ticket claim is made.

The real cases confirm that the new correction path executes after NEED and can remove the original compile failure. They do NOT establish an improved integrated success rate: neither case passed all gates. The timeout also shows that raising the token ceiling does not guarantee a complete answer within the existing wall-clock budget, especially on shared inference hardware. The timeout was not silently increased and failed candidates were not admitted.

results.json retains original receipt pointers, new-call usage, exact gate outcomes and elapsed time. replay.py and summarize.py reproduce and inspect the test. activation.json and live-packet-proof.txt document production activation. Full trace/prompt/response artifacts are retained under compile/ and protocol/.

## Subsequent production evidence — checked 17:14 UTC

Two live tickets subsequently used NEED plus one gate correction (three model calls), then passed the complete six-shard suite and were pushed: controlled-permanent modified-copy behavior (`174d10e200`) and return up to one graveyard card per color to hand (`f8b782a10e`). Commits: `774c9a86b88f19a1fc491553db2f514e1e371708` and `e86bd86304eee1864b03db7bc44e26b63e95dab6`. Neither was deployed. Full receipt references and token/time telemetry are in production-recoveries.json. These are direct evidence that the new correction path can produce integrated work; two cases do not establish a stable success rate.
