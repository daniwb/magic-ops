**Verdict: CONTINUE_WITH_CHANGES**

Experiment 001 should continue, but not to implementation yet. The next smallest safe step is a fresh planner revision that preserves Stage 1 and Stage 2c artifacts, and only repairs the two reviewed blockers:

1. Add all `LifeChanged.amount` consumers to scope and define the bounded projection invariant precisely.
2. Replace the one-unit sizing claim with either a defensible lockstep argument or an explicit split into independently testable units.

Why the successful stages were expensive:

Stage 1 used `6,178,439` input tokens, but `5,920,512` were cached. Only `257,927` were uncached. So the apparent huge total is mostly repeated cache-read context, not new text being introduced each time. Still, the uncached part was about 18x the trivial calibration’s uncached baseline. Useful work included real issue verification, broad code tracing, replacement/life pipeline inspection, analogous pattern discovery, scope matrix construction, and a complete implementation/test plan. Avoidable expansion came from repeated skill reads, the planner loading reviewer guidance inside the planning stage, broad `rg`/`sed` outputs, repeated full-file/context reads, external lookups, and allowing orchestration checklists to become part of the active working context.

Stage 2c used `926,186` input tokens, with `825,216` cached and `100,970` uncached. It was much cheaper because it reviewed an existing artifact and used targeted probes. The work was useful: it found two concrete blocking defects, especially missed `LifeChanged.amount` consumers. But it still expanded avoidably by loading full review and replacement skill text, rereading the full Stage 1 plan, running broad searches, and attempting a cargo probe in an environment where `cargo` was absent.

The key distinction: cached tokens show the orchestration/context replay burden; uncached tokens show fresh inspection and command-output growth. Both successful stages did useful engineering work, but both paid extra for oversized reusable context being pulled into the active turn instead of referenced as compact artifacts.

**Factory NG Lessons**

- Treat plans, reviews, and command outputs as addressable artifacts with hashes, not text to repeatedly inline.
- Require call-level usage telemetry; stage-level totals are insufficient for pinpointing waste.
- Separate role contracts strictly: planner should not self-review when the outer workflow requires a fresh reviewer.
- Skills need compact mode-specific checklists, not full instruction bodies on every invocation.
- Broad repository scans should produce capped, structured summaries by default.
- Budget thresholds should trigger reflection and route changes, not discard useful artifacts.
- Failed/interrupted turns need provider-level accounting; current JSONL misses partial consumption.
- Phase-fit sizing should be machine-checkable early, before a full implementation plan grows around a questionable unit boundary.

Continue with a Stage 1d revised plan only. Do not implement until Stage 2d returns clean.