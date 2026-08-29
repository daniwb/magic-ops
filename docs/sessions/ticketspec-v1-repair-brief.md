# Factory NG TicketSpec v1 Repair — Dedicated Session Brief

Status: ready for a separate Codex session  
Output: `/opt/development/magic-ops/docs/sessions/ticketspec-v1-repair/`  
Mode: deterministic repair and read-only compilation; no production mutation

## Mission

Repair the rejected TicketSpec/compiler prototype until it emits one Map
ticket whose lifecycle is determined by mechanical readiness checks. Preserve
the first prototype byte-for-byte. Do not broaden corpus research, implement
the Map change, invoke a worker, or run model stages 4–7.

The repaired compiler must run the current Magic parser on full pinned Oracle
text, inventory every assertion and gap, bind real evidence and executable
gates, and emit `ready` only if every readiness predicate passes. Otherwise it
must emit an honest `candidate` or `blocked` ticket with typed reasons.

Read completely before acting:

- `/opt/development/magic-ops/AGENTS.md`
- `/opt/development/magic-ops/docs/factory-ng-plan.md`
- `/opt/development/magic-ops/docs/sessions/ticketspec-v1-brief.md`
- `/opt/development/magic-ops/docs/sessions/ticketspec-v1/architecture-review.md`
- `/opt/development/magic-ops/docs/sessions/ticketspec-v1/`
- `/opt/development/magic-ops/docs/sessions/corpus-contract/architecture-review.md`
- `/opt/development/magic-ops/docs/sessions/oracle-face-snapshot/architecture-review.md`
- `/opt/development/magic-ops/docs/sessions/oracle-face-snapshot/schema.md`
- current parser and focused tests in
  `/opt/development/test/openmagic/scripts/paragraph/`
- relevant Engine code, converter/registry paths, and tests in
  `/opt/development/magic-new/backend/`

If a Skill for creating Skills is available, use it before creating the
required session-local Skill artifact.

## Candidate to reproduce, not presume

Retain the existing family unless real analysis disproves it:

- selected assertion: `Target player draws two cards.`;
- positive faces: Inspiration and Comparative Analysis (resolve their complete
  Oracle IDs from pinned data);
- observed Inspiration result to reproduce:
  `verb_unmapped:p_draw target player draws two cards.`;
- Comparative Analysis also contains Surge, so it is not a predicted
  whole-face unlock unless analysis proves all its other assertions succeed.

These are investigation inputs, not accepted output facts.

## Required repair

### Real analyzer adapter

Implement a deterministic read-only adapter over the current paragraph parser.
It must accept full Oracle text and semantic-face metadata directly, including
faces absent from carddb. It may not replace the parser with an exact-line
regex. Pin the adapter and analyzer bytes.

For every positive member emit its full semantic-source hash, full-source UTF-8
byte spans, every assertion/clause in source order, every parser outcome, and
the complete before-state gap set. Include actual analyzer output for both
faces.

### Distinct scope calculations

Calculate and preserve three independent sets:

- `root_cause_scope`: all faces containing the selected homogeneous miss;
- `sole_blocker_members`: faces whose complete gap set is exactly that miss;
- `predicted_whole_face_unlock_members`: faces predicted to reach the declared
  successful face state after only this change.

Never infer one set from another. If only Inspiration is a proven sole blocker,
predicted whole-face unlock is one even when root-cause scope contains both.

### Content-addressed evidence

Replace synthetic labels and prose claims with receipts:

- hash the complete projection descriptor, membership, and policy artifacts;
- record repository commit, relevant dirty-state policy, and hashes of every
  inspected file;
- hash actual adapter, analyzer, and policy files;
- make the Engine receipt name exact files, symbols, hashes,
  converter/registry reachability evidence, and a runnable target-player draw
  behavior test;
- create an actual versioned session-local Map `SKILL.md` and hash its bytes
  plus referenced resources.

The Skill is a binding worker contract: inputs, allowed/prohibited paths,
decision/refusal schema, constrained patch behavior, required tests,
split/reflection rules, and prohibition on inventing Engine capability inside
Map work. Do not install it as a production Skill in this session.

### Executable gates

Every gate must have a runnable non-placeholder command, expected result, and
evidence location. Specify:

- schema/hash/DAG/history validation;
- focused reproduction for every root-scope member;
- discriminating positive and adjacent-negative parser tests;
- Engine target-player draw behavior test;
- honesty check that prohibited Engine files remain unchanged;
- relevant regression suite;
- immutable-scope remeasurement and exhaustive result partition validation.

Run all creation-time gates. Patch-dependent gates remain pending, but their
commands and success contracts must already be complete.

### Strong schemas and validators

Repair all artifacts with JSON Schema Draft 2020-12, typed `$defs`/`$ref`,
required readiness fields, enums/formats, and
`additionalProperties: false` unless extension is explicit. Validate ticket,
work profile, attempt policy, gates, graph, scope, finding/root cause, evidence
pack, workflow, readiness, and result partition.

Do not fall back to schema-ID checks if `jsonschema` is unavailable; fail with
a typed dependency error. Cross-artifact validation must enforce hashes,
member conservation, graph references, lifecycle consistency, and readiness.

### Identity, history, and graph

- hash the complete normative ticket identity; exclude presentation, priority,
  model selection, and member ordering;
- validate the entire digest, not a prefix;
- use a persistent immutable open/history ledger fixture and prove a second
  equivalent compile creates no duplicate work;
- model the root/main mission as a typed node linked to the Map ticket by a
  typed edge;
- validate references, edge policy, and acyclicity.

### Exact negative tests

Every invalid fixture must fail for its named machine error code. Cover stale
premise, mixed behavior, incomplete assertion/gap inventory, invalid source
span, missing/mismatched receipt, projection member substitution at unchanged
count, missing/synthetic Skill, duplicate historical identity, ambiguous work
type, missing root edge, dangling edge, cycle, and `ready` with an unsatisfied
predicate. Prove byte-identical clean equivalent runs.

## Lifecycle and hybrid routing contract

Compilation begins at `candidate`. One readiness evaluator may change it to
`ready` only after every premise, schema, evidence, scope, graph, history,
quarantine/relation, Engine, Skill, and pre-model gate predicate passes. Persist
all evaluator results and reason codes. No other path may assign `ready`.

Ticket evidence and work requirements must be model-independent. Add a pending
routing descriptor for the later debug run with this sequence:

1. deterministic code prepares facts, scope, baseline, and receipts;
2. local AI may compress, classify, explain, or propose a plan;
3. deterministic checks verify local-AI output before it becomes trusted input;
4. a routed capable model performs semantic decision and constrained
   implementation;
5. deterministic code applies gates and remeasures the full scope;
6. local AI may prepare a focused failure/correction capsule;
7. expensive AI is recalled only for unresolved correction or reflection.

Keep local and online token usage separately measurable: input, output, cache
read, cache write, effective total, wall time, model, attempt, and stage. The
200k effective-token value is a target; 500k creates a warning and reflection,
never destructive cancellation. Reflection may conclude that continued work
is necessary.

Local-AI statements remain advisory until verified. Routing selects a model
from ticket difficulty, uncertainty, risk, required capabilities, and observed
attempt history—not merely from the Map/Engine label.

This session only implements and executes deterministic creation-time work in
stages 1–3. Do not execute the pending AI route.

## Required artifacts

Write only beneath the repair output:

- `report.md` with reproduced findings and lifecycle verdict;
- `schemas/`, `schema-guide.md`, and `compiler/`;
- `skills/<name>/SKILL.md` and only required resources;
- `inputs/` with pinned descriptors/receipts or content-addressed links;
- `outputs/{ticket,scope,graph,evidence-pack,workflow,readiness,result-partition}.json`;
- `fixtures/valid/`, `fixtures/invalid/`, and immutable history fixtures;
- `test-results.json` with commands, exits, and named assertions;
- `open-questions.md` containing only genuinely unresolved decisions;
- `manifest.json` with all hashes, repository state, rerun commands, status,
  and proof of no production mutation.

Manifest status is `complete`, `incomplete`, or `blocked`; ticket lifecycle is
independently `candidate`, `ready`, or `blocked`. A complete repair may
correctly produce a candidate or blocked ticket.

End with:

`READY_FOR_TICKETSPEC_REPAIR_ARCHITECTURE_REVIEW`

## Boundaries

- Preserve `/docs/sessions/ticketspec-v1/` byte-for-byte.
- Do not modify canonical NG docs, production repositories, installed Skills,
  branches, dispatcher/tickets/workers, services, or databases.
- Do not install dependencies globally.
- Do not implement the Map fix or invoke a model worker.
- Preserve accepted corpus semantics and unrelated dirty worktrees.

## Return path

Return here and request review/reflow of:

`/opt/development/magic-ops/docs/sessions/ticketspec-v1-repair/`
