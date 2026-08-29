# Factory NG TicketSpec v1 + First Map Compiler — Dedicated Session Brief

Status: ready for a separate Codex session  
Output directory: `/opt/development/magic-ops/docs/sessions/ticketspec-v1/`  
Mode: schema implementation and read-only prototype; no production mutation

## Mission

Define executable, project-independent Factory NG TicketSpec v1 schemas and
build a deterministic read-only Magic adapter/compiler that emits exactly one
validated Map ticket from current measured evidence. Prove idempotence,
scope conservation at creation time, typed Map/Engine separation, graph
validity, and rejection of invalid or ambiguous candidates.

This is not another architecture essay. Produce machine schemas, fixtures,
compiler code, validators, tests, and one compiled ticket artifact.

Read completely before acting:

- `/opt/development/magic-ops/AGENTS.md`
- `/opt/development/magic-ops/docs/factory-ng-plan.md`
- `/opt/development/magic-ops/docs/sessions/corpus-contract/architecture-review.md`
- `/opt/development/magic-ops/docs/sessions/oracle-face-snapshot/architecture-review.md`
- `/opt/development/magic-ops/docs/sessions/oracle-face-snapshot/schema.md`
- `/opt/development/magic-ops/docs/sessions/mtgjson-allprintings/architecture-review.md`
- relevant existing Magic classifiers, `coverage_planner.py`, reparse outputs,
  vocabulary/executor audits, and dispatcher ticket/capability schemas

## Required schema package

Implement JSON Schemas plus concise normative documentation for:

1. `factory.ticket/v1` — reusable ticket lifecycle envelope;
2. `factory.work-profile/v1` — type, difficulty/risk, required capability,
   context/tool requirements, routing constraints, budget targets/warnings;
3. `factory.graph-edge/v1` — typed DAG edges and dependency policy;
4. `factory.attempt-policy/v1` — retries, reflection triggers, terminal/refusal
   verdicts, and non-destructive budget behavior;
5. `factory.gate-requirement/v1` — command/evidence/result contracts;
6. `magic.scope/v1` — immutable Oracle-face/assertion member scope;
7. `magic.finding/v1` and `magic.root-cause/v1` — deterministic candidate
   evidence and homogeneous behavior identity;
8. `magic.result-partition/v1` — exhaustive append-only after-state partitions.

Use explicit schema versions and additional-property policy. IDs and hashes
must be mechanically reproducible. Human Markdown is explanatory only.

## Binding TicketSpec rules

Every compiled ticket must contain or content-address:

- explicit `work_type`; Map and Engine must not share an ambiguous contract;
- project, repository, source snapshot, Oracle inventory, projection, adapter,
  analyzer, policy, and Skill hashes;
- root mission ID and typed graph edges;
- homogeneous structured root-cause and required-behavior hash;
- complete immutable source-admitted Oracle-face member manifest;
- semantic revision hash and relevant assertion/span locator per member;
- quarantine and relation-readiness status;
- exact positive members and adjacent negative fixtures;
- predicted unlock members separately from root-cause scope members;
- complete current gap sets/dependency bundle where measurable;
- allowed/prohibited paths and explicit refusal/split conditions;
- required discriminating, honesty, regression, and remeasurement gates;
- work profile and model-independent routing requirements;
- 200k effective-token target and 500k warning/reflection policy, never a
  destructive automatic stop;
- structured completion evidence and exhaustive result partitions.

Ticket identity must not depend on title, free text, model choice, priority, or
member ordering. A ticket cannot become ready when its premise is stale,
members are quarantined, required evidence is heuristic-only, behavior is
mixed, dependencies are unknown, or the same identity is already open/history.

## First deterministic Map compiler

Inspect current analyzers and choose one reproducible, bounded Map root cause
that:

- is present on the pinned admitted Oracle-face population;
- has a deterministic predicate and complete member recovery;
- is behavior-homogeneous;
- needs no new Engine capability according to evidence, or emits a structured
  blocked dependency rather than pretending otherwise;
- has positive and adjacent-negative examples;
- has measurable baseline and predicted transition;
- is not merely a leading-token/catch-all discovery bucket.

The compiler must:

1. ingest pinned machine evidence and the admitted Oracle-face descriptor;
2. normalize and validate a candidate;
3. reproduce every scope member;
4. reject quarantine/relation-ineligible members when applicable;
5. deduplicate by stable ticket identity;
6. emit one root/main Map ticket, scope manifest, graph manifest, and evidence
   pack descriptor;
7. run twice against identical inputs and create no second identity/artifact
   difference;
8. validate all schemas and hashes;
9. include negative fixtures showing rejection of mixed behavior, stale
   premise, duplicate identity, missing evidence, cycle, ambiguous work type,
   and incomplete scope.

If no current analyzer can produce a trustworthy ticket, do not fabricate one.
Return `blocked` with a precise missing deterministic adapter and implement the
smallest read-only adapter possible within this session. A hand-curated member
list or LLM-only classification does not satisfy the mission.

## Seven-stage trace descriptor

The compiled ticket must contain a pending debug workflow descriptor with:

1. compile/validate ticket;
2. reproduce baseline and materialize scope;
3. build compact evidence/Skill pack;
4. semantic decision or binding refusal;
5. constrained patch plus discriminating test;
6. mechanical apply/gates/full scope remeasurement and focused correction;
7. immutable checkpoint for fresh review/integration.

Do not execute stages 4–7 in this session. The goal is a ticket ready for the
later supervised debug flow.

## Boundaries

- Do not modify production Magic/magic-ops code, dispatcher state, databases,
  services, workers, tickets, branches, or canonical NG documents.
- Prototype code and outputs stay inside the session output directory.
- Do not publish, push, merge, implement the Map change, or invoke a worker.
- Do not claim recognized/expressible/playable coverage beyond pinned evidence.
- Do not import legacy `playable` or parser `auto` as truth.
- Do not use printing-occurrence count as work priority or scope size.
- Preserve unrelated dirty worktrees.

## Required artifacts

Write under the output directory:

- `report.md` — implementation result and architecture findings;
- `schemas/` — all executable JSON Schemas;
- `schema-guide.md` — normative field/identity/lifecycle description;
- `compiler/` — deterministic compiler, validator, and tests;
- `inputs/` — compact pinned evidence/descriptors or content-addressed links;
- `outputs/ticket.json` — exactly one compiled Map ticket;
- `outputs/scope.json` — complete immutable scope or content-addressed member
  artifact plus descriptor;
- `outputs/graph.json`;
- `outputs/evidence-pack.json`;
- `outputs/workflow.json` — pending seven-stage trace descriptor;
- `fixtures/valid/` and `fixtures/invalid/`;
- `test-results.json` — schema, negative, hash, DAG, dedup, and idempotence tests;
- `open-questions.md` — only decisions genuinely still required;
- `manifest.json` — source/artifact hashes, commands, status, rerun evidence,
  and absence of production mutation.

Status is `complete`, `incomplete`, or `blocked`. End with:

`READY_FOR_TICKETSPEC_ARCHITECTURE_REVIEW`

## Return path

The user returns to the Factory NG architecture chat and asks it to review
`/opt/development/magic-ops/docs/sessions/ticketspec-v1/`.
