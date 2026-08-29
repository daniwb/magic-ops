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
