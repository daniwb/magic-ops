# Factory NG CorpusSnapshot v1 — Dedicated Session Brief

Status: ready for a separate Codex session  
Owner of final decisions: Factory NG architecture chat  
Output directory: `/opt/development/magic-ops/docs/sessions/corpus-snapshot/`

## Mission

Design and run a read-only `CorpusSnapshot v1` prototype that gives the
architecture session measured evidence for choosing Magic's population and
source-unit identity policies.

First read completely:

- `/opt/development/magic-ops/AGENTS.md`
- `/opt/development/magic-ops/docs/sessions/corpus-contract/architecture-review.md`
- `/opt/development/magic-ops/docs/sessions/corpus-contract/contract.md`
- `/opt/development/magic-ops/docs/sessions/corpus-contract/metrics.md`
- `/opt/development/magic-ops/docs/factory-ng-plan.md`

Treat the architecture review as authoritative when it differs from the
original corpus-session proposal.

## Required experiment

Compile and compare at least these versioned population-policy candidates from
the pinned MTGJSON corpus:

1. the current classifier-compatible population;
2. all non-funny source faces supported by the upstream schema, including
   digital/rebalanced content as a separately visible dimension;
3. a paper/product-oriented population with every exclusion expressed as a
   stable reason code.

Do not silently decide ambiguous inclusions. Show counts and examples by
layout, type, legality, digital/rebalanced status, and exclusion reason. Include
parent-card rollups alongside primary face counts.

Test the proposed `scryfallOracleId + side` source identity for:

- missing values;
- duplicates/collisions;
- multi-face correctness;
- identical Oracle IDs appearing in unexpected parent groups;
- stability implications for renamed or revised Oracle objects;
- deterministic fallback identity requirements.

Generate canonical manifests for each candidate policy and prove that a second
run over identical inputs is byte-identical. Record raw corpus hash, policy and
normalizer hashes, member count, sorted member-manifest hash, and repository
state. The prototype may write scripts and artifacts only inside the output
directory; it must not modify production source or canonical Factory NG docs.

## Boundaries

- Read-only with respect to production repositories and services.
- Do not mutate dispatcher tickets, workers, branches, services, or databases.
- Do not calculate or claim recognized, expressible, or playable coverage.
- Do not build TicketSpec or generate production tickets.
- Do not resolve population policy by preference; preserve tradeoffs.
- Do not use card name or unstable array position as source identity.
- Keep full machine-readable member manifests; Markdown examples are views.
- Use bounded command output and record exact measurement commands.

## Required artifacts

Write all of these under the output directory:

- `report.md` — evidence, comparisons, anomalies, and recommendation;
- `policy-comparison.json` — exact counts and breakdowns for every candidate;
- `identity-audit.json` — missing IDs, collisions, multi-face findings, and
  fallback cases;
- `schema.md` — proposed `CorpusSnapshot v1` descriptor and member schema;
- `open-questions.md` — decisions still requiring architecture review;
- `prototype/` — bounded deterministic generator/validator used by the run;
- `manifests/` — canonical candidate descriptors and complete member manifests;
- `manifest.json` — session provenance, source SHAs/hashes, artifact hashes,
  commands, reproducibility result, and session status.

The top-level `manifest.json` status is one of `complete`, `incomplete`, or
`blocked`. Do not edit the previous corpus-contract artifacts or
`docs/factory-ng-plan.md`.

End the session with a short artifact summary and the exact sentence:

`READY_FOR_SNAPSHOT_ARCHITECTURE_REVIEW`

## Return path

The user returns to the Factory NG architecture chat and asks it to review
`/opt/development/magic-ops/docs/sessions/corpus-snapshot/`. That chat verifies
hashes and reproducibility, resolves policy decisions with the user, and
reflows accepted conclusions into the canonical plan.
