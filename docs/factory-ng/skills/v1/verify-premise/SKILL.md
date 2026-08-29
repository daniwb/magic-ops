---
name: verify-premise
description: Prove or reject a TicketSpec's code and corpus premise without editing source.
---

Read the exact pinned paths, hashes, examples, and current behavior. Check for
an existing capability before calling a missing primitive. Measure the complete
member set and partition it as fixed, still same root cause, reclassified, or
unsupported. Return `VERIFIED`, `SPLIT_REQUIRED`, `STALE`, or
`NEEDS_PRIMITIVE` with evidence. No source edits, tickets, queue updates, or
integration occur in this Skill.
