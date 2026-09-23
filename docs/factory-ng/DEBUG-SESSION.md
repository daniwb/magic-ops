# Factory NG debug session — the data, the wire out, the response back

Added 2026-09-22. Answers three questions without disturbing the running
factory: what Python produces, what leaves the box, and what comes back.

## 1. Where the boundary actually is

The Factory does not talk to a bespoke server. Every model interaction is one
short-lived process:

```
producer (Python)          TicketSpec JSON          docs/factory-ng/tickets/*.json
      |
      v
factory-ng-run-{engine,map}-ticket.py     one attempt, in an isolated /tmp/factory-ng-* clone
      |  engine-pipeline-pack.py / map-ticket-spec-pack.py
      |  + harness contract/vocabulary/evidence sections
      v
   packet (the prompt)  ................................ docs/factory-ng/runs/<stem>.packet.txt
      |  stdin
      v
scripts/model_call.py  <-- THE WIRE BOUNDARY
      |  prompt in on stdin, answer out on stdout, `tokens: in= out= cache_r= cache_w=` on stderr
      +-- claude / claude-agentic ......... `claude -p` CLI subprocess
      +-- codex ......................... `codex exec --json` subprocess
      +-- goose-*-staged ................ goose subprocess
      +-- openrouter .................... direct HTTPS POST to openrouter.ai
      +-- *-agentic ..................... subprocess + card-knowledge MCP (127.0.0.1:4103)
      v
raw provider response ................................. docs/factory-ng/runs/<stem>.raw.json
      |
      v
apply -> candidate gate -> focused gates -> receipt ..... docs/factory-ng/runs/<stem>.json
```

Because the boundary is a process with stdin/stdout, it can be observed without
touching the controller, the queue, or any lock.

## 2. What is already retained (no switch needed)

`docs/factory-ng/runs/` keeps one set of artifacts per attempt. All share a
stem, with the phase embedded in the suffix:

| Artifact | Content |
|---|---|
| `<stem>.packet.txt` | the complete prompt: ticket contract, capability spec, evidence, code regions, output format |
| `<stem>.raw.json` | the raw provider payload (claude CLI envelope, OpenRouter JSON, or `{"provider_error": …}`) |
| `<stem>.continuation.*` | the bounded NEED continuation round |
| `<stem>.investigation.*` | the read-only evidence-investigation round |
| `<stem>.gate-repair.*` / `<stem>.repair.*` | repair rounds after a gate failure |
| `<stem>.lookup.jsonl` | card-knowledge MCP lookups made during the attempt |
| `<stem>.context.txt` | context pack the harness assembled |
| `<stem>.json` | the immutable receipt: outcome, telemetry, gates, next action |

`/tmp/orch/knowledge-lookups.jsonl` accumulates every knowledge-service query
across all workers.

## 3. The wire tap (what the retained files never held)

`scripts/factory_ng_wire_tap.py` records the pieces that were previously
invisible: the **exact provider argv** (flags, timeouts, appended system
prompt), the **byte-exact request** with its SHA-256, and the **whole round
trip under one `call_id`**.

How it hooks in, without changing behaviour:

* `model_call.py` reads the tap switch at start-up. Off means the code path is
  untouched.
* On, it tees stdin, records the request, and replays the identical bytes to
  whichever engine runs — so no engine needed modification.
* `subprocess.run` is wrapped for the life of the call to capture argv, then
  restored in a `finally` so nothing leaks.
* `save_raw()` — already called by every engine with the provider payload —
  mirrors that payload into the tap.
* OpenRouter builds its request in-process, so its exact JSON body is recorded
  as `http_request`. The `Authorization` header and the API key are never
  recorded.
* A broken tap disables itself rather than taking a worker down.

### Switch

`state/factory-ng-wire-tap.json` (gitignored). Re-read by every new
`model_call.py`, so it takes effect on the next call with **no controller
restart**.

```json
{"enabled": true,
 "started_at": "2026-09-22T19:41:36Z",
 "expires_at": "2026-09-22T21:41:36Z",
 "dir": "/…/magic-ops/state/wire-tap",
 "max_record_bytes": 400000,
 "max_total_bytes": 200000000,
 "ticket": null}
```

* `expires_at` is a hard stop — the tap cannot be left on by accident.
* `max_total_bytes` auto-disables once the tap directory reaches the budget.
* `ticket` narrows recording to one ticket (matches `KB_TICKET`/`TICKET`).

### Records

`state/wire-tap/wire-YYYYMMDD.jsonl`, one JSON object per line:

| event | fields |
|---|---|
| `request` | `prompt`, `prompt_bytes`, `prompt_sha256` |
| `spawn` | `argv` — the literal provider command line |
| `http_request` | `url`, `body` — OpenRouter only, no credentials |
| `response` | `raw`, `raw_bytes` |
| `summary` | `exit`, `duration_ms`, `spawns`, `stdout_bytes`, `answer` |

Every record carries `ts`, `pid`, `engine`, `model`, `tier`, `phase`
(`initial`/`continuation`/`investigation`/`repair`/`correction`), `ticket`,
and `call_id`.

## 4. Driving a session

```bash
# what is running, tap state, the last few round trips
python3 scripts/factory-ng-debug-session.py status

# live correlated stream: REQUEST / RESPONSE / KNOWLEDGE / RECEIPT
python3 scripts/factory-ng-debug-session.py watch --follow

# one round trip in full
python3 scripts/factory-ng-debug-session.py show --stem <substring> --full
python3 scripts/factory-ng-debug-session.py show --lookups     # + KB queries

# produce the prompt only — free, no model, no quota
python3 scripts/factory-ng-debug-session.py pack \
    --ticket docs/factory-ng/tickets/<ticket>.json --out /tmp/packet.txt
```

`pack` runs the real packer against the canonical checkout read-only and adds
the same harness sections the runner adds (ticket contract, vocabulary handoff,
compilation notice, staged evidence instructions), so what it prints is what
would be sent.

```bash
# one live round trip, throwaway hardlinked clone — SPENDS QUOTA
python3 scripts/factory-ng-debug-session.py call \
    --ticket docs/factory-ng/tickets/<ticket>.json \
    --engine claude --model claude-sonnet-5 --yes
```

`call` never applies a patch, never runs a gate, never writes a receipt, never
touches the canonical checkout, and never enters the controller's queue. It
clones with hardlinks, so it is cheap on disk and time.

## 5. Recipes

**"What exactly did we send?"**
`watch --follow` to catch the stem, then `show --stem … --full`. For the
literal command line: `factory_ng_wire_tap.py --show <call_id> --part argv`.

**"Why did this park?"**
`show --stem …` prints the receipt: `outcome`, `failure_category`,
`next_action`, and per-call telemetry. Cross-check the answer text against the
packet's `required_behavior` list.

**"Did the provider actually answer, or did we lose it?"**
`show` prints the parsed response kind (`claude-cli`, `openrouter`,
`provider_error`), stop reason, and token counts. `raw.json` retains the
untouched payload; the tap retains the same bytes plus exit code and wall time.

**"Is the tap costing anything?"**
`factory_ng_wire_tap.py --status` shows bytes stored against the budget.
Records are clipped head-and-tail past `max_record_bytes`.

## 6. Honest limits

* For the `claude`, `codex` and `goose` engines the HTTPS body is assembled
  inside the CLI. The tap captures the CLI argv plus the exact stdin bytes,
  which fully determine the request, but not the TLS-layer bytes.
* `--part request` and `--part response` are clipped by `max_record_bytes`;
  `--full` on `show` reads the untruncated `packet.txt` / `raw.json` instead.
* The tap is per-process. It records calls made after the switch flips; calls
  already in flight when it is turned on are not retroactively captured.
* Nothing here changes gates, acceptance, integration, or deployment authority.
  It observes.

## 7. Tests

`scripts/test_factory_ng_wire_tap.py` — 16 tests covering: inert when off,
correlated records when on, stdin replay fidelity, argv capture, `subprocess.run`
restoration, expiry, disk-budget auto-disable, ticket filtering, non-fatal
failure behaviour, and clipping.
