# TicketSpec v1 normative guide

Machine JSON and the schemas in `schemas/` are authoritative. JSON is UTF-8,
key-sorted, compact, newline-terminated. All hashes use SHA-256 over that form.

Ticket identity hashes project, repository, explicit work type, root mission,
structured root cause/required behavior, immutable scope hash, and every pinned
source/policy/adapter/analyzer/Skill hash. It intentionally excludes title,
free text, model, priority, and member order (members are sorted before hashing).
An identical identity in open or historical tickets is rejected.

`map` and `engine` are distinct enum values and routing contracts. Readiness is
forbidden for stale premises, quarantine, heuristic-only required evidence,
mixed behavior, unknown dependencies, incomplete scope, or duplicate identity.
Graph edges are typed and a cycle is invalid. Scope membership is creation-time
immutable; predicted unlock is separate. Completion is an exhaustive disjoint
partition of original scope. Unsupported is accounted, never called fixed.

Lifecycle states are `candidate`, `ready`, `claimed`, `running`, `review`, and
terminal `complete`, `refused`, `blocked`, or authorized `cancelled`. Attempts
preserve work at budget boundaries: 200k effective tokens is the target; 500k
creates a checkpoint and reflection, never destructive automatic stopping.

IDs prefixed `ticket:` are hashes of identity material; `sha256:` fields are
content hashes. Assertion locators bind an exact line/span within a semantic
revision. Relations are `not_required` for this single-face predicate.
