# TicketSpec v1 repair schema guide

All machine artifacts use canonical UTF-8, sorted-key, compact JSON with a trailing newline and JSON Schema Draft 2020-12. Schemas are closed with `additionalProperties: false`; shared hashes, lifecycle states, and immutable member shapes live in `$defs` and are referenced with `$ref`.

The ticket is the lifecycle envelope. Scope separately records root-cause, sole-blocker, and predicted-whole-face-unlock sets. Evidence contains actual full-text analyzer outputs and content receipts. Graph links a typed root mission to the Map ticket. Readiness records every predicate and is the sole authority for a `candidate` to become `ready`. Result partition conserves the immutable root scope and remains pending until a patch exists. Work-profile, attempt-policy, gate, finding, and root-cause schemas validate their typed embedded or standalone contracts.
