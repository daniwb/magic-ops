# Staged Pipeline Workflows (Map / Engine / Handler)

As of 2026-08-07. Idea (Dani): "less thinking, more doing" — ticket work is
stereotyped, so the **harness does the deterministic steps** and the model
gets **one focused call** instead of an agentic 100-turn session. Every stage
is gate-verified; escalation only on genuine failure (exit 2). Measurements
below are from the 2026-08-07 validation series.

Scripts: `magic-ops/scripts/{map,engine,handler}-pipeline.sh` + `*-pack.py`,
shared applier `map-pipeline-apply.py`, region fetcher
`pipeline-fetch-regions.py`.

> Redesign note (2026-08-16): the map→engine handoff is being migrated from
> free-text `missing_prim` values to atomic, many-to-many capability contracts
> with an immutable attempt ledger. See [factory-redesign.md](factory-redesign.md).

---

## 1. MAP pipeline (`map-pipeline.sh TICKET [--push]`)

Goal: map one REPARSE-MAP ticket (miss shape) via a parser/converter patch.

| # | Step | Who |
|---|------|-----|
| 1 | Extract shape + ticket from the dispatcher DB | script (pack.py) |
| 2 | Live examples: scan the review pile for up to 5 cards that miss with this shape RIGHT NOW (oracle text + exact misses) | script |
| 3 | Grep code regions by shape token (slotparse/reparse/converter) + knowledge-service hits | script + kb :4103 |
| 4 | **Decide the mapping rule** (or park: NEEDS_PRIMITIVE / SEMANTIC_GAP / …) | **model** |
| 5 | Patch as SEARCH/REPLACE blocks | **model** |
| 6 | Apply (exact match, game/ guard) + gate: build, vocab/shape tests, review-pile delta (shape counter; total-misses fallback for small shapes invisible in the top-40 table) | script |
| 7 | Commit + push branch `reparse/task-N` → integrator lands it | script |

Gate metric: shape instances drop OR total-misses drop (isolated clone).
Forbidden: `backend/game/` (auto-park in the applier).

## 2. ENGINE pipeline (`engine-pipeline.sh TICKET [--push]`)

Goal: build ONE small primitive from a park (`missing_prim`).
Input ticket: blocked with missing_prim (park from the map lane or map pipeline).

| # | Step | Who |
|---|------|-----|
| 1 | Load primitive name + park REASON (from pipeline reply files) + example cards | script (pack.py) |
| 2 | Executor regions: grep tokens from the primitive name + backtick identifiers from the REASON across game/cards files, ranked | script |
| 3 | Find a worked example (kb /find) + attach a shape-test template (head of a recent shape_*_test.go) | script + kb |
| 4 | **Decide the smallest engine change** (or park: FRAMEWORK/AMBIGUOUS — framework-sized work stays with manual engine rounds) | **model** |
| 5 | Edits (SEARCH/REPLACE, game/ ALLOWED via --allow-game) + NEW test file (NEWFILE) | **model** |
| 6 | Apply + gate: build, vocab/shape/combat tests, **new `+func Test` in the diff required** (after `git add`! untracked-file trap), **full sharded suite** | script |
| 7 | Commit + push branch `reparse/engine-task-N` → integrator | script |

## 3. HANDLER pipeline (`handler-pipeline.sh TICKET [--push]`)

Goal: ONE per-card handler (cardfns) + behavior test. The most stereotyped tier.

| # | Step | Who |
|---|------|-----|
| 1 | Card from the ticket title, oracle text from carddb | script (pack.py) |
| 2 | Nearest existing handler via kb /similar → **full file + its test as template** into the pack | script + kb |
| 3 | Helper candidates via kb /find (oracle text as query) | script + kb |
| 4 | **Design the handler** (or park: precise kebab-case primitive name) | **model** |
| 5 | Two NEWFILE blocks: `cardfns/<Name>.go` + `<Name>_test.go` | **model** |
| 6 | Apply + gate: build, new test in diff, full sharded suite; **on red: bugfix rounds on the KEPT tree** (its own files + exact error → correction blocks only, up to BUGFIX_MAX=3, NEWFILE may overwrite) | script (+model for fixes) |
| 7 | Commit + push branch `reparse/handler-task-N` → integrator | script |

game/ stays guarded (handlers use primitives/helpers; if one is missing → park).

---

## Shared mechanics

- **Exit codes** (all three): 0 = gate green (+push), 4 = park (a success!
  the demand gets filed), 2 = 2 model calls exhausted → **escalate**, 1 = infra.
- **Model modes**:
  - Sonnet: read-only agentic (Read/Grep/Glob, 25 turns, must-emit rule at
    the end) — mutation ALWAYS stays block-based with the harness.
  - Local (PIPE_BASE_URL = shim :4102): single-shot without tools via a
    direct /v1/messages curl (SSE parsing!), @@@ markers instead of <<<
    (the llama-server parser 500s on <<<), + bugfix rounds. The claude CLI
    is unusable locally (it advertises internal tools → gpt-oss answers
    with tool_calls + empty content).
- **NEED round**: the model may request missing regions once
  (`NEED: <path|symbol>`); `pipeline-fetch-regions.py` delivers them.
- **Serial GPU operation** (Dani): NEVER run parallel to the rl1 lane on the
  llama-server — start tests/pipeline runs at the ticket boundary
  ("cycle done"), pause the lane, restart the launcher afterwards.

## Escalation ladder (cost order)

1. **Local pipeline** (handler: single-shot + bugfix) — $0, ~4–8 min
2. **Local agentic** (rl1 worker) — $0, ~20–25 min, 4/4 green today (incl. map!)
3. **Sonnet pipeline** — ~0.3–1M tokens, ~5–10 min
4. **Sonnet agentic** (fleet worker) — ~2.7M median, reserved for true exploration

Each rung fires only on a gate-verified failure of the rung below.

## Measurements, validation series 2026-08-07 (Sonnet unless noted)

| Run | Result | Tokens (raw) | Duration |
|-----|--------|--------------|----------|
| Map #2485 triage | Park each_player_discard (verified correct) | ~30k | 63 s |
| Map #2482/#2515 triage | Parks with code-verified gap lists | 30–40k / ~0.9M (agentic) | 35 s–3 min |
| Engine #2485 build | GREEN — executor + test + full suite | ~1.0M | ~10 min |
| Map #2485 after primitive | GREEN — total-misses −8 | ~0.57M | ~9 min |
| Handler #2192 | GREEN — handler + test, first attempt | ~0.58M | ~9 min |
| Handler #2193 local | **GREEN — 1 bugfix round** (single-shot + step-6 fix loop) | $0 | ~9.5 min |
| **Full circle Map→Engine→Map** | park → primitive → green | **~1.6M** | ~20 min |
| Baseline: emergent engine work in an agentic session (#2457) | green | 22.5M | hours |

## Open items

- Lane integration: pipelines claim via the dispatcher `/claim` (lease =
  dedup gate + dashboard visibility); ticket creation + self-claim for
  engine demands coming out of parks (Dani's step-3 idea); name
  normalization for demand dedup (map parks ≠ cardfns helper namespace —
  the Brimaz lesson!).
- ~~Port bugfix rounds to the map/engine pipelines~~ done 2026-08-07 (BUGFIX_MAX=2, kept tree, tier gate re-run).
- ~~Local pipeline compile limit~~ solved 2026-08-07: bugfix rounds on the
  kept tree got gpt-oss to green (Cemetery Gatekeeper, 9.5 min, $0).
