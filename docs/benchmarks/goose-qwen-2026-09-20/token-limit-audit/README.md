# Token-limit root-cause audit — 2026-09-20

## Conclusion

The staged run requested 16,000 tokens. The installed Goose custom provider
`~/.config/goose/custom_providers/strix_halo.json` selected `engine: ollama`.
Goose 1.51.0 consequently removed the top-level token budget and sent
`options.num_predict: 16000` to `/v1/chat/completions`. Halogen 0.11.8 does not
recognize that Ollama-specific field, so its request model silently ignored it
and applied its default of 8,192. The server generated 8,192 tokens; Goose did
not strip an originally longer answer after receiving it.

## Evidence chain

1. `../staged.timing.json`: the benchmark explicitly set `GOOSE_MAX_TOKENS=16000`.
2. `../staged.llm.jsonl`: Goose model config contains `max_tokens: 16000`, but
   its HTTP request contains only `options.num_predict: 16000`, with no
   top-level `max_tokens`, `max_completion_tokens`, or `max_output_tokens`.
3. [Goose v1.51.0 Ollama adapter](https://github.com/aaif-goose/goose/blob/v1.51.0/crates/goose-providers/src/ollama.rs#L248)
   deliberately performs this translation; it is expected for an Ollama provider.
4. `halogen-health.json`: live server reports default 8,192, hard cap 65,536,
   and recognizes the three top-level budget aliases above. This is not a
   hard model limit of 8,192 or a shortage of context space.
5. `halogen-budget-parser-proof.json`: imported the actual running image's
   `ChatReq` request model without starting inference. No budget -> 8,192;
   nested Ollama budget 16,000 -> 8,192; each supported top-level alias
   set to 16,000 -> 16,000.
6. `halogen-staged-window.log`: the original staged server request reports
   prompt 7,270 and generation 8,192, matching Goose's recorded usage.
7. `wire-probe-summary.json`: the installed Goose binary was exercised
   against a local fake HTTP endpoint in two fresh isolated config roots.
   `engine: ollama` emits nested `options.num_predict: 16000`;
   `engine: openai` emits top-level `max_tokens: 16000`. Both use the same
   `/v1/chat/completions` endpoint. The probe performs no model inference.

The server source is `/halogen/tools/serve_api.py` inside container `halogen`:
CHAT_MAX_TOKENS at line 1530, ChatReq and alias resolution at 1621–1722,
reasoning answer reserve around 3991, and hard-cap validation around 4018.
Unknown fields follow Pydantic's default ignore behavior; `options` is not a
recognized ChatReq field. Server requests exceeding the real 65,536 ceiling
are rejected, not silently reduced to 8,192.

## Reasoning implications

Goose sent no thinking control. Halogen reports default reasoning effort
`xhigh`, and reasoning consumes the same total generation budget as final text.
At 8,192 the default answer reserve is 1,228 tokens; at 16,000 it is 2,400.
This helps explain why a response that spent much of its budget reasoning ran
out midway through source code. It is independent of the fixed token-field
mismatch. The same mismatch affected every agentic model request as well;
the agentic total can exceed 8,192 because it sums 25 separate requests.

## Verified correction, not applied to installed settings

Change just `engine` from `ollama` to `openai` in the installed custom provider.
Keep provider name `strix_halo`, model `halogen-qwen3.8-flash-next`, the existing
base URL, and `GOOSE_MAX_TOKENS=16000`. The root base URL works: the capture test
verified Goose derives `/v1/chat/completions` for either engine. A complete
proposed config is retained as `strix_halo.proposed.json`.

This selects the OpenAI-compatible wire protocol; it does not route requests
to OpenAI or change the served local model. Raising GOOSE_MAX_TOKENS alone
while retaining the Ollama engine would repeat the mismatch.

No installed Goose configuration, model-server setting, Factory policy, or
canonical source was changed. The prior benchmark must be read as using an
effective 8,192-token per-request budget, not the requested 16,000. A corrected
coding rerun has not been performed as part of this diagnostic audit.
