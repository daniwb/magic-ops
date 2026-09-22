# Factory discovery and dependency handoff repair — September 8

The user authorized the four audited Engine corrections and asked whether
that would fix the factory. Engine behavior alone does not repair production.
This change also addresses two observed preparation/handoff failures.

## Implemented factory changes

1. Capability discovery searches a bounded plan: generated label, up to three
   identifiers explicitly present in the requirement, and the operation name.
   One explicit label fallback is allowed. All requests go through the HTTP
   knowledge service; each request records its purpose. Selection reserves
   room across queries so one noisy result does not crowd out named symbols.
   Broad operation hits remain unverified candidates, not proof of support.
2. Engine packets ask for decomposition into reuse, connection, Engine gap,
   or insufficient evidence, and a public-path verification. An existing
   implementation can be verified with a test-only patch. The runner retains
   assessment claims from initial, continuation and repair responses in
   `capability_assessments`. These claims never replace gates or change states.
3. Dependency Map resumes include the integrated Engine contract and fresh
   symbol evidence. Prepared Map packets now render that Engine source in a
   separate bounded read-only budget, resolved in the actual checkout.
   Previously they only rendered `scripts/` evidence.
4. An ordinary dependency no longer disappears merely because the parser
   reports eligible after the Engine lands. It emits a Map verification
   successor, as integration-recovery dependencies already did, retaining
   the exact Oracle members and the complete-card obligation.

5. The controller reserves up to the existing repair-reserve count (currently
   two) of active Map resumes after completed Engine dependencies even when
   the recovered ordinary queue exceeds admission capacity. A restricted
   producer mode cannot create/retry Engine work, and dependency Map resumes
   outrank broad Engine work. This uses no additional worker or model round.

No semantic routing classifier, new agent round, direct knowledge SQL access,
or bypass of tests/integration was added. A lookup miss still does not itself
create a new capability demand: the producer consumes the Map verdict, and
its candidate evidence is expressly unverified. Assessments are optional
telemetry for older adapters and cannot auto-close a ticket. Model compliance
and actual complete-card quality still need observation.

## Validation

18 knowledge/client/packet tests, 14 staged tests, 65 controller tests and
19 reliability tests passed (116 total); five enabled profiles validate.
The real HTTP fixtures check generated-label misses with named implementations,
query bounds, source freshness, service failures, and Engine source delivery
to the Map packet. The resume regression now requires verification even for
an eligible ordinary dependency. Existing integration-recovery cases remain.

`fts5-discovery-repair-replay.json` and its JSONL trace retain a replay of the
eight historical label misses: all now produce candidates for inspection.
This is not eight solved capabilities, nor evidence of semantic precision;
several candidates only implement one operation from the requirement.

These scripts are loaded by subsequent preparation/producer/worker processes.
Already-running observations are not retroactively changed. Full Engine wave
status and live successor publication are recorded separately.

## Remaining production limits

At startup the watchdog still reported 51 unresolved integration failures and
no productive progress in its latest interval. Those failures, quota/model
routing, complete-card trials, the SQL dashboard/statistics work and sustained
100+/day measurement are separate from these bounded repairs. Nine new Engine
regressions verify capabilities and connections; parser mappings and all
abilities of each actual card must still be verified before counting cards.

## Live handoff evidence

The controller was reloaded by exact PID under the dispatcher-admin lock,
leaving isolated workers and the independent integration process running.
The supervised replacement started as PID 2870145. It then automatically
queued `map.plan-pump-a-radha-coalition-warlord-ed4644a3b7/v2` through the new
completed-dependency reserve despite the oversized queue. The new ticket
contains the integrated domain-count contract and resolved Engine symbols.
See `controller-handoff-reload.json` and `live-completed-dependency-handoff.json`.
This is observed automatic resumption, not a completed-card claim.
