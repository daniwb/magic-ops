# Multi-miss admission

The user requested general work on cards with multiple unresolved phrases.
Ordinary discovery previously required one miss. The only exception admitted
exactly two misses of the same family and stopped at two blocked Map parents.
Both pilot parents had unsuccessful Engine dependencies, so the exception
could not supply further work.

The enabled `build-plan-multi-miss` producer replaces that pilot. It admits
**two through six current parser misses**, including different supported verb
families. All misses must have explicit family-to-runtime mappings and registry
evidence. Cards with unknown/static/replacement catch-all misses or more than
six misses remain outside this lane. This expands admission; it does not
weaken complete-card acceptance.

The normal runnable reserve and queue cap bound production. Blocked historical
parents no longer consume a permanent two-card pilot allowance. Scans retain
an independent cursor and reuse revision/card-keyed parse results, then reparse
the exact candidate and check source identity before publication.

Every ticket records all miss occurrences, all participating families, their
runtime evidence and complete Oracle text. It requires tests for each clause
and their combined behavior. Runtime gaps still generate one validated atomic
Engine dependency at a time. Map resumes retain the original scope, full-card
gates and obligations, along with the updated remaining-miss inventory.

The existing Oracle-text production identity prevents reopening old tickets
under a multi-miss label. A multi-miss lineage also prevents a fresh single-miss
ticket after dependencies change its remaining family/count. Existing repair
budgets and failed receipts remain intact. No worker, quota, integration gate,
deployment or work-schedule policy changed.

## Measurement and validation

`census.json` pins source revision
`4e545cebc439944937540dc269cd86a8780a0911`. It contains 113 candidate cards,
representing 112 distinct Oracle-text production keys. There are 95 cards with
two mixed-family misses, 13 with two same-family misses, four with three mixed
misses, and one with four mixed misses. These are candidate counts, not
completed-card yields. Admission always revalidates current source and history.

121 regressions passed across multi-miss, control, frontier, scan performance,
reliability and stale-supply recovery. Both actual worker harnesses reject a
pinned fixture whose headline miss is resolved while another family remains,
reject a miss migrated to another category, and accept the complete fixture.
Other cases cover 2–6 misses, unsupported families, duplicate prevention,
source-cache changes, retained dependency obligations and blocked pilot roots.
Two pre-existing timeout/stop tests now isolate their schedule dependency so
they can run during the separately configured quiet hours.

Actual pinned-source examples passed preparation, both staged/Codex packet
builders, isolated queue publication and assignment to three distinct workers:

| Card | Misses | Families |
| --- | ---: | --- |
| Angel of Serenity | 2 | bounce, exile |
| Abyssal Harvester | 3 | exile, token_copy |
| Gargantuan Gorilla | 4 | damage, damage_by, grant_eot, sacrifice |

`preflight-results.json` records these checks. They start no provider or worker
process and claim no accepted or integrated card changes.

## Activation

The producer configuration was replaced atomically under `dispatcher-admin`.
A fresh controller-module read resolved the enabled command with
`--lane fresh --max-misses 6` and the September 14 measurement. A read-only
probe of that configured producer offered Applied Geometry, with put_counters
and token_copy misses. No manual live queue entries were created.

The separately requested work window remains **22:00–07:00 Europe/Zurich**.
Activation happened during quiet hours, so live production/dispatch proof must
wait for the next allowed window; no provider call bypassed the schedule.
Existing integration work continued under its own scoped lock. No game-source
edits or live deployment were performed by this change.

`activation.json` records configuration and runtime state. `implementation.patch`
contains this task's changes relative to the pre-existing working tree; it
preserves concurrent quiet-hours work and earlier supply recovery changes.
