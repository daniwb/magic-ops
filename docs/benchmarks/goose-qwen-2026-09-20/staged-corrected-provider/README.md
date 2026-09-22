# Corrected-provider staged retest

Same historical ticket, source revision and byte-identical staged prompt as the
[parent benchmark](../README.md). A fresh isolated clone uses revision
`fcb60f31cda3285216ac60206c56cc320b8e8b16`. Goose 1.51.0 uses model
`halogen-qwen3.8-flash-next`, provider `strix_halo`, now with `engine: openai`.
The requested output budget remains 16,000, temperature remains 0.7, and the
single no-tools request has no model repair round. Reasoning remains at the
server default, so only the provider wire-format correction is intentional.

`request-settings.json` confirms the live request carries `max_tokens: 16000`.
The corrected installed provider is copied into an isolated Goose config root.
The Factory's original scope/format/vocabulary and ticket gates evaluate the
proposal. No production integration, push, deployment, or live-ticket mutation.

Runtime excludes evidence preparation and external validation, reported separately.
Input/output usage is taken from Goose's per-request provider usage ledger.

## Result: passed all original ticket gates

- One model request; no tools and no repair round.
- Generation: **860.261 seconds (14m20s)**.
- Validation: **69.898 seconds (1m10s)**.
- Combined measured time: **930.159 seconds (15m30s)**.
- Input: **7,273 tokens**; output: **15,218 tokens**; total: **22,491 tokens**.
- Provider cache-read count was unavailable, not proven zero.
- The response ends with the complete final EXPECT line; no 8,192-token cutoff.
- Strict patch application, scope, gofmt, vocabulary registration, named behavior
  test, full `go test ./game ./cards`, and `git diff --check`: **all passed**.

The required test covers a target staying tapped for one untap, clearing the
marker, untapping on the following untap, repeated applications not extending
the duration, an unaffected sibling, and an adjacent plain-tap case.

This confirms the provider correction works in a real staged coding run.
The server handled concurrent requests, so the slower wall time is not a
controlled before/after performance comparison. The default xhigh reasoning
setting was unchanged. Raw usage and exact validation evidence are retained.

## Review boundary

This was an isolated harness test, not a production integration. The model added
an additional hash-suffixed freeze primitive instead of reusing equivalent existing
behavior; passing the ticket gates does not establish that this is the best patch
to merge. Its plain-tap check tries several existing effect names, so it provides
weaker coverage than separately asserting each named adjacent path. The generated
patch is preserved unchanged apart from normal harness gofmt; no manual repairs
were used. No full six-shard integration, commit, push, or deployment was performed.
Canonical source was clean after validation.
