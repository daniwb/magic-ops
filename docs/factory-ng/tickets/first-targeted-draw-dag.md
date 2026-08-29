# First Factory Ticket DAG — targeted player draw

Status: evidence child complete; Engine v2 and the bounded Map repair stack accepted for dependent observation.
These are not live dispatcher tickets and authorize no source mutation.

```text
root: targeted-player-draw semantics
  |
  +-- discovery: refresh indexed evidence
  |     (pins current parser + converter + test loci)
  |
  +-- engine: lift a draw ability target into SpellTargetType
  |     (depends on discovery)
  |
  +-- map: emit the canonical chosen-player target for p_draw
  |     (depends on engine)
  |
  +-- verification: remeasure the two original Oracle assertions
        (depends on engine and map)
```

## Ground truth that forced the split

- `scripts/paragraph/reparse.py:1609` explicitly documents that `target
  player` is not representable and returns no Map result for that form.
- `backend/cards/converter.go:2243` constructs a draw `SpellEffect`, but does
  not copy `ability.Target.Filter` into `SpellTargetType` (unlike neighboring
  targeted effects).
- The old TicketSpec's Engine overlay proved the desired eventual behavior,
  not behavior in the current source tree. It cannot make the Map ticket
  independently ready.

## Child contracts

| Child | Layer | Bounded outcome | Model route |
|---|---|---|---|
| `discovery:evidence-pack-targeted-player-draw-v1` | Factory evidence | Current, line-pinned parser/converter/test packet; negative cases included | deterministic code, local AI optional advisory only |
| `engine:draw-target-lifting-v2` | Engine | `draw` converter lifts `ability.Target` to a chosen player target; focused populated-library behavior test | Codex constrained; accepted in an isolated clone ([receipt](../runs/2026-08-28-engine-draw-target-lifting-v2.json)) |
| `map:target-player-draw-v2→v4` | Map | `p_draw` emits only the canonical target form; `target opponent` and referential/each-player negatives remain honest | Qwen prepared-direct exposed its test-interface failure; Codex was host-sandbox-blocked; Claude staged supplied the bounded focused-test repair |
| `verification:target-player-draw-v1` | Verification | Original two assertions accounted for; Comparative Analysis remains explicitly partial because Surge is unrelated | deterministic gates plus fresh review |

The engine and Map children must not be run in parallel: the Map contract
depends on the Engine representation being real. Independent unrelated tickets
may still run in parallel.

The first Engine attempt is closed `gate_failed`; its receipt is in
[`../runs/2026-08-28-engine-adapter-observations.md`](../runs/2026-08-28-engine-adapter-observations.md).
The reissued v2 child added the Go module/test-header evidence and was accepted
in its disposable clone. Its TicketSpec is
[`engine-draw-target-lifting-v2.json`](engine-draw-target-lifting-v2.json) and
its receipt is
[`2026-08-28-engine-draw-target-lifting-v2.json`](../runs/2026-08-28-engine-draw-target-lifting-v2.json).
The Qwen v2 and Codex v3 observations are preserved as failed receipts. The
Claude v4 bounded repair then passed the Map and focused Engine boundary gates
in the same disposable clone; its receipt is
[`2026-08-28-map-target-player-draw-v4.json`](../runs/2026-08-28-map-target-player-draw-v4.json).
This remains observation only, not an integration action. The next child is
verification/reconciliation, not another implementation retry.
