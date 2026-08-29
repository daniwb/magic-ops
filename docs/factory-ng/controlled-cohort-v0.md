# Factory NG controlled cohort v0

Status: five-ticket no-push canary complete. The cohort starts only from
freshly measured, single-root-cause TicketSpecs—not legacy dispatcher rows.

## Selection evidence

- The pinned legacy inventory classifies all 5,310 rows and finds no directly
  dispatchable item: [legacy reconciliation](legacy-backlog-reconciliation-v1.md).
- The sole atomic-looking old sweep, `legacy:3967`, was remeasured across
  18,612 review cards. Its 14 `loyalty_body:choose` members span incompatible
  behaviors, so it is explicitly split-required:
  [evidence TicketSpec](tickets/evidence-loyalty-body-choose-v1.json).

## The first safe cohort

1. One newly produced atomic TicketSpec runs supervised in an isolated clone.
2. Five separate, evidence-complete TicketSpecs run as a no-push canary; each
   gets its own model-specific profile, receipt, scope gate, and telemetry.
3. Only accepted canary proposals are presented for an explicit integration
   decision. No automatic commit, live-ticket mutation, deploy, or refactor is
   part of this cohort.

The source-changing cohort now contains one atomic, observation-only Map
candidate produced from current ground truth:
[`map.static-condition-gained-life-pump/v1`](tickets/map-static-condition-gained-life-pump-v1.json).
It covers only Tenured Concocter and Ulna Alley Shopkeep's identical
`you gained life this turn` condition, which has an existing runtime
representation. Qwen prepared-direct changed only the allowed parser and
focused-test paths in a disposable clone; the pinned remeasurement is zero.
See the [observation receipt](runs/2026-08-29-map-static-condition-gained-life-pump-v1-qwen.json)
and [local-only integration receipt](runs/2026-08-29-map-static-condition-gained-life-pump-integration-v1.json).
It is not pushed or deployed. This preserves the protection against
renaming a partial mixed-bundle patch as production progress.

## Supervised first decision

[`cohort-loyalty-direction-choice-v1`](tickets/cohort-loyalty-direction-choice-v1.json)
is a zero-write capability-decision ticket over the two directional-choice
cards. Qwen prepared-direct returned `NEEDS_PRIMITIVE` in 784 effective tokens
with no edit block and no source mutation; the full receipt is
[`2026-08-28-cohort-loyalty-direction-choice-v1.json`](runs/2026-08-28-cohort-loyalty-direction-choice-v1.json).
This is a successful park: no model was allowed to pretend generic targeting
implements player-order direction.

## Five-ticket canary outcome

All five independent capability-decision tickets returned `NEEDS_PRIMITIVE`,
with no edit block or source mutation. The four additional families were modal
choice (524 effective tokens), named-card choice (552), chosen-target delayed
effect (551), and cross-zone artifact choice (532). These are useful distinct
Engine gaps, not retryable Map work; each has an immutable receipt in
[`runs/`](runs/). The canary therefore passes its safety criterion: uncertain
work parks cheaply and visibly instead of producing a plausible patch.
