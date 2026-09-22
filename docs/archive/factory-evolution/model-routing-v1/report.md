# Factory NG model-routing benchmark v1

> Archived result. Preserved with the complete v1 reproducibility bundle for
> comparison with later routing decisions.

One frozen cross-layer ticket was run from the same base commit in isolated
worktrees. The harness—not the candidate—checked Map behavior, the production
converter/Engine boundary, parser and cards regressions, and scope discipline.

| Model | Model time | Marginal cost | Quality | Result |
|---|---:|---:|---:|---|
| Qwen3.8-27B Q8 local | 6m 15s | $0.000 | 15/100 | Parked; no patch |
| GPT-5.6 Luna | 12m 35s | $0.144 | 65/100 | Engine half only |
| **GPT-5.6 Terra** | **8m 58s** | **$0.852** | **100/100** | **Pass** |
| GPT-5.6 Sol | 9m 24s | $2.662 | 100/100 | Pass |
| Claude Haiku 4.5 | 0m 59s | $0.170 | 15/100 | Turn cap; no patch |
| Claude Sonnet 5 | 9m 58s | $1.893 | 50/100 | Engine half; scope violation |
| Claude Opus 5 | 6m 25s | $2.868 | 30/100 | Scratch exploration only |

## Decision

Route medium cross-layer Map+Engine tickets to **GPT-5.6 Terra** by default.
It was the lowest-cost complete pass and was faster than Sol. Escalate to Sol
only after Terra has a concrete failed gate or an explicit high-risk reason.

Use Luna only for bounded Engine-child work where a parent ticket has already
settled the Map change. Use local Qwen for cheap preparation, retrieval, and
visible park/refusal work—not unattended implementation of this class.

The tested Claude CLI routes are not acceptable for this worker contract yet:
Haiku used its turn budget without editing; Sonnet completed only the Engine
half and left a generated binary; Opus stopped at a scratch test. This is a
measurement of this exact bounded prompt/package and CLI configuration, not a
general statement about all Claude interfaces or models.

## Measurement notes

- Model time is the candidate call only. Harness gating time is stored in each
  raw receipt and excluded from the headline to avoid cold-build/cache noise.
- Costs are provider-reported where available. Claude CLI internally routed
  Sonnet and Opus calls through Haiku as well; those submodel costs are included.
- Local `$0` means no marginal API charge. Energy and hardware depreciation
  were unavailable and must be added before a total-cost comparison.
- This is a screening result on one known golden ticket. Do not promote the
  routing rule permanently until Terra and Sol are compared on at least three
  pre-compiled unseen tickets, with a fresh independent reviewer for every
  candidate that passes deterministic gates.

Raw receipts: `runs/*.json`; normalized data: `results.json`.
