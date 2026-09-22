# Goose / local Qwen harness comparison — 2026-09-20

Requested model: `halogen-qwen3.8-flash-next`; provider: `strix_halo`; Goose 1.51.0.

## Results

| Mode | Goose runtime | External validation | Model requests | Tool calls | Input tokens | Output tokens | Total tokens | Reported cached input | Outcome |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Staged | 213.864 s (3m34s) | 50.076 s | 1 | 0 | 7,270 | 8,192 | 15,462 | Not reported | Response cut off mid-test; required-test gate failed |
| Agentic | 1,143.215 s (19m03s) | 0.011 s | 25 | 48 | 981,290 | 42,853 | 1,024,143 | 905,426 | Turn limit; no file changes; scope gate failed |

Neither produced an acceptable candidate. Agentic took 5.35 times the Goose
runtime and used 66.24 times the aggregate reported tokens, but the latter
includes extensive prompt-cache reuse. Its reported noncached input was 75,864
tokens. Staged cache reuse is unavailable, not proven zero. Validation stopped at
the first real failure; later ticket gates and full production integration were
not run. End-to-end measured runtime plus validation: 263.940 s staged,
1,143.226 s agentic. Setup/evidence preparation is excluded from both.

The agentic tool calls were 46 shell calls (source inspection), one tree call,
and one unparseable tool call. Goose returned an error for the malformed call
and continued rather than crashing. It performed no write/edit call, and its
checkout remained unchanged. Its final CLI message reports the maximum action
limit. The process exit code was zero, which is not task success.

The staged response had the correct named registry file and public registration,
but ended halfway through the test function. The Factory applier accepted complete
blocks and omitted the incomplete new-test block. The original named-test gate
correctly rejected this: no passing test matched its mandatory selector.

For context only, the original overnight adapter attempt on this same ticket took
138.438 s of model time, reporting 41,573 uncached input + 538,501 cached input and
3,856 output tokens, and failed on invalid generated Go syntax. The historical
run had different prompts, reasoning settings and environment, so it is not a
controlled third arm of this comparison.

## Interpretation and next experiment

This test does not justify replacing the production harness with default Goose.
It demonstrates robust tool-error handling, but the staged path needs a verified
output-limit mapping, and the agentic path needs a tighter source-investigation
budget and an explicit transition to implementation. Reasoning must be configured
consistently before comparing against the old adapter. Retest with the complete
contract and unchanged gates after those setup issues are addressed. One task is
insufficient to rank general model capability or project-wide activation throughput.

Canonical source was clean at completion. Factory worker routing, limits, and
Goose's installed provider configuration were not changed.

## Protocol

Two sequential isolated runs of the same historical Engine ticket,
`ticket:engine.auto-freeze-until-next-untap-7b6fc522b0/v1`, on its exact original
revision `fcb60f31cda3285216ac60206c56cc320b8e8b16`. Both received the same
complete behavior contract, scope, original gate list, and selected source
excerpts. The original TicketSpec is retained in `ticket.json`.

- Staged: Goose with `--no-profile`, no tools, one model request, return strict edit blocks; the existing Factory patch applier applies the response.
- Agentic: Goose with `--no-profile --with-builtin developer`, up to 25 turns, source exploration and direct edits in a disposable checkout. The external evaluator owns testing.
- Both: temperature 0.7; configured response limit 16,000; context limit 131,072; provider configuration copied into an isolated `GOOSE_PATH_ROOT`. Existing Goose/global Factory configuration is unchanged.
- No live-ticket dispatch, canonical edits, integration, push, or deployment. Clone remotes removed.
- Validation uses Factory's existing `check_candidate`: scope, formatting, vocabulary handoff when applicable, and every original TicketSpec gate until first failure. No full production integration was requested or performed.
- No model correction round after validation in either run.

This is one paired case, not a general model-quality benchmark. The source already
has related freeze/untap behavior, so reuse with a discriminating test is explicitly
valid. The modes differ in tool access and patch delivery as well as turn budget.
Runtime is measured from CLI start to exit, separately from external validation.
Input token totals include repeated context across requests; reported cache reads
are a subset, not extra input tokens. Output counts are provider-reported and include
reasoning where the provider counts it; no independently measured reasoning split.

## Setup observations

Initial recipe-loading attempts failed locally before creating model sessions;
these are retained as `staged-provider-preflight*` artifacts and excluded from
benchmark time/tokens. The first actual staged session is named
`factory-benchmark-staged-provider-preflight5`; `staged.*` contains its results.
The final harness uses Goose's CLI instruction-file interface, not recipes.

The installed custom provider is configured with `engine: ollama`, but Goose's
retained request uses a chat-completions-shaped body. It sends the configured output
limit as `options.num_predict: 16000`, not `max_tokens`. The staged response ends
mid-test at exactly 8,192 output tokens. This strongly suggests that the endpoint's
output cap was not overridden; it is not evidence of a semantic inability.

Goose permits reasoning with this configuration; the old Qwen adapter explicitly
disables it. An old-adapter comparison is therefore contextual, not controlled.

The first evaluator invocation lacked Go on its shell PATH; the evaluator was
corrected to use the host's installed `/data/magic-stack/toolchain/go/bin` before
measured validation. No model output was repaired manually.

## Evidence

- `*.prompt.txt`: complete prompts.
- `*.timing.json`: commands, nonsecret environment and CLI timing.
- `*.messages.json`, `*.stdout.jsonl`, `*.stderr.log`: retained conversations and CLI output.
- `usage.json`: Goose session and per-request usage ledger.
- `*.validation.json`, `*.patch`: gate results and generated changes.
- `run_trial.py`, `validate_trial.py`, `summarize_usage.py`: invocation and evaluation scripts; require the isolated checkouts and config described above.

CLI options were checked against the installed `goose run --help` and the
[official Goose CLI documentation](https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/goose-cli-commands.md).

## Follow-up: token cutoff confirmed

The subsequent [token-limit audit](token-limit-audit/README.md) proved the
8192 cutoff is the Halogen default caused by the Ollama/OpenAI wire-field
mismatch. The installed Goose binary and running Halogen request parser were
checked independently. Effective per-request budget was 8192 in both arms.

## Corrected-provider staged retest

The [follow-up staged run](staged-corrected-provider/README.md) requested 16,000
correctly, produced a complete 15,218-token response, and passed every original
TicketSpec gate, including full game/cards package tests. Generation 14m20s,
validation 1m10s; server contention prevents a clean speed comparison.
