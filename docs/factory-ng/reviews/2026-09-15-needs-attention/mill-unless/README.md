# Deep Spawn recovery

The reviewed worker failed compilation by treating Zone pointers as slices. Its
proposal also forced milling and tested ETB instead of the requested own upkeep.
`rejected-response.txt` retains that evidence; `ticket.json` binds the original
TicketSpec and failed receipt hashes.

The correction registers `sacrifice_self_unless_mill`, uses the existing named
option choice and Mill APIs, and sacrifices only the same source still controlled
by the payer. An insufficient library cannot pay the whole cost and is left intact.
Tests cover accept/decline, exactly two/short/empty libraries, library changing during
a choice, absent source, wrong player/alternative, mill notification, and own-upkeep
trigger timing. All original candidate gates passed (`gates.json`).

Normal production integration passed and pushed
`d3271e5c644d3b38f384b013daf5237005c8c378`:
`../../../runs/2026-09-15T204924Z-engine-operator-mill-unless-recovery-sep15-v1-1789505364915797394-integration.json`.
Original parent reconciliation uses the normal integration receipt. No deployment.
