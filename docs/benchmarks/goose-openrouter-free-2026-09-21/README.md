# Goose OpenRouter free connection check — 2026-09-21

The installed Goose configuration selects provider `openrouter` and model
`openrouter/free`; its existing credential was loaded without printing or copying
it into the repository. A temporary Goose root, empty extensions, `--no-profile`,
one turn and a 1,024-token limit isolated the probe from the personal configuration.

The live request passed the exact JSON assertion in 1.7 seconds, reporting 342
input tokens, 13 output tokens and $0 cost. The existing `goose_staged.decode_events`
parsed the response successfully. See `connection-check.json`. This proves
connectivity and basic response parsing, not Map/Engine ticket qualification.

The production adapter is pinned to `strix_halo` and Qwen. A Factory addition
needs a separate OpenRouter adapter/profile, credential provisioning for the
isolated process, shared provider cooldown, error handling, suitable context and
completion budgets, and frozen-ticket qualification through unchanged gates.
The probe events exposed the requested router name but not the resolved model;
production receipts should obtain that identity from provider metadata.

OpenRouter documents that this router randomly selects available free models:
https://openrouter.ai/openrouter/free/
This differs from the fixed local model and makes repeatability a qualification
concern. No production worker configuration was changed or ticket dispatched.

The sandbox attempt also showed that Goose can emit a network-error message with
exit code zero and a complete event containing zero usage. A future adapter must
reject that as provider failure rather than treating it as a successful proposal.

Startup: canonical checkout was clean; dashboard reachable; Factory running with
355 deferred tickets and zero runnable tickets. Watchdog reported one unresolved
integration failure. Canonical memory path was absent on this host; current
handoff and runbook were consulted. Controller log was empty and the watchdog
log path was absent.

## Authorized one-hour trial completed

The worker ran 2026-09-21 12:40:55–13:40:55 UTC (14:40:55–15:40:55 Zurich).
The persisted deadline stopped new claims automatically. The last already-running
harness finished after the deadline; the worker is now explicitly disabled.

10 attempts across 7 distinct tickets produced zero accepted patches.
Outcomes: {"infrastructure_failed": 4, "infrastructure_failed_model_protocol": 1, "blocked_by_capability": 1, "parked": 2, "infrastructure_failed_rate_limited": 1, "gate_failed": 1}.
Failures include missing/malformed strict edit blocks, provider failures and one
rate-limit outcome. One Map response produced a capability blocker. No trial
patch reached integration. See `trial-results.json` for every receipt.

The adapter, registered profile and staged runner support remain installed.
It uses the Goose credential, no extensions, shared cooldown, one NEED and one
correction. The expiry record lives in `state/factory-ng-worker-trials.json`,
independent of dashboard worker configuration. To authorize another trial, its
deadline must be explicitly renewed as well as enabling the worker.

Validation: 60 targeted regression checks passed with the Factory Go toolchain
and a temporary Go cache; the additional new-profile end-to-end fixture passed.
The new profile and all enabled profiles validated. A live adapter smoke check
returned the expected JSON at reported zero cost. The all-profile validator also
encounters a pre-existing invalid disabled Nemotron experiment; enabled-profile
validation remains green.

Receipt `resolved_model` currently contains the router alias, not a proven
underlying model identity; do not interpret it as a pinned-model comparison.

## Correction to trial diagnosis (2026-09-21)

The recorded rate-limit receipt was a classification bug, not evidence of an
actual 429 response. The adapter scanned raw reasoning text and could match
numbers such as source line 429. Replaying all 24 call artifacts identifies
four completion-budget exhaustions and one reasoning-only answer, with no
verified provider rate limit. Historical receipts remain immutable.
See `format-fix/retrospective-classification.json`.

Response contract v2 now supplies a phase-specific Goose system instruction
and a final reminder, a worked exact-patch example, and explicit no-tools
rules. Continuation and correction calls cannot offer another NEED round.
Provider error classification ignores reasoning/IDs and checks structured
completion/truncation signals before diagnostics. The strict patch applier
and all source/scope/semantic gates remain unchanged.

A live minimal correction produced an existing-file edit and a new unittest
file; the unchanged applier accepted both and the test passed. This validates
format compliance on that small example, not full Engine coding capability.
57 relevant regression tests pass. The production worker remains disabled.

Full follow-up, including strict marker normalization and the still-failing frozen
Engine replay: [format-fix/README.md](format-fix/README.md).

## Small Map qualification

A subsequent bounded qualification passed two of three historical Map tasks.
The third also failed a separate run with measured parser inputs. Worker remains
disabled. [Full results](small-map-qualification/README.md).
