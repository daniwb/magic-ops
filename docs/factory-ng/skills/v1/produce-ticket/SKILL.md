---
name: produce-ticket
description: Compile one atomic Factory NG TicketSpec from current deterministic evidence.
---

Input: pinned source revision, exact corpus/member inventory, legacy provenance if any.

Refuse a ticket with more than one independently testable root cause, stale
evidence, missing adjacent negatives, or no bounded allowed-path set. Emit one
TicketSpec with DAG parents, source hashes, required behavior, profile route,
token warning, and gates. Deduplicate against existing TicketSpec IDs and
legacy provenance. Deterministic evidence is authoritative; AI may summarize
but cannot invent membership or readiness.

Success: rerunning unchanged input emits no additional ready ticket.
