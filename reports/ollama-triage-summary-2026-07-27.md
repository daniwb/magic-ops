# Local-GPU triage evaluation — outcome (2026-07-27)

**Question:** can the local GPU (24 GB, Ollama box 192.168.1.15) pre-check card
tickets for missing shapes/primitives, saving Claude tokens on first try?

**Answer:** not as an autonomous park authority — no local model reaches the
precision where a MISSING verdict may park a card. But three free lanes ARE
validated, with `qwen3.6:27b think` as the recommended annotator config.

## Method

`scripts/ollama-triage.sh` — single-shot `/api/chat` per card (NO agentic
loop, NO Claude-CLI harness: that combination leaked memory on the
orchestrator host in July). Prompt ≈ 18k tok: shape catalog + signature-only
primitive index + strict 3-line verdict contract (BUILDABLE /
MISSING_SHAPE|PRIMITIVE: kebab / UNSURE). Hard rules: unsure ⇒ UNSURE ⇒
requeue for Sonnet; every MISSING claim is grep-refuted against the full
catalogs by the script (the mandatory-grep rule, deterministic); MISSING is
never terminal — it becomes a `LOCAL-TRIAGE:` ticket annotation for Sonnet to
precheck. Memory guards: 2 GB ulimit, curl timeouts, num_predict cap,
stream:false; measured peak RSS 22 MB.

Ground truth: 20 resolved dispatcher tickets (10 built = BUILDABLE,
10 parked with missing_prim = MISSING) + 2 smoke cards.
Reports: `ollama-triage-2026-07-27-{0842,0843,0858,0919,0923,0929,0937,1105,1108}.md`.

## Results (same 20 cards)

| model | missing-recall | buildable-recall | false-park | precision(MISSING) |
|---|---|---|---|---|
| qwen3-coder:30b | 10/10 | 0/10 | 10 | 50% |
| gemma4:e4b no-think | 1/10 | 10/10 | 0 | 100% (n=1) |
| gemma4:e4b think | 3/10 | 6/10 | 2 | 60% |
| gpt-oss:20b (always thinks) | 4/10 | 4/10 | 3 | 57% |
| qwen3.6:27b no-think | 8/10 | 4/10 | 6 | 57% |
| **qwen3.6:27b think** ✅ | 4/10 | 7/10 | **1** | **80%** |

Key findings:
- Composability judgment ("could Sonnet build this from the 283 primitives?")
  is the wall. qwen3-coder says MISSING to everything (incl. primitives
  literally in its prompt — Krark's-Thumb class); gemma-no-think says
  BUILDABLE to everything. Only qwen3.6+think shows usable discrimination,
  with errors falling almost entirely in the harmless direction.
- Thinking models: gemma4/qwen3.6 honor `think:false`; gpt-oss does not and
  needs num_predict ≥ 3000 or content comes back empty (thinking eats the
  budget — done_reason "length").
- qwen3.6/qwen35 family needs Ollama ≥ 0.31 for GPU serving (box upgraded
  0.30.4 → 0.32.4 mid-eval; before that: size_vram=0, CPU-only, unusable).
  qwen3.5:35b (23.9 GB) never fit the 24 GB card and still doesn't.
- Stale-park detection works: both the grep-refute layer and qwen3.6
  independently flagged Dispelling Exhale's park as stale
  (`counter_unless_pay` exists as a shape today).
- Ollama's server-side prefix cache works across jobs with the shared static
  prompt prefix: first card ~22 s prefill, subsequent 2–6 s (no-think).

## Recommended wiring (not yet done)

1. **Record-shaped routing** (open item: DSL-RECORD tagging): qwen3-coder or
   qwen3.6, 22/22 on "is every ability a known shape?" — route hits to the
   cheap record lane. False yes → linter catches; false no → costs nothing.
2. **Stale-park grep sweep** (no LLM): rerun grep-refute over all parked
   tickets' missing_prim; hits → requeue candidates. 1 confirmed find in 10.
3. **LOCAL-TRIAGE annotations**: `MODEL=qwen3.6:27b THINK=true
   NUM_PREDICT=4000` over the todo queue; MISSING hints (80% precision, 40%
   recall) + evidence lines attached to tickets; Sonnet batch-prechecks the
   claims. Never parks on its own.

## Operational rules learned (memory-leak postmortem)

- Never run the Claude-CLI agentic harness against a local/Ollama backend:
  no prompt cache (quadratic re-prefill) + retry buffering leaked memory on
  the orchestrator host (which has NO swap) until the run died.
- Any experimental worker: wrap in a memory cap (ulimit / systemd-run
  MemoryMax) and hard per-request timeouts; restart Ollama between batches
  if long-running.
- Ollama durations are nanoseconds (923000000 ≈ 0.92 s, not minutes).
