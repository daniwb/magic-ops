# Factory NG Corpus Contract — Dedicated Session Brief

Status: ready for a separate Codex session  
Owner of final decisions: Factory NG architecture chat  
Output directory: `/opt/development/magic-ops/docs/sessions/corpus-contract/`

## Mission

Define the project-level corpus contract that lets Factory NG produce truthful
Map and Engine tickets. Investigate the existing Magic corpus, classifiers,
coverage/audit tools, card representation, executors, tests, and historical
factory documents. Use phase.rs only as comparative evidence; do not copy its
workflow or design by default.

Answer these questions with repository evidence:

1. What is the authoritative corpus unit and snapshot identity?
2. What exactly do `recognized`, `expressible`, and `playable` mean?
3. How are silent loss, parsed-but-inert behavior, and partial support detected?
4. How are failures normalized into stable root causes without losing members?
5. How are co-occurring gaps, marginal unlock, and dependency bundles computed?
6. What immutable scope manifest must every root ticket contain?
7. What before/after evidence proves a Map or Engine ticket succeeded?
8. Which existing tools can be retained, repaired, or retired?
9. Which statements remain assumptions requiring measurement?

## Boundaries

- Research and design only; do not implement the new factory.
- Do not mutate dispatcher tickets, workers, services, branches, or production.
- Do not treat parser success as playability.
- Do not use an LLM as the sole authority for identity, counts, or closure.
- Do not propose arbitrary card-count batches as tickets.
- Preserve disagreements and unknowns in `open-questions.md`.
- Prefer bounded command output and record commands that establish key counts.

## Required artifacts

Write all six files before declaring the session complete:

- `report.md`
- `contract.md`
- `metrics.md`
- `ticket-examples.md`
- `open-questions.md`
- `manifest.json`

`manifest.json` must record the Magic and magic-ops SHAs, corpus identity/hash,
artifact hashes, important commands, and one status:
`complete`, `incomplete`, or `blocked`.

Do not edit `docs/factory-ng-plan.md`. End the session with a short summary of
the artifacts and the exact sentence:

`READY_FOR_ARCHITECTURE_REVIEW`

## Return path

The user returns to the Factory NG architecture chat and asks it to review
`/opt/development/magic-ops/docs/sessions/corpus-contract/`. That chat verifies
the manifest and evidence, discusses material open questions with the user, and
then reflows accepted conclusions into the canonical NG plan and specifications.
