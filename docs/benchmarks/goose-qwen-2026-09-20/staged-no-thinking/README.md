# Final no-thinking comparison and staged rollout — 2026-09-20

Same frozen ticket, checkout revision and byte-identical staged prompt as the corrected-provider run. Goose 1.51.0, `strix_halo`, `halogen-qwen3.8-flash-next`, OpenAI-compatible engine, `max_tokens=16000`. Only the no-thinking run declares model request parameter `enable_thinking=false`; `request-settings.json` confirms it on the wire.

| Configuration | Generation | Input tokens | Output tokens | Result |
| --- | ---: | ---: | ---: | --- |
| Thinking enabled (provider default) | 860.261 s | 7,273 | 15,218 | All original ticket gates passed |
| Thinking disabled | 252.032 s | 7,236 | 3,462 | Strict patch application failed |

No-thinking was 70.7% faster and generated 77.3% fewer output tokens in these individual trials, but tried to SEARCH for absent source and create an already-existing `backend/game/ability_effects.go`. Validation stopped at patch application; no semantic success is claimed. Failed application was not manually repaired. The shared inference server had concurrent work, so elapsed times do not establish a controlled speedup. Corrected thinking run validation took an additional 69.898 seconds; no-thinking failed application in 0.021 seconds.

Decision authorized by Dani: enable the working staged solution if no-thinking is unsuccessful. New `qwen-goose-staged@1.0.0` routes Qwen through Goose with thinking enabled and 16,000 completion tokens. Complete source/contract/repair packets are preserved. Goose has no tools/extensions and isolated configuration; the existing harness applies edits and retains every original gate. A single bounded NEED continuation or correction is allowed (two total model calls). Partial/unfinished responses are rejected. Existing exact-profile cohorts and retry history stay intact.

The legacy agentic route is drain-only for any saved verification from the job already running at activation. It cannot start another ticket. This avoids stranding the existing job while switching all new eligible Qwen work. No benchmark patch was integrated or deployed.

Validation: 112 adapter, staged runner, profile and control tests passed before activation; after adding drain-only routing, 75 adapter/control tests passed. A real installed-Goose run against a deterministic mock HTTP endpoint sent exactly one request with max_tokens=16000, no tools and the full contract sentinel, and returned correct text/token telemetry (`production-adapter-wire-check.json`). The new profile plus baseline and all enabled profiles validate. Validating every experimental profile also encounters the pre-existing unqualified Nemotron profile; production validation excludes it.

Artifacts: `staged.timing.json`, `usage.json`, `staged.validation.json`, `request-settings.json`, `results.json`, and the complete raw event/request logs. The comparison thinking run is in `../staged-corrected-provider/`.
