# September 19 — Engine dependency failure census (blocked Map work)

**Status: filed for follow-up work. Nothing here has been changed in the engine, in
policy, or in live job state. All findings are read-only observations.**

## Why this review exists

The factory reported `ticket supply exhausted: enabled workers have had no work for
ten minutes`. That alert was accurate but not the cause. A separate diagnosis
(same day) established that the generic Map/Engine producer frontier is genuinely
drained: of 16,392 audited cards, 10,264 carry exactly one remaining miss, but
only 876 are shape-eligible for the single-miss lane and all 876 are already owned
by existing `build-plan:` production keys. That is a capability problem, not an
orchestration fault.

This review covers the **other** supply pool: work that already exists and is
stranded behind terminal Engine tickets.

## The shape of the problem

Blocked Map jobs point at terminal Engine parents via
`job.dependency_blocker.children`. The relation is effectively **1:1** — reviving
*N* engine tickets unblocks *N* Map jobs. Unlock is linear, so the census is the
whole value of the pool.

At census time (`census-summary.json`):

| parent state / outcome | count |
|---|---|
| `parked` / `parked` | **394** |
| `failed` / `gate_failed` | **294** |
| `failed` / `preparation_failed` | 18 |
| `failed` / `infrastructure_failed` | 9 |
| `failed` / `infrastructure_failed_provider_capacity` | 7 |
| `failed` / `infrastructure_failed_model_protocol` | 6 |
| `parked` / `infrastructure_failed_model_protocol` | 2 |
| `failed` / `source_unavailable` | 1 |
| `awaiting_verification` / `working` / `completed` (non-terminal) | 4 |
| **total distinct engine parents** | **735** |

Counts drift slightly because the controller is live. Re-run `build_census.py` for
current numbers.

## Evidence handling (read this before working tickets)

`log_path` is **purged** — only 2 of 294 gate-failed jobs still have their log.
Do not chase `log_path`.

`result_path` and the full observation receipt are present for **all 735 parents**
(verified: 0 missing on disk; only 3 rows carry no receipt field at all). The
receipt (`schema: factory.observation-receipt/v1`) is the source of truth.
Useful fields:

- `failure_category` — `model_response`, `candidate_gate`, `missing_evidence`,
  `gate_failed`, `compile_or_vet`, `edit_scope`
- `gates[]` — the gate that actually failed, with `detail`
- `capability_assessments[]` — `classification` (`connection` / `engine_gap` /
  `reuse` / `insufficient_evidence`), `existing_symbols`, `remaining_gap`, `stage`
- `integration` — `"observation_only"` on these receipts

## Finding 1 — the repair lane's profile allowlist excludes 100% of current failures

`candidate_retry()` in `scripts/factory-ng-produce-build-plan.py` admits a
`gate_failed` repair **only** when the profile is `qwen-prepared-direct@1.0.2`.

The 294 gate-failed engine tickets are on:

| profile | count |
|---|---|
| `codex-constrained@1.1.0` | 176 |
| `claude-staged@1.0.0` | 68 |
| `qwen-prepared-local@1.0.1` | 27 |
| `claude-agentic@1.0.0` | 21 |
| `codex-constrained@1.0.0` | 2 |

**None** is `qwen-prepared-direct@1.0.2`. `census-summary.json` reports
`repair_lane_eligible_count: 0`.

Compounding this: `retry_generation` is `None` on **all 294**, so the
`generation < 1` budget test would pass for every one of them. The profile filter
alone is what excludes the entire pool. This looks like a stale routing leftover.

**Action:** review widening the repair-eligible profile set. This must not become a
supply-manufacturing trick — keep the existing "never reset historical attempts"
rule, keep `retry_generation` monotonic, and keep every gate intact. The change is
about *which profiles may be retried*, not about erasing failure history.

## Finding 2 — `allowed_paths` fences the model out of the file holding the seam

This is the largest structural blocker and it is **mis-labelled as model
ambiguity**.

**311** tickets carry an explicit `VERDICT: AMBIGUOUS` (272 `parked` + 39
`failed`). **48** carry an explicit `allowed_paths` / "outside allowed" /
"excluded from allowed" signal — all of them `parked`. In these
cases the model correctly located the required change, correctly refused to guess,
and then parked — because the file that must change is not in the ticket's
`allowed_paths`.

`VERDICT: AMBIGUOUS` is currently doing double duty for two opposite situations:

- *"I don't know"* — genuinely not retryable without more evidence
- *"I know, but I'm fenced out"* — retryable by re-scoping the ticket

These need separating. Suggested: a distinct verdict (e.g.
`VERDICT: OUT_OF_SCOPE_SEAM` with the named file) so the producer can route
re-scoping work instead of parking it terminally.

Named seam files across the census (full counts in `census-summary.json`):

| file | tickets naming it |
|---|---|
| `backend/game/ability_effects.go` | 40 |
| `backend/cards/converter.go` | 22 |
| `backend/game/gamestate.go` | 18 |
| `backend/game/activated_abilities.go` | 10 |
| `backend/game/gamestate_choice.go` | 8 |
| `backend/game/card.go` | 7 |
| `backend/cards/registry.go` | 5 |
| `backend/game/effect_sequence.go` | 5 |
| `backend/game/dynamic_amount.go` | 4 |
| `backend/game/gamestate_trigger_target.go` | 4 |
| `backend/game/replacement.go` | 4 |

Representative `remaining_gap` statements — precise, actionable, and currently
unactionable:

> "The required independent per-mana choice cannot be implemented within the
> allowed paths: activation validation and mana resolution live in
> `backend/game/activated_abilities.go`…"

> "no visibility into the mana-pool/AddMana API, the existing 'add N mana, choose
> one color uniformly' executor this task must preserve, or the
> restricted-mana-spending mechanism ('spend only to cast legendary spells')…"

> "bounce must resolve to the exact StackObject already bound by the preceding
> copy atom's target (a spell on the Stack) rather than an independently resolved
> battlefield target"

Note the FROZEN-registry rule still applies: new primitives go through
`registry_<topic>.go` init files and `shape_<topic>_test.go`. Widening
`allowed_paths` must not mean unfreezing `V2EffectRegistry`.

## Finding 3 — ~75 failures are non-semantic wasted spend

`no_verdict_in_output_count: 75` — "no edit blocks and no verdict found in model
output". These are harness/model-response failures, not hard Magic-engine problems.
A retry with better output handling would clear most of them.

Also non-semantic, from the gate details:

- 16 provider-side (7 "model at capacity", 9 "provider process exited 1")
- 8 "untested proposal exceeds TicketSpec scope"
- 7 `test_symbol_collision` — the required test name already exists outside the
  editable test file. This is a **ticket-construction defect**, not a model failure;
  the TicketSpec should pick a non-colliding test symbol at build time.
- SEARCH/REPLACE hygiene: verbatim mismatch, second REPLACE marker in one block

**Historical, do not chase:** 5 tickets show `bash: line 1: go: command not found`,
all dated Sep 4–7. `../../toolchain/go/bin/go` exists and reports `go1.25.0`, and
`launchers/launch-factory-ng.sh` exports it on `PATH`. That environment gap is
already closed.

## Artifacts in this directory

| file | contents |
|---|---|
| `census-summary.json` | aggregate counts, profiles, seam-file histogram, repair-eligibility |
| `engine-dependency-census.jsonl` | one row per engine parent — full machine-readable census |
| `worklist-scope-excluded-seam.json` | Finding 2 pool — 48 re-scope candidates |
| `worklist-parked-ambiguous.json` | 272 parked tickets with explicit `AMBIGUOUS` |
| `worklist-no-verdict.json` | Finding 3 pool — 75 harness retry candidates |
| `worklist-evidence-insufficient.json` | genuine evidence-gap pool (excludes scope-excluded) |
| `build_census.py` | regenerates all of the above from live state |

Each row carries: `engine_ticket`, `engine_ticket_path`, `state`, `outcome`,
`profile`, `attempts`, `retry_generation`, `receipt`, `failure_category`,
`failed_gates`, `blocked_map_jobs`, `named_seam_files`, `scope_excluded_signal`,
`evidence_insufficient_signal`, `explicit_ambiguous_verdict`,
`no_verdict_in_output`, `repair_lane_eligible`.

Regenerate with:

```bash
cd /data/magic-stack/development/magic-ops
python3 docs/factory-ng/reviews/2026-09-19-engine-dependency-failure-census/build_census.py
```

## Suggested order of work

1. **Finding 1 first.** It is the smallest change with the widest effect — one
   allowlist decides whether a 294-ticket pool is reachable at all. Review it in
   `candidate_retry()` and state the guardrails explicitly in the diff.
2. **Finding 2 second.** Triage `worklist-scope-excluded-seam.json` by seam file.
   `ability_effects.go`, `converter.go` and `gamestate.go` cover the bulk. Decide
   per-file whether widening `allowed_paths` is safe under the frozen-registry rule.
   Introduce a distinct verdict so this class stops being terminally parked.
3. **Finding 3 opportunistically.** Cheap wins, but they need harness changes
   (output parsing, test-symbol collision avoidance at TicketSpec build time)
   rather than a policy change.

## Hard constraints for whoever picks this up

- Parked and failed are **terminal by design**. Nothing here may be revived without
  an explicit reviewed decision. `docs/factory-ng/reviews/2026-09-17-producer-starvation`
  and the Sep-16 notes in `RUNBOOK.md` both forbid resetting historical attempts
  to manufacture supply.
- Never bypass gates. Never pipe a test run into `| tail` inside a chain.
- `git stash` is forbidden repo-wide (shared across worktrees).
- Kill by PID — `pkill` patterns match your own cmdline and the tmux server.
- The `V2EffectRegistry` literal is FROZEN.
- Canonical `openmagic` tree must be clean when you walk away; a dirty tree blocks
  NG integration.
- Live deployment is a separate explicit decision from a green integration.

## Related

- `docs/factory-ng/reviews/2026-09-17-producer-starvation/` — same symptom,
  different cause (a producer crash). Useful contrast: that incident had a
  traceback; this one has none.
- `docs/factory-ng/reviews/2026-09-16-four-hour-workers/` — origin of the
  `reviewed-harness-corrections-sep16` producer, which is now drained
  (`no_reviewed_harness_remaining`).
- `RUNBOOK.md` §"Empty supply and model leases (September 16)".
