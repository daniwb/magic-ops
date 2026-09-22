# Production Engine comparison — 2026-09-20

Earlier active Claude period: September 17 UTC, claude-sonnet-5, staged profile.
Qwen: September 20 through approximately 14:45 UTC, halogen-qwen3.8-flash-next, Goose staged.

| Outcome | Claude | Qwen/Goose |
| --- | ---: | ---: |
| Integrated and pushed | 24 | 6 |
| Failed | 12 | 18 |
| Parked | 17 | 2 |
| Integration conflict | 0 | 1 |
| Finished ticket versions | 53 | 27 |
| Integrated share | 45.3% | 22.2% |

Engine tickets only; Map dependency discovery excluded. Each ticket version counted once, even if it generated multiple observations. Retry versions count separately in both cohorts. Queued or usage-gated entries and the running Qwen ticket without a finished observation are excluded. One more Qwen ticket finished since the earlier 26-ticket summary.

Claude failures: 12 gate failures. Qwen failures: 11 gate failures, 5 infrastructure failures, 2 model-protocol failures. All 30 successes have matching pushed integration receipts with full-sharded-suite passed, and none is an excluded candidate. Qwen's conflict is confirmed in excluded_candidates of its integration receipt. Exact per-ticket receipt references are in results.json.

Claude's integrated proportion is about twice Qwen's in this sample, but it parked nearly one-third of its tickets. Different tasks, dates, source revisions and preparation quality prevent a controlled model-quality comparison. No equal-time throughput or cost conclusion follows from these counts.
