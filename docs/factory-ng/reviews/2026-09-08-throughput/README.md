# Factory throughput review — September 8, 2026

Read-only production investigation and design discussion. No workers, policy,
gates, source, integrations, or deployments were changed. These files are
analysis artifacts, not new operating instructions.

The user's desired sustained output is at least 100 cards/day, preferably
400+, with ordinary ticket work around or below 200k–500k tokens. This review
does not turn the existing non-destructive token thresholds into hard stops.

## Measurements

Dashboard data captured at approximately 12:42 UTC. Attempt and integration
window: September 7 12:42:22 through September 8 12:42:22 UTC. Receipt times
are not necessarily completion times. Live file reads are not transactional.

- 3,924 TicketSpecs: 2,070 Map, 1,850 Engine, four evidence.
- 4,432 observation receipts; 468 non-superseded integration receipts.
- 3,917 jobs including superseded history. Excluding explicitly superseded
  jobs: 1,096 failed, 800 blocked, 437 completed, 230 parked, 239 queued,
  51 integration_failed, one working.
- Corpus `auto`: 12,476; approximately 24-hour change +65. September 7's
  first/last retained samples are 12,400/12,476. All September 8 samples
  examined remain at 12,476. These are sampled classification counts, not
  an independent semantic audit or proof of live deployment.
- 197 attempts across 160 distinct tickets in the window; 61 accepted,
  77 gate_failed, 38 infrastructure_failed, four model-protocol failures,
  nine capability-blocked, seven parked, one invalid capability demand.
- 36 successful integration receipts cover 85 distinct tickets: 79 Engine,
  six Map. Some were accepted before this window. Four additional integration
  receipts have no integratable candidates. Integration parents contain both
  ticket IDs and receipt paths; counting all parents would double this result.
- Integration receipts exclude 34 candidate occurrences for semantic/gate
  failure and 16 for conflict. These are occurrences, not unique unresolved
  jobs. The 51 currently unresolved integration failures comprise 37
  full_gate_failed and 14 candidate_conflict.

| Route | Attempts | Accepted candidates | Acceptance | Recorded model-call hours | Median raw processed tokens |
|---|---:|---:|---:|---:|---:|
| Claude agentic | 38 | 24 | 63.2% | 2.35 | 1,541,368 |
| Claude staged | 42 | 24 | 57.1% | 2.55 | 92,016 |
| Qwen prepared Map | 28 | 7 | 25.0% | 2.10 | 9,739 |
| Qwen agentic Engine | 87 | 6 | 6.9% | 17.28 | 657,857 |

Two operator recovery observations are outside the route table. One Qwen
Engine observation lacks numeric token telemetry. These are different ticket
mixes and profiles, not a randomized comparison of model ability. Model-call
time excludes some preparation, gates, integration and waiting. Success means
accepted candidate, not newly correct card.

Raw processed tokens above include repeated cached input. They are not
monetary cost, subscription quota consumption, or normalized effective tokens.
The inspected remote Engine runner records uncached input separately from
cache reads/writes. The prepared Qwen Map runner already includes cache reads
in input_tokens, so those must not be added twice. A naive input+output
median is only 33,542 across recent numeric receipts and hides 119 million
reported cache-read tokens and 4.58 million cache-write tokens in the window.
Older adapter conventions and missing/zero telemetry need separate treatment.

## Structural evidence

Of the 126 distinct Engine tickets attempted in the window, 85 declare an
expected unlock of one, 29 declare zero, ten declare larger values and two
omit it. These declarations are not a measured corpus-wide marginal yield.
Across all Engine TicketSpecs including versions, 1,176 of 1,850 declare one.

137 of the recent 197 attempts use tickets pinned to commit `1aecc4b9`, dated
September 6 10:44 UTC. Pins support reproducibility but old queued work is
expensive to compose against moving main. A concrete September 8 trace:
Qwen's self-pump candidate passes its named behavior and package tests, then
fails to apply to current `ability_effects.go`. Evidence:
`../../runs/2026-09-08T113321Z-engine-auto-pump-until-eot-ability-self-no-target-9e24f96767-v1-integration.json`.

34 of the 38 Qwen Engine infrastructure_failed observations first report
`no edit blocks and no verdict found in model output`. This is evidence of
an unusable model response; the outcome label alone does not establish an
external infrastructure outage. Gate failure categories also overlap across
initial and repaired attempts, so they must not be treated as disjoint causes
without classifying the final candidate.

Current source sizes: reparse.py 21,027 lines; ability_effects.go 12,348;
gamestate.go 6,412; converter.go 3,649. GameState already contains event
subscriptions and turn-history counters. A shared history/query interface
would therefore consolidate existing behavior, not start from an empty engine.
File size is evidence of discovery/integration surface, not a correctness test.

## Dashboard

The HTML shell returns in 1.7 ms. `/factory-ng/data` takes 10.936 seconds and
returns 21,484,317 bytes in one local measurement. The handler launches
factory-ng-dashboard.py per request. That script scans all tickets, reads
the runs directory separately for observations and integrations, and rehashes
ticket files for binding checks. The directory contains about 10,904 JSON
files, including artifacts that are not receipts.

The page fetches this data every 30 seconds, rebuilds every attempt row and
the full ticket selector, and includes gate details in the transferred data.
Its problem KPI still filters unresolved problems to the last hour; its
control-loop health badge is based on controller running state. This can
disagree with the watchdog's persistent failure report.

A small SQLite index, incrementally updated from immutable artifacts, is a
suitable proposal: indexed current states and relationships, aggregate API
responses, paginated history, details loaded on demand. Keep one definition
of each metric and a rebuild path. This would change the documented no-ticket-
database implementation choice; it is proposed here, not activated.
SQLite documents this application/file-analysis use case at
https://www.sqlite.org/whentouse.html.

## Statistics that should become durable

Measure three levels separately: provider call/attempt, immutable ticket
version, and complete card/capability mission including successors and repairs.
The present exported summaries do not establish exact mission-level yield.

Record all raw provider counters with adapter convention/version; normalized
uncached/cached/output counts; explicit effective-token formula; cost where
available; model, preparation, gate and waiting time; final failure class;
source age; actual card identity transitions at each landed revision; and
dependencies still preventing a card from becoming usable. Keep historical
failures, current unresolved failures and superseded work distinct.

Primary outcomes: net independently verified cards/day, successful complete
missions/day, total mission tokens per newly enabled card, and latency to a
usable card. Add capability reuse and forecast-versus-realized card yield.
Report seven-day results and representative ticket classes, because one-day
recovery waves and changing difficulty distort comparisons.

## Suggested decision experiment

Avoid making another factory rewrite a prerequisite. Select a frozen,
representative cohort of 30 currently blocked cards, divided among existing-
capability composition, real history/quantity gaps, and unusual card behavior.
Compare the current path against direct card recipes or isolated handlers
using a small, documented engine interface. Use equivalent independent
behavior checks and the unchanged full integration gates. This is a proposed
deliberate benchmark, not authorization to dispatch duplicate production work.

Count the interface/setup cost, every failed attempt, repair and successor,
and actual enabled cards. First prove low cost on the cohort, then use unseen
cards to test reuse, then observe sustained output across a complete quota
week. A successful demo alone does not establish 100 or 400 cards/day.

The architecture hypothesis is to permit local implementations while keeping
game-wide authority for events, choices, zones, costs and continuous effects
shared. Extract repeated behavior incrementally after concrete examples;
defer neither integration nor correctness to a final big refactor. An offline
Oracle-to-existing-representation compiler could remove parser-rule changes
from ordinary card authoring, with explicit single ownership and Oracle-text
versioning for each recipe. Its savings remain unproven until measured.

## Exports and limitations

- `tickets.csv`: every captured TicketSpec, job state, versions/parents,
  declared yield, attempt totals, reported token sums and integration count.
- `attempts.csv`: all captured observation receipts with raw counters and
  a raw-processed estimate for inspected current adapter conventions.
- `summary.json`: all-history totals, daily attempt outcomes, recent profiles,
  gate duration totals, source cohorts and version-lineage counts.

Unknown usage remains blank in attempt exports; ticket sums include numeric
observations only and expose their availability count. Raw cost estimates for
historical runs are provisional because adapters changed. No sum of parent
and child yields should be interpreted as unique cards. The source dashboard
snapshot SHA-256 is preserved in summary.json; raw source artifacts remain
under docs/factory-ng/tickets and runs. No new production tests were run for
this read-only review; export row counts were checked against the snapshot.
