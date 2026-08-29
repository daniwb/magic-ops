# Factory NG observation — first bounded Ticket flow

Status: complete observation; no patch applied, no live ticket, commit, or
deployment was created.

## Root TicketSpec

- `ticket:sha256:cd300ae084ecf9dcabc9db8cf82c89dc44ced93dae3a50a4d54c94192fb926e8`
- type: `map`; lifecycle at dispatch: `ready`
- target assertion: `Target player draws two cards.`
- profile: `qwen-prepared-direct@1.0.0`
- guardrails: 200k effective-token target, 500k reflection warning, parser-only
  Skill, harness-owned apply and gates.

## Execution result

The direct profile returned `PARK`, with no edit blocks.

| Counter | Value |
|---|---:|
| Input tokens | 4,401 |
| Output tokens | 419 |
| Cache-read tokens | 121 |
| Cache-write tokens | 0 |
| Effective tokens (`input + output`) | 4,820 |

The result is within the normal target. It did not consume an agentic loop or
perform repository mutation.

## Diagnosis

The packet demonstrated a target-capable **overlay path**, but did not include
the exact parser function/rule to extend, the canonical Map tuple that the
converter accepts for a chosen player, or the focused test shape. A subsequent
deterministic source check found that current `reparse.py` explicitly refuses
`target player` and current `converter.go` does not lift a draw target into
`SpellTargetType`. The model therefore refused to invent a representation that
might draw for the controller instead of the selected player. Classify this as
`ticket_contract` plus `evidence_or_index`, not `model_profile`.

## Linked child work (proposal, not a live ticket)

`discovery:evidence-pack-targeted-player-draw-v1` is the first child of the
root TicketSpec. Its bounded output is a refreshed execution packet containing:

1. the exact `p_draw` parser locus and adjacent negative cases;
2. the canonical Map/target representation and converter path; and
3. the minimal parser and Engine-facing test expectations.

No implementation work belongs in this child. The refreshed packet must then
split the work into an Engine converter child followed by a Map child; see
[`tickets/first-targeted-draw-dag.md`](../tickets/first-targeted-draw-dag.md).
This preserves a truthful dependency graph instead of hiding a cross-layer
change inside a misleading Map ticket.
