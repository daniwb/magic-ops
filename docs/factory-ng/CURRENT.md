# Factory NG — Durable Handoff

Last updated: 2026-08-29  
Status: Factory NG is now in controlled rollout. The staged, non-agentic
pre-NG execution core is retained; TicketSpecs, profiles, receipts, and the
single dashboard are the thin control plane around it. No legacy-ticket
mutation, push, or deploy is automatic.

## Current phase status — this section supersedes older proposed/governance wording below

| Phase | State | Grounded result |
|---|---|---|
| 0 — inventory | complete | The read-only reconciliation classifies all 5,310 legacy rows; none enters the NG queue directly. |
| 1 — TicketSpec DAG | complete | Versioned typed tickets, parent links, source pinning, scope, Skills, and gates are in use. |
| 2 — producer | complete for the first atomic class | The narrow deterministic registry-bridge producer refuses duplicate, already-registered, and no-dispatcher cases. New classes are added only when a real candidate needs them. |
| 3 — Skills/adapters | complete | Model-specific adapters wrap the proven staged flow; they are not a shared agentic prompt loop. |
| 4 — telemetry/dashboard | complete | One receipt-derived dashboard shows ticket DAG, outcomes, input/output/cache telemetry, and integrations. New staged runs can retain each raw response for the receipt. |
| 5 — golden Map flow | complete | `target-player-draw` passed the real Map→converter→Engine flow and is locally committed, not pushed or deployed. |
| 6 — Engine flow | complete | `switch_pt` now has a full accepted Map→Engine observation trace: 17 pinned misses remeasure to zero in a disposable composition clone. |
| 7 — legacy backlog | complete | Historical tickets remain provenance only until freshly compiled from ground truth. |
| 8 — controlled rollout | initial rollout complete | The five-ticket no-push Qwen canary, the supervised Engine bridge trace, and one freshly produced two-card Map ticket have all completed in isolated clones. The small supervised queue is active; shared-source integration remains an explicit action. |

### Next small action

Keep the deterministic producer as the only entry to the small queue. The
next ready TicketSpec runs through its compatible staged adapter in an
isolated clone and gets one receipt; accepted clone patches are then presented
for a separate integration decision. Do not make governance review, refactor
analysis, or new infrastructure prerequisites for that work.

### Latest complete trace

`ticket:engine.switch-pt-registry-bridge/v3` used the restored Claude staged
adapter: compact indexed pack → one bounded `NEED` continuation → constrained
two-file patch → deterministic build/focused/six-shard gates. Its receipt is
[`runs/2026-08-29-engine-switch-pt-registry-bridge-v3.json`](runs/2026-08-29-engine-switch-pt-registry-bridge-v3.json).
Composed with the accepted `map.switch-pt/v5` patch, all 17 pinned
`verb_unmapped:switch_pt` cards remeasure to zero. The canonical `openmagic`
checkout remains clean, unpushed, and undeployed.

The first newly produced queue ticket is
[`ticket:map.static-condition-gained-life-pump/v1`](tickets/map-static-condition-gained-life-pump-v1.json).
Its deterministic producer isolated the exact two cards whose parser misses
only `This creature gets +2/+0 as long as you gained life this turn.` while
the runtime already supports `happened/you_gained_life`. Qwen prepared-direct
made the one-line parser mapping and a three-case negative-boundary test in
one call (6,584 input, 374 output, 202 cached tokens). The two-card pinned
remeasurement is zero; see its
[`receipt`](runs/2026-08-29-map-static-condition-gained-life-pump-v1-qwen.json).
The accepted clone commit `d9e5318d` has now been integrated locally as
`8dd5e065`, after the same focused source test and pinned remeasurement gates;
see the [integration receipt](runs/2026-08-29-map-static-condition-gained-life-pump-integration-v1.json).
It is not pushed or deployed.

Read this file after the repository startup protocol in `AGENTS.md`. It is the
authoritative resumption point for Factory NG work; do not reconstruct status
from an old chat or assume that proposed documents are live behavior.

## User decisions that are binding

- Preserve the old staged pipeline as the execution core.  Factory NG is a
  thin control plane around it, not a generic replacement agent.
- A Ticket is model-neutral; its execution packet/profile is model-specific.
  Do not give every model the same prompt, tool loop, or executable.
- Models operate **in parallel on separate compatible child tickets**.  Give
  the same ticket to several models only for a deliberate benchmark or blind
  review.
- `200k` effective tokens is an ordinary target and `500k` creates a warning
  and reflection; neither is a hard stop.
- One dashboard, raw input/output/cache-read/cache-write/reasoning telemetry,
  ticket DAG, and immutable receipts are required.
- Contract changes—not ordinary refactors—require Sol or Opus review.  High
  impact contract changes require independent Sol and Opus approval.
- Refactors are small, behavior-preserving tickets. The simple nightly
  inventory is read-only and creates proposals, not patches or live tickets;
  it is background work, not the current Factory startup path.
- **Pareto simplicity is binding:** this is a hobby project, not an audit
  program. Prefer the smallest design that makes behavior understandable and
  testable; do not add governance machinery merely to cover theoretical edge
  cases. Each ticket/run has one immutable TicketSpec JSON file. Its receipts
  record the relative path and SHA-256 and derive required gates from that
  file—no ticket database and no duplicated full TicketSpec blobs in receipts.
- **Bootstrap boundary:** the externally stored Factory trust root is a
  deliberate, operator-managed bootstrap anchor. NG v1 does not implement
  trust-key rotation or automatic activation of replacement trust material.
  Any such change needs a separate, explicit operator decision; do not expand
  this baseline with an audit-style rotation system merely to close that edge.

## Proven now

### Ticket/execution shape

- TicketSpec v1 and the golden Map→converter→Engine flow were accepted.  The
  old pipeline's evidence pack, symbol lookup, bounded `NEED`, block applier,
  and deterministic gates remain the core.
- The existing card-knowledge SQLite FTS index is the required grounding step.
  It now also indexes compact `backend/game` function signatures and leading
  docs as `engine` entries, alongside primitive/helper/handler entries. A
  preparation harness must query this index before extracting named interfaces;
  it must not send broad raw source files to a worker. The running service will
  expose the new kind after its ordinary next restart/reindex; no lane was
  restarted for this change. Regression:
  `python3 scripts/test_card_knowledge_service.py`.
- Model Profile Contract v1:
  [`model-profile-contract-v1.md`](model-profile-contract-v1.md).
- Model profiles are separate executables/workflows, not prompt variants:
  [`model-profiles/v1/`](model-profiles/v1/).

### Model benchmark v2

The benchmark was a known frozen target-player-draw Map ticket with a
harness-owned Map→converter→Engine boundary test. It is a proof of workflow
shape, not permanent production routing. Full receipts and methodology:
[`../benchmarks/model-routing-v2/`](../benchmarks/model-routing-v2/).

Accepted results:

| Profile | Quality | Model-call time | Provider input | Output |
|---|---:|---:|---:|---:|
| Qwen prepared-direct | 100/100 | 132.813 s | 12,513 | 686 |
| Qwen prepared-agentic | 100/100 | 724.683 s | 773,819 | 2,531 |
| Codex Luna constrained | 100/100 | 53.358 s | 53,846 | 2,170 |
| Codex Terra constrained | 100/100 | 34.535 s | 35,434 | 1,149 |
| Codex Sol constrained | 100/100 | 23.395 s | 28,922 | 890 |
| Claude Sonnet staged | 100/100 | 83.461 s | 15,375 | 8,057 |
| Claude Opus staged | 100/100 | 63.230 s | 2,749 | 5,177 |
| Claude Haiku staged | 65/100 | 68.051 s | 6,403 | 6,164 |

Qwen direct made one bounded `NEED`, then patched successfully. It has no
agentic tools and keeps Qwen thinking disabled. It is the first local profile
for evidence-complete small Map work; Qwen agentic is an escalation for truly
incomplete evidence. Do **not** claim Qwen direct is Map-only: direct Engine
work has not been benchmarked yet.

## Proposed, not live

- [Change provenance and RCA contract](change-provenance-and-rca-contract-v1.md)
  plus schemas. It defines harness-written commit trailers such as ticket,
  attempt, profile/model, evidence, Skill, gates, review, and provenance
  digests. Provenance is not causal blame.
- Contract review is still required before this becomes binding:
  - one fresh Sol **or** Opus review for a normal contract amendment;
  - independent Sol **and** Opus review for cross-project identity,
    acceptance semantics, integration authority, or token/cost accounting.
- Refactor Inventory v0 is a manually runnable, read-only code indexer. It is
  not scheduled and does not create tickets, patches, deployments, or a live
  event store.

## Contract-review status (2026-08-28)

The governance package remains **proposed** until a fresh Sol and an
independent Opus acceptance cover the same package digest. The local
operator-controlled trust root lives outside this repo at
`/opt/development/factory-ng-trust`.

The last concrete review findings are implemented and covered by fixtures:
accepted provenance has a full harness attestation and is bound to its
execution receipt; registered local adapter implementations are mechanically
classified as high-impact Factory changes. Do not silently promote these draft
contracts into production integration before the independent approvals.

The previous Sol review is retained at
[`reviews/contract-v1/review-34-sol.raw.jsonl`](reviews/contract-v1/review-34-sol.raw.jsonl).
It rejected permissive `sha256:` labels. The proposal now requires exact
64-lowercase-hex content addresses (including ticket/attempt/review prefixes),
regenerates the signed valid receipts, recomputes receipt/manifest identities
where their canonical artifacts are present, and adds short/non-hex/trailing,
gate-content-mismatch, and review-subject-replay counterexamples. A fresh Sol
review of package `sha256:c3bada89bcde0e673c694101a5568fa58209109c4612821df3c057f19b3358d9`
was rejected because the review package omitted fixtures loaded by its own
deterministic test gate; the finding is retained at
[`reviews/contract-v1/review-35-sol.raw.jsonl`](reviews/contract-v1/review-35-sol.raw.jsonl).
The packer now derives and hash-pins every fixture and the test verifies that
coverage. That package was then rejected because its package-builder was
executed by the gate without being hash-pinned; the finding is retained at
[`reviews/contract-v1/review-36-sol.raw.jsonl`](reviews/contract-v1/review-36-sol.raw.jsonl).
The builder now pins itself alongside every fixture and validator it invokes.
That package was then rejected because independent Sol/Opus wrappers could
reuse one raw review artifact; the finding is retained at
[`reviews/contract-v1/review-37-sol.raw.jsonl`](reviews/contract-v1/review-37-sol.raw.jsonl).
High-impact approvals now require distinct raw-review digests and have a
signed, otherwise-independent duplicate-artifact counterexample. That package
was then rejected because a review subject did not bind the complete signed
execution receipt; the finding is retained at
[`reviews/contract-v1/review-38-sol.raw.jsonl`](reviews/contract-v1/review-38-sol.raw.jsonl).
The review subject now contains the canonical complete receipt digest, with a
signed profile/model replay counterexample. The next fresh Sol review will
cover package
`sha256:75c4508a73a0c9bb0bdde4450f9ffc31c24224e1446ae41e4dfae0290e2211d4`.
Do not reuse any prior acceptance; Opus is requested only if that fresh Sol
review accepts the exact same digest.

### Current acceptance boundary

The latest independent reviews are preserved as
[`review-44-opus.raw.json`](reviews/contract-v1/review-44-opus.raw.json) and
[`review-45-sol.raw.jsonl`](reviews/contract-v1/review-45-sol.raw.jsonl),
with the latter's pinned package manifest at
[`review-45-manifest.json`](reviews/contract-v1/review-45-manifest.json).
They identify a full trust-key rotation/activation protocol as the sole
remaining review demand. Per the binding Pareto/bootstrap decision above, it
is explicitly out of scope for Factory NG v1; governance remains proposed,
not falsely accepted.

Refactor Inventory v0 is implemented and verified read-only at
`docs/factory-ng/refactor-inventory/v0/latest/`: it leaves source status
unchanged and is byte-reproducible on consecutive runs. Review 26 identified the
remaining governance prerequisite: Sol/Opus receipt verification cannot trust
keys or reviewer identities supplied by the proposed repository itself. A
read-only audit found no pre-existing external/previously accepted Factory
trust store in this environment. Do not create one implicitly: an operator
must choose its custody, bootstrap ceremony, and rotation authority. The
operator has now chosen a local bootstrap root at `/opt/development/factory-ng-trust`
(outside this repo, private key mode `0600`); validators use that fixed path
and do not accept an ambient environment override. It is a bootstrap trust
root, not a deployed service.

## Current Doing — Factory start phase

1. Produce the first small, evidence-complete TicketSpec child tickets from a
   pinned Magic ground-truth snapshot. Keep Map and Engine work separate.
2. Compile one selected child through the existing staged core with its chosen
   model profile. This is an **observation-only** run: no live-ticket mutation,
   commit, deploy, or automatic integration.
3. Preserve raw input/output/cache-read/cache-write/reasoning counters,
   gates, scope outcome, and the exact model/profile decision in one run
   summary. Use it to decide the next Ticket, not to infer permanent routing.
4. After the first flow is understood, add the thin NG control-plane wrapper
   and the single telemetry dashboard view. Activate governance only after the
   required independent Sol/Opus acceptance.

Not in the current Doing circle: refactor root-cause analysis, model-attribution
analysis, contract-review hardening, and trust rotation. They are retained in
the [Idea Pool](IDEA_POOL.md), not made prerequisites for starting workers.

### First-flow result

The first observation is recorded in
[`runs/2026-08-28-first-observation-qwen-direct.md`](runs/2026-08-28-first-observation-qwen-direct.md).
Qwen prepared-direct parked correctly at 4,820 effective tokens. Deterministic
reinspection showed that the original Map-only TicketSpec also relied on a
hypothetical Engine overlay. The next bounded work is therefore the explicit
Ticket DAG in
[`tickets/first-targeted-draw-dag.md`](tickets/first-targeted-draw-dag.md):
evidence preparation, then atomic Engine, Map, and verification children—not a
larger-model retry.

The initial Engine-child routing observations are in
[`runs/2026-08-28-engine-adapter-observations.md`](runs/2026-08-28-engine-adapter-observations.md).
The reissued v2 Engine child then used the complete module/test evidence,
returned a two-file Codex constrained proposal, and passed its focused cards,
scope, diff, and baseline-relative formatting gates in a disposable clone.
Its immutable TicketSpec and receipt are
[`tickets/engine-draw-target-lifting-v2.json`](tickets/engine-draw-target-lifting-v2.json)
and
[`runs/2026-08-28-engine-draw-target-lifting-v2.json`](runs/2026-08-28-engine-draw-target-lifting-v2.json).
No source tree was modified during that observation. The dependent Map sequence is also complete in
the same disposable clone: Qwen direct exposed a focused-test interface
failure, Codex was blocked by host bwrap setup, and a bounded Claude staged
repair supplied the test while preserving the Qwen semantic hunk. The exact
two-card Map tuple and the Engine conversion/execution gate both passed; see
[`runs/2026-08-28-map-target-player-draw-v4.json`](runs/2026-08-28-map-target-player-draw-v4.json).
The next Factory work is verification/reconciliation and the thin control
plane, not further implementation retry.

The user subsequently approved one narrow integration. The accepted
player-target draw Map→Engine patch is committed locally in
`openmagic` as `56eeacf024e0b17653d4c4eeb94c920efd4f77e7`, with no push or
deploy. The source Map gate passed after commit; the focused Engine test had
passed on byte-identical clone files but its source-tree retry is currently
blocked in the shared Go compiler. See
[`runs/2026-08-28-target-player-draw-integration-v1.json`](runs/2026-08-28-target-player-draw-integration-v1.json).

### Thin control-plane status

The single Factory NG dashboard is served at `http://localhost:9999/dashboard`
when Dispatcher v4 is running. It shows the current corpus-source/imported/
auto/review card totals, a small on-disk 15-minute status history, Ticket DAG
links, receipt binding, outcomes, integrations, and raw
input/output/cache/reasoning/cost telemetry. Its Qwen-local, Claude, and
Codex controls persist the selected profile/model and enabled state for the
next supervised NG cycle; they never start a legacy dispatcher lane or
integrate a patch. The receipt-only CLI source remains
[`scripts/factory-ng-dashboard.py`](../../scripts/factory-ng-dashboard.py),
so the web view has no competing TicketSpec or receipt interpretation.

The dashboard's `▶ Start factory` control starts the persistent Factory NG
ticket-production controller in its own tmux window. It runs only the explicit
deterministic producers registered by the harness, persists a newly produced
measurement/TicketSpec atomically, and exposes its phase/current activity in
the dashboard. It never replays a historical TicketSpec, touches the legacy
dispatcher queue, integrates source, pushes, or deploys. With no new
ground-truth class it remains visibly running but waiting for new work.

The first read-only legacy reconciliation is
[`legacy-backlog-reconciliation-v1.md`](legacy-backlog-reconciliation-v1.md),
with machine-readable detail in
[`legacy-backlog-inventory-v1.json`](legacy-backlog-inventory-v1.json).
Its pinned dispatcher snapshot classifies all 5,310 legacy rows: no row is
currently eligible for direct NG dispatch; every apparent ready item is either
a multi-shape sweep or needs a fresh single-shape evidence compile.

The first such remeasurement, `legacy:3967`, is recorded as
[`evidence-loyalty-body-choose-v1.json`](tickets/evidence-loyalty-body-choose-v1.json).
It scanned all 18,612 review cards and found 14 semantically mixed members, so
it is split-required rather than assigned to a model. The resulting controlled
cohort gate is [`controlled-cohort-v0.md`](controlled-cohort-v0.md).

The producer now derives its source revision rather than carrying the old
baseline SHA forward. Its first current-source check, legacy `5310`'s
`static_conditional` label, scanned all 18,612 review cards and found 446
members, 410 distinct matching details, and a largest exact-detail cluster of
four. It is therefore preserved as a Skill-bound
[`SPLIT_REQUIRED` evidence ticket](tickets/evidence-static-conditional-v1.json),
not sent to a worker. The full immutable member measurement is
[`measurements/static-conditional-v1.json`](measurements/static-conditional-v1.json).

The first current-source Engine candidate is the 17-member
[`switch_pt` DAG](tickets/engine-switch-pt-v1.json): all members have exactly
the same parser miss, with self, target-creature, and each-creature variants.
Its Sol adapter observation failed before reading code because bwrap could not
set up loopback; its declared Claude staged fallback was stopped by the 500k
reflection after 136 provider messages and 5,724,290 cache-read tokens without
a terminal verdict. Both are adapter outcomes, not capability/model-quality
judgments, and their raw receipts remain visible in the single dashboard.
Qwen prepared-direct then returned the correct `NEEDS_PRIMITIVE` park in 8,462
input tokens, nine output tokens, and 121 cache reads. It is therefore proven
for this cheap Engine **decision** route, but not yet for hard Engine
implementation.

The old Engine packer now accepts a Factory TicketSpec directly and uses its
pinned evidence anchors. Its first no-tools Sonnet pass on `switch_pt` returned
three valid named `NEED` interfaces in 48.7 seconds; its one bounded final
continuation then emitted no provider payload before 180 seconds. The combined
immutable observation is
[`runs/2026-08-28-engine-switch-pt-v8-claude.json`](runs/2026-08-28-engine-switch-pt-v8-claude.json).
This proves the index-grounded packet/NEED stage, while leaving final Claude
continuation transport—not the ticket/model semantic result—as the remaining
Engine-adapter problem.

The corrected one-turn Claude no-tools retry also produced no provider payload
within its 90-second harness bound (and thus no reportable provider tokens).
This is recorded as an adapter/availability failure in
[`runs/2026-08-28-engine-switch-pt-v4-claude.json`](runs/2026-08-28-engine-switch-pt-v4-claude.json),
not as evidence about Sonnet or the Engine ticket. The practical next rule is
small: run a cheap Claude health probe before routing work to its CLI adapter.

That probe subsequently passed (`FACTORY_NG_OK` in 1.6 seconds), while the
unchanged ticket's broad raw-excerpt packet still returned no payload inside
120 seconds. The separate v5 receipt records the packet-shape distinction;
the next retry must use a compact named-interface packet rather than treating
this as a Sonnet quality result.

The accepted target-player-draw source gate has now also passed in the real
source worktree: `go test ./cards -run '^TestDrawSpellTargetLifting$' -count=1`.
The immutable v2 integration receipt
[`runs/2026-08-28-target-player-draw-integration-v2.json`](runs/2026-08-28-target-player-draw-integration-v2.json)
supersedes the earlier stalled-gate record. The local commit remains unpushed
and undeployed pending an explicit user decision.

The function/capability index is again a required Engine-preparation input,
not a raw-source substitute. Its SQLite-backed knowledge service now indexes
non-test `backend/game` functions under the `engine` kind alongside the
existing primitives, helpers, and handlers. The isolated regression builds a
temporary index and proves more than 100 engine symbols, including the P/T
and effect-manager interfaces. No live service or lane was restarted; this
takes effect on the service's ordinary next reindex.

The index-grounded `switch_pt` implementation retry reached a real semantic
gate, rather than a transport failure. It was allowed to continue past its
180-second reflection warning, and a single repair was applied and tested only
in a disposable clone. Its simple 2/5 → 5/2 test passes, but the Ticket's
composition invariant fails: a 2/5 creature with +1/+2 must switch to 7/3,
whereas the proposal gives 8/5 by snapshotting into Layer 7b. The immutable
receipt is [`runs/2026-08-28-engine-switch-pt-v9-claude.json`](runs/2026-08-28-engine-switch-pt-v9-claude.json).
This is a correctly rejected Engine enhancement and a concrete next-foundation
ticket (represent switching at post-additive Layer 7e), not a reason to merge
or to run unbounded retries.

The next isolated Engine foundation observation was the smaller Layer-7e
representation ticket. Its Opus run made one precise `NEED` request, then
produced a semantically strong multi-hunk proposal. The shared applier had a
real limitation: it silently retained only the first SEARCH/REPLACE pair under
one FILE header. It now applies every pair and has a regression test. The
reapplied proposal passes its actual Layer-7e behavior tests in a disposable
clone, but the v1 TicketSpec named a different test function, so the selector
would execute zero tests. The immutable receipt correctly records that as a
contract-selector failure rather than accepting or integrating the patch:
[`runs/2026-08-28-engine-pt-switch-layer-v1-opus.json`](runs/2026-08-28-engine-pt-switch-layer-v1-opus.json).
The next run needs a fresh TicketSpec revision with a behavior-based focused
selector; it must not relabel this v1 proposal as an accepted v2 result.

That fresh v2 observation is now accepted for dependent observation. Opus made
one bounded NEED request and its proposal passed test discovery, focused Layer
7e behavior, scope, diff, and baseline-relative formatting gates in a
disposable clone. The full game-package suite has 25 known baseline failures
in both clean source and candidate, with no candidate-only failures. The
accepted result is
[`runs/2026-08-28-engine-pt-switch-layer-v2-opus.json`](runs/2026-08-28-engine-pt-switch-layer-v2-opus.json).
It supplies the explicit Engine foundation for a new small `switch_pt`
ability-dispatch child; it has not been integrated, pushed, or deployed.

That dependent child is now also accepted for observation in
[`runs/2026-08-28-engine-switch-pt-v2-opus.json`](runs/2026-08-28-engine-switch-pt-v2-opus.json).
It first applies the Layer-7e parent in a fresh clone, then wires only the
three proven execution shapes (self, target creature, each creature). The
strict multi-hunk applier applied four parent hunks and two child hunks; the
initial child test used stale APIs, so its exact compile errors produced a
small repair rather than a broad retry. A malformed Git-conflict-delimiter
repair was rejected as-is; the succeeding format-only repair used the normal
SEARCH/REPLACE protocol. The final TestSwitchPTExecution selector is green
for all three shapes, and the candidate has no full-game failure beyond the
same 25 clean-baseline failures. This proves a parent-overlay Ticket DAG and
multiple changes per proposal without integrating, pushing, or deploying any
source change. The next work item is a separate Map child, not more Engine
redesign.

The local Qwen prepared-direct adapter was debugged against the next Map child:
its old non-streaming llama.cpp transport returned an empty body after the
server had already decoded hundreds of tokens. The adapter now consumes SSE
and asks for the final usage event; a probe reports input/output/cache reads
correctly. The Map packet now also supplies exact `parse_atom` argument probes,
so a no-tools worker need not guess nested parser shapes. The first repaired
Qwen observation produced a compact proposal and passed its supplied test, but
the independent TicketSpec boundary check caught self-form mapping on a spell;
its one repair understood the bug but used invalid Markdown patch delimiters.
It is honestly rejected in
[`runs/2026-08-28-map-switch-pt-v4-qwen.json`](runs/2026-08-28-map-switch-pt-v4-qwen.json),
not normalized or integrated.

The next Qwen profile revision is `qwen-prepared-direct@1.0.2`. Its system
instruction now gives the exact machine-parser grammar, including a mandatory
file header for every repair. It also has a narrow adapter-side recovery tool:
it may convert a complete `FILE:/SEARCH:/REPLACE:` payload (optionally inside
one fence) only when every file path is explicitly Ticket-allowed. Missing
paths, prose, unified diffs, and generic Markdown remain rejected. The v4 raw
repair remains invalid and immutable; this is for a fresh TicketSpec only.

The fresh `map.switch-pt/v5` Qwen observation confirms the adapter repair:
both responses used canonical machine blocks, its six focused Map tests pass,
and the target-player/qualified-target boundaries remain honest. Its composed
17-member gate instead exposed a missing Engine registry bridge: accepted
`backend/game` overlays deliberately do not register `switch_pt` in
`backend/cards`, so the parser still refuses it. The failed no-push receipt is
[`runs/2026-08-28-map-switch-pt-v5-qwen.json`](runs/2026-08-28-map-switch-pt-v5-qwen.json).
The next atomic work is
[`engine-switch-pt-registry-bridge-v1`](tickets/engine-switch-pt-registry-bridge-v1.json),
scheduled for one isolated Claude Opus observation at 02:00 CEST; it cannot
push, deploy, or alter the source checkout.

The first repeatable producer is now deliberately narrow rather than generic:
`scripts/factory-ng-produce-registry-bridge.py` detects the exact class
“existing `ExecuteAbilityEffect` dispatcher, missing v2 registry entry”,
checks for an existing TicketSpec, and emits one Engine bridge candidate only
when the class is proven. It reports `already_registered`,
`no_existing_dispatcher`, or `duplicate_ticket` otherwise. Other Engine gap
classes stay separate producers rather than being guessed by this one.

## Safety / resumption checklist

1. Start in `/opt/development/magic-ops`; read `AGENTS.md`, canonical memory,
   and run `scripts/session-health-check.sh`. The obsolete global session lock
   is retired; integration, deployment, and dispatcher administration use
   their own process-held scoped locks from `factory-ng-scoped-lock.sh`.
2. Preserve unrelated dirty files. This repository currently contains user
   changes and untracked Factory NG documentation; do not reset, stash, push,
   deploy, mutate live tickets, or restart lanes merely to continue NG design.
3. Record every proposed-versus-accepted distinction. A passing local test,
   benchmark receipt, or draft schema never authorizes live integration.
4. Runtime policy is explicit in `config/factory-ng-policy.json`: accepted
   durable patches enter the full production gate automatically and a green
   gate pushes automatically. Live deployment remains separately disabled by
   default. Claude and Codex dispatch use the existing quota-reset-anchored
   1/7 weekly pace gates; local Qwen is unmetered.
