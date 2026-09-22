# Qwen improvement priorities — evidence from September 20 cohort

Analysis only; no worker settings or repair policy changed.

## Observed failures

Of the 18 failed ticket versions in the retained 27-version cohort:

- 5 were rejected at the 16,000 completion-token ceiling. All five are labelled infrastructure_failed, but their receipt explicitly says completion budget exhausted. Retained raw complete events report 16,000 output tokens. Several answers end mid-code; one ends in explanation after edit blocks, so hitting the cap does not by itself prove every patch was incomplete.
- 7 failed output/patch handling: invalid or missing delimiters, NEWFILE targeting an existing file, or no recognized patch/verdict.
- 6 failed compilation/type checking: wrong argument types, invented fields/symbols, incorrect container types and an undefined local variable.

These are failure stages, not estimates of how many patches would pass semantic gates after correction. Full per-ticket evidence is in failure-analysis.json.

## 1. Separate source discovery from the patch-correction allowance

scripts/factory-ng-run-engine-ticket.py:repair_available allows Claude one bounded repair after a NEED continuation; Qwen is denied that repair once need_continuation_attempted is true. Qwen used NEED on 24/27 ticket versions, including 17/18 failures. Those 17 had no bounded repair. This is a concrete harness asymmetry, not a model-quality inference. Claude's compared successes include four that used bounded repair (two gate corrections); three also used a bounded investigation helper. Qwen's six successes include one repaired success and no investigation helper.

Recommended qualification experiment: allow at most one source continuation, one initial patch, and one focused patch correction, rather than making source discovery consume the correction. Preserve scope and all gates; do not reset ticket retries or replay live jobs automatically. Test frozen failed tickets first.

## 2. Supply actual API declarations before implementation

The attacker/library-placement v2 failure treated Player.Library (*Zone) as []*Card and passed *Card to RemoveCard, which requires a string. Neither the prepared packet nor its requested-context supplement included the Zone or Player struct definition or RemoveCard signature. A missing declaration is not proof of causation, but matches the observed wrong assumptions.

Use bounded database discovery/source resolution to include exact types, function signatures and a working test fixture from the pinned checkout. Goose's read-only MCP experiment demonstrated this integration; it also showed limitations in query quality, missing symbol IDs and advisory tool budgets. Enforce the evidence budget in the harness before production use. Keep final implementation staged.

## 3. Manage completion budget and output protocol explicitly

Benchmark a larger bounded completion allowance (e.g. 24k or 32k), or a supported separate reasoning/answer allocation, on the five ceiling failures. Keep thinking enabled: the prior no-thinking trial was faster but produced an invalid patch. Larger budgets increase time and do not guarantee correct code. Require complete validated edit blocks and unchanged gates; do not accept truncated output.

For malformed replies, give the bounded correction exact parser diagnostics and current file text. Preserve strict application rather than guessing replacement text. A schema-based edit tool is a possible later experiment, not an already validated replacement.

Retain token counters even when rejecting a response, and distinguish completion-budget exhaustion from transport/server failures. The current adapter raises before emitting telemetry for cap rejections, obscuring the real loss.

## Expected impact and limits

Repair parity and better source evidence are the first priorities. Twelve of the eighteen failures stopped at output/patch handling; the other six stopped at compilation. The data identifies plausible recoverable bottlenecks, not a predicted 45% success rate. Qualify changes on a fixed failed-ticket cohort against unchanged apply, compile, semantic and full integration requirements. The Claude/Qwen cohorts remain different tasks/dates, so improvement must be measured rather than assumed.
