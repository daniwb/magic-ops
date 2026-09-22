# Goose + card-knowledge database tools — 2026-09-20

**Conclusion: the integration works; discovery quality is useful but not uniformly reliable.** Qwen successfully invoked all four existing read-only MCP tools through Goose, followed search results to exact source declarations, and generally distinguished candidate evidence from verified code. All 10 structured source citations across the three final answers matched declarations actually read (four + one + five). However, the first general-engine search selected a specialized effect, and even the improved run did not verify the dispatch link. Keep this as an evaluated evidence-gathering option; production remains the existing no-tools staged Goose profile.

## Reproducible integration

The harness is `run_trial.py`. It creates isolated configuration and a disposable clone, removes the remote, pins model/provider, and runs Goose with the clone as its working directory:

```text
goose run --no-profile --with-extension 'card-knowledge:python3 /absolute/path/to/magic-ops/scripts/kb-mcp-server.py' --instructions PROMPT --max-turns 10 --output-format stream-json --stats
```

Only `find_capability`, `similar_handlers`, `check_capability`, and `read_source` were advertised on the actual model requests. No developer/shell/edit extension was present. The old `kb-mcp-config.json` refers to an absent `/opt/development/...` path on this host; the experiment resolves the actual server path from this checkout instead of reusing that stale command. No production config was changed.

Provider `strix_halo`, model `halogen-qwen3.8-flash-next`, Goose 1.51.0, OpenAI-compatible transport, thinking enabled, temperature 0.2, 6,000 tokens per model request, at most 10 model turns, 1,200-second process timeout. The prompt requested at most nine tool calls; **this was advisory, not a hard tool limit**. Production staged generation separately retains its 16,000-token limit. All three clones and the index used revision `f8d04f3ce658cafd9fc05a92edd2960e016e36d9`.

## Results

| Trial | Elapsed | Input tokens | Output tokens | Model requests | Tool calls | Assessment |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| General engine search | 157.276 s | 17,108 | 3,053 | 5 | 9 | Partial: source verified, specialized effect selected |
| Primitive, executor, handler, capability | 142.746 s | 15,186 | 2,816 | 5 | 8 | Executor found and verified; unresolved registration/handler clearly qualified |
| Same engine task, clearer harness guidance | 148.657 s | 26,654 | 2,863 | 6 | 11 | General draw implementation found; dispatch proof still incomplete; prompt budget exceeded |

Totals aggregate every model request, including reasoning in output. Cache counters were not reported by the provider (Goose's completion event shows zero; do not interpret this as evidence of no server-side caching). These are single trials on shared inference hardware. The first two overlapped; this is not a controlled throughput comparison.

## What changed the result

The refined prompt explains that search is exact-symbol/normalized AND-word matching, encourages short queries and simplification when results are specialized, and states that `read_source` reads the pinned checkout directly. It includes no target symbol IDs or file paths. With that guidance, Qwen found and read `GameState.executeDrawEffect`, `DrawCardsWithEvent`, `DrawCardWithEvent`, `Player.DrawCard`, and `Zone.DrawCard`. It corrected the earlier source-provenance misunderstanding. This is evidence that harness guidance matters, not proof of general reliability from one improved run.

The independent audit also found the plain dispatch arm `ExecuteAbilityEffect#case:draw`, which delegates to `executeDrawEffect` (`expected-general-draw.json`). Neither engine trial read that arm. We do not score either run as fully verified end-to-end dispatch reasoning.

## Remaining implementation gaps

- Some primitive/handler index rows have file paths but no resolvable symbol IDs. Existing `read_source(symbol_id)` cannot directly inspect those rows; Qwen correctly followed a primitive name to its engine executor instead.
- `check_capability` covers event constants/converter labels. It reported a miss for `put_counter_and_draw_card` despite the verified executor. Qwen correctly explained the coverage mismatch.
- Long natural-language queries and category filters can hide relevant functions. The initial engine run found a compound effect instead of the general draw effect.
- A prompt tool budget is not enforced by `--max-turns`; multiple calls can occur in one turn. The refined run made 11 calls and claimed 9. Any production evidence phase needs an enforced tool/cost budget and harness-counted telemetry.

Recommendation: use this integration as the basis for a bounded read-only evidence phase, with short-query guidance, explicit checkout provenance and a hard tool budget. Improve source access for non-symbol index rows before treating it as a complete replacement for code discovery. Do not infer missing Engine capability from a database miss. Production tool access has not been enabled by this experiment.

## Verification and artifacts

`verify_trials.py` checks every retrieved source excerpt byte-for-byte against its isolated checkout, whole-file SHA-256, revision, declaration lines, every structured final-answer source citation, exact advertised tool set, and clean Git state. It fails on mismatched or fabricated structured source citations. All these checks passed; they do not establish semantic completeness, which is separately reviewed in `reviewed-results.json`.

The directory retains prompts, per-call database traces, Goose session messages, raw request logs, aggregate usage, elapsed times, final answers, independent expected-dispatch evidence, settings, automated verification and this review. Repeat a trial under a new name to preserve earlier artifacts. No card patch, model workspace edits, commit, integration, gate bypass or deployment occurred.
