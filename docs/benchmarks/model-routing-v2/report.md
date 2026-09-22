# Model-routing benchmark v2 — result

Run date: 2026-08-28  
Ticket: `benchmark.map.target-player-draw/v2`  
Source: `6d85a3d649103d8f3a50fb6436ed266c77b0942a`

## Outcome

The prepared, constrained pipeline works across Qwen and the larger remote
models.  This directly overturns the v1 interpretation that Qwen or Claude
were broadly unsuitable: v1 used a generic, free-editing, combined Map/Engine
agent task.  v2 used a Map ticket with indexed evidence, block-only mutation,
harness-owned gates, and each model's appropriate executable profile.

All model-call times below exclude deterministic gate time.  Cost is actual
provider-reported cost for Claude and the versioned local price calculation for
Codex.  Qwen's API cost is zero; hardware and electricity cost were not
measured.

| Model | Profile | Accepted | Quality | Model-call time | Cost | Repair |
|---|---|---:|---:|---:|---:|---|
| Qwen3.8 27B local (direct) | `qwen-prepared-direct` | yes | 100 | 132.813 s | $0.000000 | one bounded NEED |
| Qwen3.8 27B local | `qwen-prepared-local` | yes | 100 | 724.683 s | $0.000000 | no |
| Codex Luna | `codex-constrained` | yes | 100 | 53.358 s | $0.004894 | no |
| Codex Terra | `codex-constrained` | yes | 100 | 34.535 s | $0.033968 | no |
| Codex Sol | `codex-constrained` | yes | 100 | 23.395 s | $0.061603 | no |
| Claude Haiku | `claude-staged` | **no** | 65 | 68.051 s | $0.048603 | yes |
| Claude Sonnet | `claude-staged` | yes | 100 | 83.461 s | $0.269277 | no |
| Claude Opus | `claude-staged` | yes | 100 | 63.230 s | $0.204301 | no |

Quality is 35 points for exact Map behavior, 35 for the Map-to-converter-to-
Engine boundary, 15 for regressions, and 15 for scope/diff discipline.  Every
accepted receipt passed all four harness-owned gates.

## Raw telemetry

The fields remain separate; cached input is not added twice.  The Claude CLI
reports normal input separately from cache-read/cache-write input; Codex's
input field includes its cache-read portion.  Qwen's receipt also records its
non-cached input (`63,698`) explicitly.

| Model | Provider input | Cache read | Cache write | Output | Reasoning |
|---|---:|---:|---:|---:|---:|
| Qwen local (direct) | 12,513 | 1,728 | 0 | 686 | unavailable |
| Qwen local | 773,819 | 710,121 | 0 | 2,531 | unavailable |
| Codex Luna | 53,846 | 47,104 | 0 | 2,170 | 1,291 |
| Codex Terra | 35,434 | 28,160 | 0 | 1,149 | 622 |
| Codex Sol | 28,922 | 19,968 | 0 | 890 | 296 |
| Claude Haiku | 6,403 | 37,883 | 3,796 | 6,164 | 4,707 |
| Claude Sonnet | 15,375 | 23,585 | 42,194 | 8,057 | 6,654 |
| Claude Opus | 2,749 | 14,258 | 6,539 | 5,177 | 4,077 |

## Haiku result

Haiku's first response had the correct semantic idea but its converter SEARCH
window was too short, which the atomic applier rejected.  The single permitted
repair repeated both files but encoded the parser target as a value field
instead of the required third target tuple.  The converter/Engine and
regression gates passed; the exact positive Map gate failed.  This is a real
quality failure under this profile, not an adapter failure.

## Nemotron 3.5 Lightning free qualification — 2026-08-31

`nvidia/nemotron-3.5-lightning:free` is **not qualified for a Factory NG
worker** by this benchmark.  The endpoint smoke test succeeded and every
attempt was free, but none passed the frozen contract:

| Profile attempt | Accepted | Model-call time | Provider input | Cache read | Output | Result |
|---|---:|---:|---:|---:|---:|---|
| `openrouter-prepared-direct@1.0.0` | no | 206.457 s | 4,558 | 0 | 7,102 | Correct general intent; both initial and repair SEARCH blocks reconstructed indentation incorrectly. |
| `openrouter-prepared-agentic@1.0.0` | no | 687.005 s | 154,341 | 93,568 | 20,272 | Exhausted the tool loop into prose and emitted no blocks. |
| `openrouter-prepared-agentic@1.0.1` | no | 315.705 s | 153,569 | 58,752 | 12,563 | Forced-final adapter emitted blocks, but the Python SEARCH indentation was invalid and the Go replacement referenced an undefined variable. |

Because those generic profiles confounded source reconstruction with model
quality, four Nemotron-specific structured-edit revisions were also tested.
The adapter derives exact SEARCH text from model-selected source ranges,
requires both ticket paths, and syntax-checks its in-memory candidate before
emitting any mutation blocks.

| Structured profile | Accepted | Model-call time | Effective tokens | Percent of 200k | Result |
|---|---:|---:|---:|---:|---|
| `nemotron-structured-edit@1.0.0` | no (15/100) | 174.186 s | 16,310 | 8.2% | Structured transport applied, but Nemotron collapsed Python statements, selected an over-wide range, and omitted the converter behavior. |
| `nemotron-structured-edit@1.1.0` | no | 48.890 s | 6,319 | 3.2% | A nested replacement-array schema triggered an NVIDIA upstream 502; the schema was discarded. |
| `nemotron-structured-edit@1.2.0` | no | 420.202 s | 20,571 | 10.3% | The flat schema worked, but low-effort reasoning consumed the forced-tool completion without a tool call. |
| `nemotron-structured-edit@1.3.0` | no | 187.169 s | 36,063 | 18.0% | Separating planning from no-reasoning emission restored tool calls, but both attempts omitted a required path. |
| `nemotron-structured-edit@1.4.0` | no | 194.611 s | 31,812 | 15.9% | Retaining a valid partial submission restored both-file coverage; the initial candidate then failed Go syntax preflight and the benchmark repair failed Python syntax preflight. |
| `nemotron-structured-edit@1.5.0` | no | 195.280 s | 34,253 | 17.1% | The corrected partial-validation control flow was exercised. Both independent attempts retained syntax-valid Python edits, then produced invalid Go in the focused missing-path submission. |

Effective tokens use the Factory rule `provider input + output`, including
cached input exactly once.  All structured attempts were far below the 200k
ordinary target and therefore also below the 500k warning/reflection limit.
The limiting factor is reliable code correctness, not token budget.  The v1.5
receipt is the decisive qualification result: the adapter successfully solved
exact-source transport, required-file coverage, and safe partial retention,
yet two independent focused attempts still failed Go syntax before any product
mutation.

The first generic agentic trace exposed two real adapter defects: the advertised
regex tool used basic `grep`, and the final-answer phase continued to expose
tools.  Profile 1.0.1 uses `rg` and removes tools from that phase.  The fresh
run was faster and reached patch output, but still failed the unchanged
harness; therefore the adapter repair is not being confused with model
qualification.  Do not add any Nemotron profile to `factory-ng-workers.json`
unless a future model/provider revision first passes this frozen ticket and
then the independent second-ticket promotion gate.  Further benchmark-specific
prompt or retry tuning is not justified by the current evidence.

### Nemotron 3 Ultra 550B-A55B free — 2026-09-01

`nvidia/nemotron-3-ultra-550b-a55b:free` was tested with the unchanged
`nemotron-structured-edit@1.5.0` adapter, frozen ticket, source revision, and
harness. It is also **not qualified**:

| Accepted | Model-call time | Provider input | Cache read | Output | Effective tokens | Percent of 200k | Cost |
|---:|---:|---:|---:|---:|---:|---:|---:|
| no | 57.592 s | 23,746 | 0 | 3,185 | 26,931 | 13.5% | $0.00 |

The initial attempt exhausted its 1,800-token forced-submission completion
without making a `submit_edit` call. The independent benchmark repair did use
the structured tool, but submitted the Python path twice and omitted the
required Go path even after the adapter narrowed its correction to that
missing path. As with Lightning, budget is not the blocker; reliable adherence
to the structured edit contract is. Ultra was about 3.4 times faster than the
latest Lightning qualification on model-call time, but produced less usable
output. It must not be added to the live worker configuration.

### GLM 5.2 free — 2026-09-01

The requested `z-ai/glm-5.2:free` bounded agentic qualification could not
reach inference. OpenRouter returned HTTP 429 for all 12 initial attempts and
all 12 harness-repair attempts: provider input `0`, output `0`, cost `$0.00`.
This is an **infrastructure-unavailable result, not a GLM quality failure**.
The run consumed 730.761 seconds solely in bounded rate-limit backoff. No patch
was produced or applied, and GLM remains unqualified because there is no model
evidence yet.

The receipt predates the harness classification correction and therefore says
`CONTRACT_FAILED`; its zero usage and repeated 429 trace are authoritative.
The harness now records a failed, empty, zero-usage model call directly as
`INFRASTRUCTURE_FAILURE` and does not spend a semantic repair call on it.

### MiniMax M3 free direct — 2026-09-01

`minimax/minimax-m3:free` passed the frozen ticket with the non-agentic
`openrouter-prepared-direct@1.0.0` profile on the evidence-corrected v2 run:

| Accepted | Quality | Model-call time | Provider input | Cache read | Output | Effective tokens | Percent of 200k | Cost | Repair |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| yes | 100/100 | 161.058 s | 4,162 | 256 | 9,852 | 14,014 | 7.0% | $0.00 | one bounded gate repair |

The initial response applied cleanly but encoded the real player target in the
wrong data shape. The focused repair corrected both the parser tuple and the
converter's `ability.Target` handling; the exact Map behavior, converter/Engine
boundary, regressions, and scope gates all passed. The initial completion used
its full historical 8,000-token cap. The live profile therefore uses the new
Factory-wide 16,000-token completion cap while retaining two bounded calls.

An earlier preserved receipt scored 15/100 because the gate-repair prompt
showed baseline regions while asking for a delta against already-mutated
source. Its repair response contained the right semantic correction but could
not match the current SEARCH text. The harness now includes the current applied
diff for this bounded repair; the v2 receipt is the qualification result.

MiniMax then passed a second independently frozen Map ticket in one call:
6,630 provider-input tokens, 5,353 output tokens, 11,983 effective tokens, no
repair, and all six harness-owned gates green. That satisfied the direct
profile's Map promotion gate. It is now registered as the enabled
`minimax-prepared-direct@1.0.0` Factory NG worker; bounded Engine use remains
inside the same isolated-clone controlled rollout and does not grant the model
integration, push, or deployment authority.

## What this changes

- The factory must select a **profile**, not merely a model name.
- Qwen is a viable local implementation worker for small, evidence-complete
  Map work. The new no-tools direct profile also passed 100/100 using 12,513
  input tokens and 132.813 seconds—about 62× less input and 5.5× faster than
  its agentic profile on this ticket. Its first no-tools call made one bounded
  `NEED` request for the exact `p_gain_life` target precedent; the second call
  emitted the accepted patch. The direct profile should therefore be the first
  local route; agentic Qwen becomes an explicit escalation for incomplete
  evidence.
- Sonnet and Opus are viable again when run in their old pipeline-compatible
  staged profile.  This result does not support the old free-editing benchmark
  as a routing signal.
- Codex Luna is the cheapest accepted remote result on this one ticket;
  Sol is the fastest.  Neither becomes a production default until a second,
  independently frozen Map ticket confirms the result.

## Benchmark integrity notes

During construction the harness caught and repaired two adapter defects before
they were treated as model outcomes: Codex JSONL output was initially handed
to the applier without extracting the final agent message, and the v2 retry
path initially omitted the atomic-application fact.  Fresh runs were made
after each correction.  The receipts under `runs/` are the authoritative final
attempts.
