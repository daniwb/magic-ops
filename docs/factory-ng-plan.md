# Magic Factory NG — Ground-Truth Rebuild Plan

Status: discussion draft  
Created: 2026-08-27  
Implementation name: undecided; reserve `v5` for an implementation/API version

Current resumption point: [`factory-ng/CURRENT.md`](factory-ng/CURRENT.md).

## Objective

Build a small, observable, project-independent software-development factory
whose first product is a trustworthy ticket. Every piece of work must have a
known origin, state, failure reason, and verified outcome. Worker/model
experimentation comes only after this contract works.

This plan does not authorize changing the live v4 dispatcher or migrating its
data. It is the baseline for discussing past failures and design alternatives.

## Current ground truth (2026-08-27)

- Dispatcher database: 5,310 tickets.
- Ticket states: 1,637 done, 1,402 superseded, 1,022 wait, 741 archived-v1,
  232 parked-era1, 164 duplicate, 86 blocked, 21 todo, and 5 fable.
- Capabilities: 48 implemented and 86 open.
- All 86 open capabilities are linked only to blocked tickets.
- Dispatcher stats reported 0 fixes and 0 miss reduction in the last 24 hours;
  42 fixes in the last seven days; 28,181 total misses.
- Ox-alpha's recent capability attempts returned empty responses and were
  recorded as infrastructure failures.
- Qwen and the other engine lane report no open capability with a linked
  claimable ticket; the legacy pipeline reports an empty queue.

Conclusion: model quality is not the only blocker. Queue production, lifecycle
states, and dependency handling currently prevent useful work.

## System shape

```text
Corpus snapshot
    -> deterministic analysis
    -> candidate work items
    -> ticket compiler and validation
    -> ready ticket queue
    -> skill-directed worker
    -> mechanical gates
    -> fresh-context review
    -> integration
    -> re-measure corpus
    -> close ticket with proven delta
```

Central rule:

> A worker never invents its own mission. The factory produces a complete,
> validated ticket from measured ground truth.

## What the corpus is for

The corpus is the project's versioned measurement surface, not a queue of cards
and not prompt material to send wholesale to a model. For Magic it must let the
factory answer, deterministically:

- what grammatical and semantic structures actually occur;
- which structures are represented faithfully in the typed card definition;
- which represented structures have a real executor and discriminating test;
- which cards are fully playable, partially implemented, or explicitly red;
- which failures share one root cause and which capabilities co-occur;
- what exact population a proposed change is predicted to unlock; and
- which members of that population changed after the implementation.

The factory therefore keeps three different measurements visible:

1. `recognized` — the source unit was classified and no text was silently lost;
2. `expressible` — the complete meaning fits the project's typed representation;
3. `playable` — every represented behavior has verified runtime support and all
   project honesty gates pass.

These terms must never be collapsed into one coverage percentage. A card may be
recognized or expressible without being playable. Explicit partial support is
acceptable only when the unsupported fragment is preserved as typed, located,
clusterable evidence; silent swallowing is a defect.

The useful unit of work is consequently a measured root cause across the
corpus, not usually one card and not an arbitrary batch of 80–200 paragraphs.
Cards and paragraphs are evidence and scope members. Tickets are class-level
changes or atomic capabilities whose predicted and actual effects are computed
against those members.

## Product layers

1. **Map** — converts Oracle text into structured card definitions. Work targets
   a grammatical class, not an individual card.
2. **Engine** — executes structured definitions. Engine work adds one atomic,
   reusable behavior.
3. **Handlers** — an explicit escape hatch for genuinely exceptional cards,
   not the default route.
4. **Factory/Ops** — produces tickets, invokes skills, records attempts,
   applies gates, and reports confirmed outcomes.

These are the initial Magic project layers, not hard-coded factory concepts.
The reusable factory core knows about projects, typed work, graphs, attempts,
artifacts, budgets, routing, gates, reflection, integration, and telemetry. A
project package supplies its own ticket producers, work types, Skills, source
adapters, metrics, gates, and deployment policy. Magic Map/Engine/Handler and
phase.rs parser/engine workflows are two project configurations on that core.

Project-specific Skills remain versioned with, or explicitly pinned by, their
project. The factory records their content hash and contract version on every
attempt; it does not copy domain instructions into a global mega-prompt.

## Work model: typed tickets in a graph

`Ticket` is the common lifecycle envelope, but work inside it is explicitly
typed. Map and Engine work must never be inferred from a title or share an
ambiguous worker contract.

Initial work types:

- `discovery` — measures and partitions a corpus problem;
- `map` — extends deterministic parsing/mapping for a bounded class;
- `engine` — implements one atomic reusable behavior;
- `handler` — implements a justified exceptional card;
- `verification` — proves a claimed result or audits residual scope;
- `integration` — reviews, gates, lands, and remeasures a change;
- `reflection` — investigates process deviation and proposes corrective work;
- `factory` — changes the factory itself.

Tickets form a directed acyclic graph (DAG), not a strict tree:

- one ticket may have multiple parents;
- one parent may have multiple children;
- dependency edges and decomposition/provenance edges are distinct;
- one root `main_ticket` represents the original measured mission;
- every descendant remains traceable to all originating roots;
- cycles are rejected mechanically.

Suggested edge types are `decomposes_to`, `blocked_by`, `discovered_by`,
`verifies`, `integrates`, `residual_of`, and `reflects_on`. A ticket becomes
ready only when the edge-specific dependency policy is satisfied.

The main ticket closes only when every item in its original scope is accounted
for as fixed, explicitly unsupported, invalid input, or linked residual work.
Completing a few children is progress; it is not completion of the root.

## Model routing and bounded execution

The ticket producer assigns a work profile instead of naming a model directly:

- task type and required Skill;
- difficulty/risk class;
- context requirements;
- required tool capabilities;
- maximum autonomous actions;
- token/time targets and warning thresholds;
- minimum model capability policy;
- escalation route.

A versioned routing policy maps that profile to currently available models.
This keeps the ticket stable when models or prices change and permits fair
comparisons across models. Routing decisions and overrides are recorded on the
attempt.

The model-profile boundary is defined concretely in
[`factory-ng/model-profile-contract-v1.md`](factory-ng/model-profile-contract-v1.md).
Profiles own native executables, context rendering, permissions, output
contracts, bounded repairs, and telemetry parsers; the Factory retains ticket,
Skill, acceptance, scope, and integration authority. The initial prepared
profile comparison is recorded in
[`benchmarks/model-routing-v2/report.md`](benchmarks/model-routing-v2/report.md).
Every integration-eligible change must also follow the immutable
[`factory-ng/change-provenance-and-rca-contract-v1.md`](factory-ng/change-provenance-and-rca-contract-v1.md):
commit trailers establish its model/profile provenance, while later incidents
receive evidence-based root-cause analysis and linked corrective tickets.

The target envelope for an ordinary Map or Engine ticket is 200k effective
tokens. Crossing 500k adds a warning label and launches a reflection task; it
does **not** stop, cancel, or discard the attempt. These are operational
hypotheses, not success metrics. Correctness and confirmed corpus delta remain
primary.

The default bounded workflow preserves the strongest decision from the old
factory: seven explicit stages, with deterministic code doing everything that
does not require semantic judgment.

| # | Stage | Default authority |
|---|---|---|
| 1 | Compile and validate the ticket from a pinned corpus snapshot | code |
| 2 | Reproduce the baseline and materialize the immutable scope manifest | code |
| 3 | Build a compact evidence pack: examples, exact code regions, analogous implementation, applicable Skill | code |
| 4 | Choose the smallest rule/capability change, or issue a binding refusal/park verdict | model |
| 5 | Produce constrained edits and a discriminating test | model |
| 6 | Apply safely, run mechanical gates, remeasure every scope member, and allow bounded correction on the kept tree | code; model only for a focused correction |
| 7 | Create the immutable result/checkpoint and hand it to fresh review/integration | code |

This is a workflow template, not seven mandatory model conversations. An
ordinary Map or Engine ticket should normally need one semantic model call and,
only if a concrete gate fails, one focused repair call. Exploration is an
explicit escalation class rather than the default execution mode.

Budget thresholds are observational controls, not kill switches. Crossing one
creates a checkpoint and reflection while preserving work and execution context.
The reflection verdict may be `CONTINUE_NECESSARY`: the work is correctly
scoped, the additional cost is justified, and execution should continue. Other
verdicts may recommend split, reroute, repair infrastructure, revise the ticket,
or stop only through an explicit authorized cancellation policy. A threshold
never silently converts Map work into Engine work.

## Token and cost telemetry

Store both raw provider counters and a normalized accounting view per model call
and aggregate them per workflow step, attempt, ticket, root mission, model, and
project:

- input tokens;
- output tokens;
- cache-read tokens;
- cache-write/creation tokens;
- reasoning tokens when the provider exposes them;
- tool-result/context bytes or tokens when measurable;
- provider-reported cost and locally computed cost;
- model, provider, pricing-policy version, and whether each field is measured,
  estimated, or unavailable.

Never collapse these fields irreversibly into one `tokens` number. An optional
`effective_tokens` metric may apply versioned weights for comparison, but the
raw counters remain authoritative and visible. Token checkpoints occur at every
workflow boundary so the factory can explain which step consumed the budget.

## Scope conservation and residual work

Past categorization often grouped 80–200 cards or paragraphs, while a patch
fixed only a small subset. Factory NG treats the initial classified set as a
versioned scope manifest.

After every attempt the factory recomputes each scoped item and partitions it
into:

- confirmed fixed by this change;
- already fixed independently;
- still failing for the same root cause;
- reclassified to a different root cause;
- invalid or unsupported with evidence.

Every residual partition must become a linked child ticket, attach to an
existing ticket, or receive an explicit terminal classification. The factory
must never equate `delta > 0` with completion of the categorized scope.

Key metrics are therefore both `confirmed_delta` and `scope_completion_ratio`.
The root ticket visualization shows the original population, each partition,
the work graph, and the current terminal accounting.

## Reflection as first-class work

Reflection produces evidence and proposed factory changes; it does not mutate
production automatically. `CONTINUE_NECESSARY` is a valid and important result,
not a failed reflection.

Per-ticket reflection triggers include:

- token/time warning threshold exceeded;
- repeated failure or retry beyond policy;
- actual unlock materially below predicted unlock;
- scope completion stalls while attempts remain green;
- model output repeatedly violates its Skill contract;
- infrastructure failures are confused with work failures.

A 24-hour reflection job compares planned and actual throughput, ready-queue
health, aging, scope completion, model success/cost by work type, failure
taxonomy, integration latency, and confirmed corpus movement. It publishes a
structured report and may propose linked `factory` tickets. Humans approve
policy changes until the reflection mechanism itself is proven reliable.

## One operator dashboard

Factory NG has one dashboard backed by the same structured event/telemetry
store as the dispatcher. Logs remain drill-down evidence, not the primary UI.

The dashboard must provide:

- the main-ticket graph and descendant status;
- live attempts and stage progress;
- queue readiness, blocking reasons, and ticket aging;
- predicted versus actual unlock, tokens, time, retries, and completion ratio;
- model performance broken down by work type and difficulty;
- integration and gate status;
- corpus coverage/miss movement;
- reflection alerts and daily reports;
- links from every aggregate to the exact ticket, attempt, command result,
  commit, and measurement that produced it.

There is one write authority and one metric definition for both runtime and UI;
the dashboard must not maintain a second interpretation of ticket state.

## Build phases

### Phase 0 — Freeze and inventory

Do not discard or reactivate existing tickets yet. Produce a read-only inventory
that classifies every ticket as:

- `ready`
- `blocked_by_capability`
- `stale`
- `duplicate`
- `already_satisfied`
- `mixed_or_ambiguous`
- `legacy_unverified`
- `terminal`

Deliver one lifecycle definition and one reconciliation report joining tickets,
capabilities, branches, commits, current corpus misses, and explicit wait reasons.

**Exit criterion:** all totals reconcile exactly with the dispatcher database;
no ticket remains merely `wait` without a structured reason.

### Phase 1 — Define TicketSpec v1

A versioned, machine-readable ticket contains:

- stable ID and schema version;
- explicit work type and work profile;
- root mission IDs and typed graph edges;
- immutable scope manifest and current residual partitions;
- exact source evidence: card, Oracle paragraph, corpus version, and hash;
- observed gap or failure;
- required behavior;
- positive and adjacent negative examples;
- expected unlock set and estimated delta;
- allowed files and prohibited scope;
- required Skill;
- required tests, gates, and commands;
- completion evidence;
- dependencies;
- retry and terminal-failure policy.
- expected time/token envelope and reflection triggers.

**Exit criterion:** an invalid, mixed, stale, duplicate, or already-satisfied
ticket cannot reach a worker.

### Phase 2 — Build the ticket producer first

The first implementation milestone must:

1. Snapshot corpus and gameplay SHA.
2. Run coverage, swallow, vocabulary, and executor audits.
3. Group failures by root cause.
4. Calculate marginal unlock and dependency bundles.
5. Check whether the required capability already exists.
6. Compile the highest-value candidate into a validated ticket.
7. Deduplicate it against open and historical tickets.
8. Place it in `ready`.

Ticket production begins as deterministic code. AI may assist classification or
explanation, but it is not the sole authority for evidence, identity, or priority.

**Exit criterion:** running the producer twice against unchanged inputs creates
zero additional tickets.

### Phase 3 — Turn Skills into executable contracts

Create a minimal native Skill set:

- `produce-ticket`
- `verify-premise`
- `implement-map-class`
- `implement-engine-capability`
- `implement-exception-handler`
- `review-change`
- `integrate-change`
- `explain-attempt`

Each Skill defines inputs, refusal conditions, exact context, allowed commands,
output schema, mechanical gates, and binding terminal verdicts. The engine Skill
must search for an existing capability first and may return verdicts such as
`REFUSE_EXISTING_CAPABILITY` and `REFACTOR_FIRST`.

The Skills are also the project's binding "how to program here" specification.
They must encode, rather than merely suggest:

- the architectural boundaries and invariants the worker may not violate;
- an existence protocol before adding a type, primitive, handler, or helper;
- allowed and prohibited paths plus ownership of every required migration site;
- preferred analogues and extension points, with drift-checked source anchors;
- parameterization/refactor rules that may refuse locally convenient growth;
- exact edit/output protocols and a bounded context-request mechanism;
- at least one discriminating test that traverses the real execution path and
  fails when the implementation is reverted;
- required focused, regression, honesty, and corpus-delta gates;
- explicit success, park, split, refactor-first, and infrastructure verdicts;
- fresh-context review criteria and a digest proving that the reviewed diff is
  the diff proposed for integration.

Instructions that can be checked belong in linters, schemas, diff gates, or the
harness. The Skill explains the rule and names the verdict; mechanical code
enforces it. Compact mode-specific Skills are preferred over one large manual,
and their content hashes are recorded on every attempt.

**Exit criterion:** different supported models can receive the same ticket
through the same Skill and be judged by the same gates.

### Phase 4 — Make attempts fully observable

Every execution creates an immutable attempt record with:

- ticket and dependency IDs;
- worker, model, Skill version, and prompt/package hash;
- repository and corpus SHAs;
- start and finish timestamps;
- commands executed and files changed;
- model, infrastructure, contract, premise, test, and gate failures;
- before/after metrics;
- branch, commit, review, and integration outcome.
- workflow-step transitions and budget consumption;
- routing policy, selected model, and selection reason.

The operator view must immediately answer what is running, why the ticket was
created, what the worker did, where it failed, and what measurable progress
landed.

**Exit criterion:** explaining an attempt requires no shell-log archaeology,
and the single dashboard derives its state solely from these records.

### Phase 5 — Debug one golden Map flow

Choose a currently reproducible Map ticket with multiple affected cards, a
bounded grammar change, no new engine capability if possible, clear positive
and negative examples, and a measurable eligibility delta.

Run it in assisted debug mode with inspectable checkpoints:

1. Corpus evidence.
2. Gap detection.
3. Ticket compilation.
4. Skill selection.
5. Worker context package.
6. Proposed patch.
7. Focused tests.
8. Fresh-context review.
9. Integration gate.
10. Corpus remeasurement and ticket closure.
11. Residual-scope partition and root-ticket graph update.

The completed trace becomes both the canonical worked example and a factory
regression fixture.

### Phase 6 — Add the Engine flow

```text
Map ticket discovers missing behavior
    -> capability contract
    -> engine ticket
    -> engine Skill
    -> discriminating execution test
    -> review and integration
    -> dependent Map ticket requeued
    -> confirmed corpus delta
```

A capability does not close merely because code merged. It closes only after a
dependent Map flow uses it successfully.

### Phase 7 — Reconcile the legacy backlog

- Recompute evidence against current corpus and code.
- Close already-satisfied tickets.
- Merge duplicates.
- Split mixed tickets.
- Recreate valid work using TicketSpec v1.
- Preserve historical IDs as provenance.
- Archive unverifiable free-text demands.

The existing 86 open capabilities are audited first. None automatically enters
the new ready queue.

### Phase 8 — Controlled production rollout

1. One supervised ticket.
2. Five-ticket canary with pushes disabled.
3. One production worker.
4. Two different models on comparable tickets.
5. Increase concurrency only after measured reliability.

A weak model must fail visibly and cheaply; it must not be able to create silent
semantic damage.

## Initial design defaults

| Decision | Proposed default |
|---|---|
| Source of work | Deterministic corpus analysis |
| Queue unit | One root cause or atomic capability |
| Ticket storage | Dispatcher database with versioned JSON contract |
| Planning authority | Ticket producer, not worker |
| Skills | Native, narrow, versioned, with refusal verdicts |
| AI role in ticketing | Assistive; deterministic validation is authoritative |
| Work structure | Typed tickets in a DAG with root missions |
| Progress metric | Confirmed delta plus scope completion ratio |
| Review | Fresh context using ticket, diff, and standards |
| Existing tickets | Migrate and reconcile; do not delete |
| First debug flow | Bounded Map class, then one Engine dependency |
| Initial concurrency | One supervised worker |
| Model policy | Work-profile routing; model-independent contracts and gates |
| Ordinary ticket envelope | 200k target; 500k warning + reflection, never automatic stop |
| Reflection | Triggered per-ticket plus a structured 24-hour review |
| Operator UI | One telemetry-backed dashboard |
| Project model | Reusable core plus versioned project packages and Skills |

These are discussion defaults, not settled decisions. Past failures and new
ideas should be evaluated against them and recorded in a decision log before
implementation.

## First implementation slice

Before this slice starts, the corpus contract is designed in a dedicated,
fresh-context Codex session. The Factory NG architecture session remains the
decision authority: it reviews that session's artifacts, resolves open
questions, and incorporates only accepted conclusions into this plan.

The corpus session must write its outputs under
`docs/sessions/corpus-contract/`; chat prose is not a handoff artifact. Its
required outputs are:

1. `report.md` — evidence, findings, alternatives, and recommendations;
2. `contract.md` — proposed definitions, invariants, inputs, outputs, and gates;
3. `metrics.md` — precise `recognized`, `expressible`, and `playable` formulas;
4. `ticket-examples.md` — representative root-cause scope manifests and their
   compiled Map/Engine tickets;
5. `open-questions.md` — decisions that require the architecture session;
6. `manifest.json` — source repository/corpus SHAs, files consulted, commands,
   artifact hashes, and session status.

The session is research and design only: it must not change production code,
ticket state, workers, or the live dispatcher. The architecture session checks
the manifest, reviews claims against the repository, records accept/revise/
reject decisions, and reflows accepted material into this plan and later
TicketSpec documents. The dedicated brief is
`docs/sessions/corpus-contract-brief.md`.

The dedicated session completed on 2026-08-27. Its preserved artifacts are in
`docs/sessions/corpus-contract/`; architecture review verdict is
`ACCEPT_WITH_REVISIONS` in
`docs/sessions/corpus-contract/architecture-review.md`. Accepted foundations
are corpus/text/meaning/execution/scope conservation, distinct
recognized/expressible/playable measurements, structured root causes, exact
gap sets, immutable member scopes, and exhaustive before/after partitions.
Coverage numbers remain unknown. The next bounded design slice is a read-only
`CorpusSnapshot v1` comparison that settles population and identity policy
before TicketSpec implementation.

That comparison completed on 2026-08-27 with architecture verdict
`ACCEPT_WITH_REVISIONS`; see
`docs/sessions/corpus-snapshot/architecture-review.md`. It proved that
`scryfallOracleId + side` is not a unique source-row identity and that
AtomicCards cannot authoritatively distinguish paper, digital, or rebalanced
content. Factory NG will use one universal source inventory plus named policy
projections, and separate semantic Oracle-face identity from unique source
occurrence identity. The legacy classifier projection remains a baseline, the
non-funny projection is the initial diagnostic surface, and no production
population is selected until pinned MTGJSON `AllPrintings` is measured.
`AllPrintings` is the chosen occurrence/product authority: MTGJSON `uuid` is
the candidate occurrence ID; `scryfallOracleId` plus face relations supplies
semantic identity; availability, online-only, rebalanced, set, and product
fields drive named projections. AtomicCards remains a derived compatibility
check, not identity authority. No second provider is introduced by default.

The AllPrintings validation completed on 2026-08-27; see
`docs/sessions/mtgjson-allprintings/architecture-review.md`. It confirmed
122,669 unique UUID occurrences, complete Oracle IDs, clean face relations,
explicit availability, and complete original/rebalanced links. The architecture
now distinguishes two linked populations: the universal occurrence inventory
preserves printing/product evidence, while corpus coverage and ticket work use
a canonical semantic Oracle-face snapshot derived from audited occurrence
groups. Reprints must never multiply root-cause prevalence or ticket priority.
The dedicated derivation brief is
`docs/sessions/oracle-face-snapshot-brief.md`.

The derivation completed on 2026-08-27; architecture review is
`docs/sessions/oracle-face-snapshot/architecture-review.md`. The pinned source
contains 41,979 semantic Oracle-face groups: 41,973 source-admitted and six
quarantined conflicts. This is now the work population for TicketSpec design.
Printing occurrence links remain evidence. Because 142 groups have differing
per-printing other-face target sets, occurrence `otherFaceIds` unions are not
treated as semantic truth without a typed composition rule. Relation-dependent
tickets require a relation-ready receipt; other source-admitted work may
proceed. The corpus foundation is ready for TicketSpec v1 design and a
read-only ticket compiler prototype, but not unsupervised production tickets.
The dedicated implementation brief is
`docs/sessions/ticketspec-v1-brief.md`.

The first TicketSpec/compiler prototype completed on 2026-08-27 but received
architecture verdict `REVISION_REQUIRED`; see
`docs/sessions/ticketspec-v1/architecture-review.md`. It found a plausible
two-face `p_draw` Map class, but hard-coded its baseline, did not compute full
per-face gap sets, used synthetic receipts/hashes and placeholder gates, and
validated only shallow schemas. Its ticket is a candidate fixture, not ready
for model stages. The repair must bind the current parser, complete gap sets,
real Engine/Skill/gate receipts, full source spans, strong schemas, historical
deduplication, and an explicit root-mission graph before the debug flow.
The dedicated repair brief is
`docs/sessions/ticketspec-v1-repair-brief.md`. It preserves the rejected
prototype, limits execution to deterministic stages 1–3, and permits lifecycle
`ready` only through one mechanical readiness evaluator. Model stages 4–7 wait
for architecture review of the repaired artifacts.

The repair completed on 2026-08-27 with architecture verdict
`REVISION_REQUIRED`; see
`docs/sessions/ticketspec-v1-repair/architecture-review.md`. It successfully
reproduced full-text parser evidence, separated the two-member root scope from
the one-member sole-blocker/unlock scope, added a real Skill, history fixture,
and root mission graph, and honestly retained lifecycle `candidate` when its
Engine behavior gate failed. It may not enter model stages: cross-artifact
hashes are not enforced, readiness is still assigned outside the named sole
evaluator, normative nested schemas remain shallow, and creation-gate results
are largely authored rather than derived from execution receipts. The next
slice is a narrow deterministic correction of hash binding, readiness/gate
authority, the empty-library Engine test fixture, nested schemas, and manifest
finalization, followed by adversarial review.
The dedicated execution brief is
`docs/sessions/ticketspec-v1-contract-correction-brief.md`; it preserves both
earlier prototypes, runs no model stages, and requires a single top-level
pipeline plus adversarial proof before lifecycle `ready` is possible.

The contract correction completed and received architecture verdict `ACCEPT`
on 2026-08-28; see
`docs/sessions/ticketspec-v1-contract-correction/architecture-review.md`.
Independent review strengthened it further so the sole readiness evaluator
verifies receipts before consuming them, stored analyses are compared with a
fresh parser run from the pinned snapshot, and sole-blocker/unlock subsets are
mechanically rederived. The final pipeline passes 37 adversarial assertions,
two normative-identical runs, the target-player Engine overlay proof, and the
separate manifest verifier. The exact Map ticket is now admitted to the fully
observed stages 4–7 golden flow, without deployment or live ticket mutation.

The later execution route is hybrid but evidence authority remains
deterministic: code prepares facts; local AI may structure and compress them;
mechanical checks verify that preparation; a capability-matched model makes the
hard semantic decision and constrained implementation; code gates and
remeasures; local AI may prepare focused correction evidence before another
expensive call. Local and online input/output/cache tokens are measured
separately. The 200k effective-token value is a target and 500k is a
warning/reflection trigger, never a destructive stop.

The first slice produces exactly:

1. `TicketSpec v1`.
2. A read-only backlog reconciliation report.
3. A deterministic compiler that creates one valid Map ticket.
4. A native `produce-ticket` Skill.
5. An operator/debug view for the ticket and its attempts.
6. One fully observed dry run without automatic push.
7. One reviewed production run showing a confirmed coverage delta.

Only then should the project compare or scale Ox-alpha, GLM 5.2, Qwen, Codex,
or Claude workers.

## Reference experiment — observe the phase.rs factory

Before implementing broad automation, run one phase.rs task using the project's
own documented workflow and Skills. This tests whether Factory NG can observe a
different project without encoding Magic-specific Map/Engine assumptions.

phase.rs documents two relevant workflow classes:

- heavy engine work through `$engine-implementer`: plan → independent plan
  review → implementation → verification → independent implementation review
  → commit;
- lighter parser work through project-specific Skills such as
  `$parser-velocity`, which deliberately avoids the heavy review loop for
  near-miss parser changes.

Experiment preparation:

1. Select one bounded, real phase.rs task and record why its workflow class was
   chosen.
2. Pin repository SHA, project instructions, Skill files, model, provider, and
   pricing-policy version.
3. Run in an isolated worktree with publishing/merge disabled unless separately
   authorized.
4. Wrap every model call and workflow transition with telemetry capture.
5. Preserve stage artifacts so plan, reviews, implementation, verification, and
   reflection can be inspected independently.

Required report:

- raw input, output, cache-read, cache-write, and reasoning tokens per call;
- the same totals per workflow stage and for the complete root task;
- elapsed and active time per stage;
- context/package size and Skill versions;
- retries, failures, reflection triggers, and verdicts;
- changed files, tests, review findings, and final outcome;
- provider-reported and locally calculated monetary cost where available;
- a narrative trace explaining exactly how the factory performed the work.

The experiment must not rely only on a CLI's final summary because cumulative
versus last-turn accounting has been wrong in the previous factory. Raw call
records must reconcile to every aggregate shown on the dashboard.

## Open discussion log

Use this section to capture each idea or past failure before altering the plan.
For every item record:

- observed event and evidence;
- underlying failure mode;
- whether an existing phase prevents or detects it;
- proposed design change;
- cost and new risks;
- decision and validation method.

### 2026-08-27 — Work specialization, scope loss, graph, reflection, and UI

Observed problems and ideas:

- different factory stages require different model capabilities;
- Map and Engine tickets are currently difficult to distinguish reliably;
- the minimal staged workflow should normally fit below 500k effective tokens,
  with roughly 200k as the desired operating point;
- classifications containing 80–200 items often produced changes for only a
  few items, after which the residual scope became hard to follow;
- original work and derived work need many-to-many provenance and dependency
  links plus visualization;
- exceptional ticket cost/duration and daily underperformance require explicit
  reflection;
- split dashboards and log-first operation hide the actual system state.

Decision incorporated into this draft:

- use typed tickets with stable work profiles and policy-based model routing;
- use a DAG with typed edges and a visualizable root main ticket;
- conserve the original classified scope and require residual reconciliation;
- record a seven-step default workflow, a 200k target, and a non-destructive
  500k reflection warning;
- create first-class per-ticket and daily reflection work;
- build one dashboard on the dispatcher's structured telemetry authority.

Validation remains to be designed in detail during TicketSpec and telemetry
schema work.

### 2026-08-28 — First observed golden Map flow

The target-player-draw golden flow completed stages 4–7 in isolated branches.
Fresh review rejected the initial Map-only success because the production draw
converter discarded the emitted player target; the direct Engine overlay had
bypassed that boundary. The factory therefore changed the stage-4 verdict from
`IMPLEMENT` to `SPLIT`, produced a linked Engine child ticket, and added a test
that crosses DSL conversion, cast-time targeting, and resolution with populated
libraries.

The Map checkpoint is `6a4ec857302d120b7ca1eaf4c25f4d811891d978` and
the Engine child checkpoint is
`4d1935d26381c0b0dc1a1ec2540a205c5d4cc6de`. Fresh Stage-7 review returned
`ACCEPT`. No branch was pushed, no deployment occurred, and no live ticket was
mutated. The repository-wide `game` suite remains baseline-red and is not
claimed as a passing gate; the focused production-boundary and full `cards`
suite are green with content-bound receipts.

This run also validated the non-destructive budget policy. Four reviewer calls
reported 1,048,258 input tokens (865,536 cached), 8,073 output tokens, zero
cache-write tokens, and 1,934 reasoning-output tokens. The 500k warning launched
reflection, whose correct result was to continue because review had exposed a
real false-positive gate. The immediate NG design requirement is now explicit:
every Engine-capability proof must traverse the production converter boundary,
and every passing claim must have a receipt bound to the reviewed diff.

### 2026-08-27 — Non-destructive budgets and reusable factory core

Observed requirements:

- a 500k automatic stop can discard valuable work and context;
- reflection may legitimately conclude that expensive work is necessary;
- the factory must serve software projects beyond Magic through different
  project Skills;
- phase.rs provides a documented external workflow to observe;
- token accounting must retain input, output, cache reads, and cache writes.

Decision incorporated into this draft:

- replace hard stops with warning labels, checkpoints, and reflection;
- add `CONTINUE_NECESSARY` as an explicit reflection verdict;
- separate the reusable factory control plane from project packages;
- retain raw provider token dimensions and stage-level accounting;
- add one instrumented phase.rs run as the reference portability experiment.

### 2026-08-27 — Preserve the staged pipeline and define the corpus contract

Evidence reviewed:

- the production `map`, `engine`, and `handler` pipelines all used the same
  seven-stage shape: deterministic extraction/evidence, model decision/edit,
  deterministic apply/gates/commit;
- the 2026-08-07 validation measured roughly 1.6M raw tokens for a complete
  Map→Engine→Map circle versus 22.5M for emergent engine work in a free-form
  agentic session;
- the old corpus project showed that parser confidence did not imply runtime
  execution: more than a thousand ability instances were found in
  parse-but-inert classes;
- the phase.rs observation showed strong project programming rules and fresh
  review, but its planning/review workflow consumed about 12M raw input tokens
  before implementation, mostly repeated cached context.

Decision incorporated into this draft:

- preserve the seven-stage code/model/code workflow as the NG default;
- aim for one semantic model call plus focused gate-driven repair, not a
  seven-conversation agent workflow;
- define the corpus as the versioned truth and measurement surface;
- report `recognized`, `expressible`, and `playable` separately;
- make root-cause scope manifests, predicted unlock, and residual accounting
  prerequisites for ticket closure;
- use project Skills as binding programming contracts, while moving every
  checkable instruction into mechanical enforcement;
- keep fresh author/reviewer separation for risky work, but feed the reviewer a
  compact ticket, diff, test evidence, and standards pack rather than replaying
  the full exploration context.
