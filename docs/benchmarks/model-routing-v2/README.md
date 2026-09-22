# Factory NG model-routing benchmark v2

This is the pipeline-faithful successor to v1.  It compares profiles, not a
universal autonomous-agent shell.  Every candidate receives the same frozen
Map ticket, source revision, evidence facts, permitted product-file scope, and
harness-owned acceptance tests.  Each profile invokes its appropriate native
executable and output contract:

- `qwen-prepared-local`: prepared local tool loop, with thinking disabled;
- `openrouter-prepared-direct`: prepared no-tools completion over OpenRouter;
- `openrouter-prepared-agentic`: prepared read-only tool loop over OpenRouter;
- `nemotron-structured-edit`: Nemotron-specific exact-range inspection and forced structured edit submission;
- `codex-constrained`: read-only Codex session returning patch blocks;
- `claude-staged`: the old pipeline-compatible read-only Claude call returning
  patch blocks.

The harness, not the model, applies patches, runs gates, and judges success.
One bounded `NEED` response and one focused repair call are available under the
same rule for every profile.  The source ticket is Map work; its acceptance
includes the Map-to-converter-to-Engine runtime boundary discovered by the
golden target-player-draw flow.  `backend/game` remains forbidden.

Run one profile:

```bash
python3 run.py --model-id qwen-local
```

Run the complete matrix only when all provider accounts and the local GPU are
intentionally available:

```bash
python3 run.py
```

Results are immutable JSON receipts in `runs/`.  A comparison is useful only
when the resulting report identifies the profile version, evidence digest,
acceptance outcome, provider counters (including cache counters), elapsed time,
and cost/accounting source.  Local Qwen's API cost is recorded as zero; its
electricity and hardware cost are unavailable, not assumed zero.

This remains a screening evaluation.  Routing promotion requires a second,
independently frozen ticket of the same work type.
