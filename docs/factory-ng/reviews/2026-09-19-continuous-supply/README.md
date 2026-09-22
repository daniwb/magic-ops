# Continuous supply activation — 2026-09-19

The user's request covers immediate restoration, durable discovery, fitting work
at the head of the queue and cold archival of finished tickets.

## Diagnosis

The 2–6-miss lane was enabled, but every miss had to belong to an explicitly
supported verb with a registered runtime effect. Fixed static/recovery cohorts
were also exhausted. A full current-source scan found zero fresh candidates
under those rules, despite 16,392 review records. The controller's queue was
empty with target eight and cap twelve. Repeated historical processing and
larger queue limits could not change those admission decisions.

## Active changes

- A current-corpus fallback scans every review miss family and ranks fresh
  whole-card tasks with one through six misses. The SQLite measurement cache
  resumes bounded slices and invalidates on relevant parser/corpus inputs.
  Only the small ready reserve becomes TicketSpecs; the remaining ~15,000
  candidates are indexed demand.
- Exact Oracle evidence and complete-card gates remain mandatory. Staged Map
  workers must prove runtime reachability or produce a validated atomic Engine
  demand. Proven compilers run before general investigation. Engine foundations
  and Map resumes take dispatch precedence over further investigation.
- The ranking favors smaller parser seams, fewer misses, exact-detail reuse
  and shorter Oracle text; major subsystem keywords receive a higher complexity
  estimate. One active exact miss signature prevents parallel duplicate shape
  work. Existing card/text lineage prevents fresh-ID retries.
- Completed and terminal superseded jobs move to immutable full job archives,
  with compact compatibility tombstones and existing artifact paths retained.
  More than 5,900 jobs archived. Reconciliation skips their lifecycle work and
  cached immutable artifact stat checks. Dispatch sorts ready jobs only.
- Runtime status exposes the ranked supply summary and archived-job count.
  Seven over-bound cards and six ineligible/no-miss records have explicit
  blockers. Existing failed histories do not automatically gain new attempts.

## Verification and live evidence

128 tests pass across corpus-frontier, archive, producer-performance, control,
recovery and attention-recovery suites. Four control-test paths were relocated
from the absent `/opt/development` checkout to the shared source-path helper.
The initial real TicketSpec also successfully compiled through the actual Map
packet builder before activation.

The initial task, `ticket:map.frontier-f7bcf6a38043/v1` (Tunnel), passed focused
tests, complete-card measurement, build and the full six-shard suite. Its wave
flipped 22 cards and pushed `cf353e719c02f2aa40aa364d35b2b08796188b65` under
unchanged automatic integration policy; no deployment. The complete receipt is
[the integration receipt](../../runs/2026-09-19T080900Z-map-frontier-f7bcf6a38043-v1-1789805340327686200-integration.json).
The updated source was automatically remeasured, and newly available work was
also emitted by the original proven build-plan compiler. Live reserve has
remained around 7–9 tickets as workers claim work and producers refill it.

Controller reloaded gracefully under dispatcher-admin serialization, preserving
worker/integration processes. The watchdog raced one supervisor restart and
created a redundant launcher; the single-controller process lock prevented
duplicate reconciliation. The redundant idle launcher was stopped by its
verified PID, retaining the active controller and workers.

## Limits and next intervention conditions

### Later correction: deferred frontier overflow

The morning reserve observation did not hold when remote workers reached quota
holds. Frontier contracts explicitly admit only Codex/Claude investigation
profiles, while the controller counted runnable rather than all pending supply.
An available Qwen worker therefore triggered additional production without
being eligible to claim those contracts, accumulating roughly 1,950 deferred
tickets. This is a routing/admission defect, not evidence of model inability.

Frontier admission now counts all pending frontier work, including deferred
and backlogged contracts. The controller retains only the highest-ranked
unattempted contracts within the configured queue cap and preserves overflow
as reversible `backlog`, promoting it as queue slots open. Attempted work,
receipts, quotas and profile contracts are unchanged. Four reserve regression
tests and the related frontier/archive/controller/performance suites passed
(105 tests). This correction bounds inventory; it does not qualify Qwen for
frontier investigation or remove the remote quota holds.

This is an operating supply improvement, not evidence that every candidate is
implementable or that all failed semantic histories have been repaired. The
system retains whole-card gates, bounded retry budgets and explicit blocked
demand. Over-bound tasks need decomposition or relevant shared capabilities;
unexplained eligibility needs diagnosis. See `state/factory-ng-frontier.json`
and RUNBOOK for current dispositions. No queue size can honestly substitute for
those unresolved contracts, and exhaustion must never be reported as completion.
