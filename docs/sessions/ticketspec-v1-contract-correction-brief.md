# Factory NG TicketSpec v1 Contract Correction — Dedicated Session Brief

Status: ready for a separate Codex session  
Output: `/opt/development/magic-ops/docs/sessions/ticketspec-v1-contract-correction/`  
Mode: deterministic contract correction and adversarial tests; no model stages

## Mission

Produce the first mechanically trustworthy TicketSpec v1 bundle by correcting
only the blockers recorded in
`docs/sessions/ticketspec-v1-repair/architecture-review.md`. Preserve both
earlier prototypes byte-for-byte. Reuse their accepted corpus, parser, scope,
identity, graph, Skill, routing, and budget decisions; do not restart corpus
research or implement the Map change.

The output may be `ready`, `candidate`, or `blocked`. `ready` is permitted only
when one evaluator derives every predicate from validated receipts produced by
actual commands. A green self-authored literal is not evidence.

Read completely before acting:

- `AGENTS.md` and its required canonical memory;
- `docs/factory-ng-plan.md`;
- `docs/sessions/ticketspec-v1-repair-brief.md`;
- `docs/sessions/ticketspec-v1-repair/architecture-review.md`;
- all non-cache files under `docs/sessions/ticketspec-v1-repair/`;
- accepted corpus and Oracle-face architecture reviews referenced by the plan;
- current parser and relevant Engine source/tests.

## Immutable inputs and boundaries

- Treat `docs/sessions/ticketspec-v1/` and
  `docs/sessions/ticketspec-v1-repair/` as immutable inputs and prove both trees
  byte-identical before/after.
- Write authored artifacts only beneath the correction output directory.
- Do not change production parser/Engine code, tickets, dispatcher, workers,
  services, databases, installed Skills, branches, or commits.
- A session-local Go test may be injected into `go test` with `-overlay` or run
  from an isolated temporary copy. It must not be copied into a production
  repository. Prefer `-overlay` and record the overlay plus test bytes.
- Do not invoke local or online AI workers and do not execute stages 4–7.
- Preserve unrelated dirty worktrees.

## Required corrections

### 1. End-to-end content binding

Recompute and enforce the exact canonical hashes for scope, graph, evidence
pack, projection descriptor and membership, identity, policy, Skill, inspected
files, and every artifact referenced by the ticket. Define explicitly which
fields are excluded from each digest and why. The validator must reject a
well-formed but false hash even when its format is valid.

Add exact-code negative cases for at least:

- `E_SCOPE_HASH_MISMATCH`;
- `E_GRAPH_HASH_MISMATCH`;
- `E_EVIDENCE_PACK_HASH_MISMATCH`;
- `E_PROJECTION_HASH_MISMATCH`;
- `E_IDENTITY_DIGEST`;
- `E_SKILL_RECEIPT_MISMATCH`;
- `E_REPOSITORY_RECEIPT_MISMATCH`;
- `E_ENGINE_RECEIPT_MISMATCH`.

Member substitution, ordering normalization, duplicate identity, and stale
source/file bytes must remain covered.

### 2. One readiness authority

Compilation begins at `candidate` and may not assign `ready`. A single
readiness evaluator consumes schema validation, cross-artifact validation,
history/DAG checks, quarantine/relation policy, and executed creation-gate
receipts. It derives every predicate, reason code, final lifecycle, and the
ticket lifecycle. No caller supplies predicate truth values.

Prove mechanically that:

- an unsatisfied predicate cannot coexist with `ready`;
- removing or forging a receipt changes the derived result;
- compilation alone cannot emit `ready`;
- only the evaluator symbol/path writes the final lifecycle;
- reevaluation from unchanged receipts is deterministic.

### 3. Real Engine behavior proof

Replace the empty-library test evidence with a session-local discriminating Go
test that puts at least two drawable cards into the target player's library,
executes the real `ExecuteAbilityEffect` draw path with a player target, and
asserts that the target draws two while the controller draws zero. The test
must fail if targeting is reverted to the controller. Run it without modifying
the production repository, preferably through Go's `-overlay` facility.

The Engine receipt must bind the test, overlay, exact source files/symbols,
content hashes, repository commit/dirty state, command, exit code, and output
digest. Mechanically verify symbol presence and the claimed converter/executor
path; do not encode the reachability claim only as prose.

### 4. Closed nested schemas

Use JSON Schema Draft 2020-12 with `$defs`/`$ref` and
`additionalProperties: false` for every normative nested structure, including:

- ticket readiness, Skill receipt, work profile, attempt policy, and gates;
- projection and policy;
- graph nodes and typed edges;
- analyses, assertions, parser outcomes, file/repository/Engine receipts;
- readiness predicates and evaluator record;
- workflow stages, routing descriptor, and telemetry dimensions;
- result partitions and their member collections;
- gate execution receipts and manifest records.

Arrays require item schemas, uniqueness/key constraints where applicable, and
meaningful cardinality. Embedded schemas must be referenced from their parent,
not merely validated opportunistically afterward.

### 5. Executed creation-gate receipts

Implement one gate runner. For each creation gate, record at minimum:

- stable gate ID and command digest;
- exact argv/cwd and relevant environment allowlist;
- repository/corpus state;
- start/end timestamps and wall time;
- exit code;
- stdout/stderr content digests and bounded artifact locations;
- derived `passed` or `failed` result.

The compiler may declare required gates but may not declare their result. The
runner executes them; the readiness evaluator consumes only verified runner
receipts. Patch-dependent gates remain declared and `pending` because stages
4–7 have not run.

### 6. Receipt verification

Mechanically validate all file bytes, repository commits and relevant dirty
paths, projection membership/policy, analyzer/parser bytes, Skill bytes and
referenced resources, Engine symbols/test, history ledger, and corpus source.
Define a typed stale-input result. Do not make unrelated dirty files an
automatic failure when their state is recorded and proven outside the ticket's
inspected surface.

### 7. Reproducible finalization

Provide one top-level rerun command that performs compilation, gate execution,
readiness evaluation, validation, tests, and finalization in the correct order.
Separate immutable normative outputs from per-run attempt receipts so real
timestamps do not make ticket identity unstable.

The manifest excludes only its own bytes, hashes every other final artifact,
and is written last. A separate read-only verifier must validate the manifest
after finalization. Running the documented pipeline again must leave normative
outputs byte-identical, create no duplicate history entry, produce a new or
explicitly reused attempt receipt according to the documented policy, and end
with a valid current manifest.

## Adversarial acceptance tests

Tests must mutate one condition at a time and assert the exact named failure.
In addition to all previous repair cases, cover every hash listed above,
forged gate success, mismatched command digest, changed stdout/stderr evidence,
stale repository/file receipt, untyped graph edge, malformed nested object,
duplicate result member, missing result member, direct lifecycle promotion,
and stale manifest bytes.

The test suite must demonstrate that the exact zeroed-`scope_hash` mutation
used by architecture review now fails with `E_SCOPE_HASH_MISMATCH`.

## Required artifacts

Write beneath the correction output:

- `report.md` and `open-questions.md`;
- `schemas/` and a schema guide;
- `compiler/`, including gate runner, sole readiness evaluator, validator,
  finalizer, and manifest verifier;
- `inputs/` with pinned/copy-or-content-addressed immutable inputs;
- `skills/implement-map-class/SKILL.md` copied or revised only if required and
  always content-bound;
- `tests/` including the session-local Engine overlay test;
- `gate-receipts/` with bounded stdout/stderr evidence;
- `outputs/` containing ticket, scope, graph, evidence, workflow, readiness,
  and pending result partition;
- `fixtures/valid/`, `fixtures/invalid/`, and history fixture;
- `test-results.json` and `manifest.json`.

The report must distinguish accepted inherited facts, newly executed facts,
and remaining assumptions. Record token usage for this Codex session if the
environment exposes it; never fabricate unavailable counters.

## Exit criteria

All of the following are required before lifecycle `ready`:

1. all schemas and cross-artifact bindings validate;
2. every creation gate has a verified passing execution receipt;
3. the corrected Engine behavior proof passes;
4. the sole evaluator derives every readiness predicate as satisfied;
5. every adversarial case fails with its expected code;
6. two pipeline runs preserve normative identity and history uniqueness;
7. the final manifest verifier passes;
8. both earlier prototype trees remain byte-identical;
9. model stages 4–7 remain pending and no production mutation occurred.

If any condition fails, emit `candidate` or `blocked` with typed reasons and do
not weaken the condition.

End with:

`READY_FOR_TICKETSPEC_CONTRACT_CORRECTION_ARCHITECTURE_REVIEW`

## Return path

Return to the Factory NG architecture chat and request review/reflow of:

`/opt/development/magic-ops/docs/sessions/ticketspec-v1-contract-correction/`
