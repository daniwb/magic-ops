# September 17 repeated ticket starvation

At12:25 UTC the queue was empty, all three enabled Codex workers had quota
(86% shared usage against95% ceilings), and canonical source was clean.
Codex-3 remains disabled. Last productive activity was hours earlier.

The capability-dependency producer crashed while revalidating Loki, the Deceiver
for the fully integrated delayed-sacrifice dependency. A direct triggered mapping
bypassed parse_atom, leaving typed and put_condition uninitialized; the newly
added Jeskai recipient-marker check accessed typed unconditionally. Prior code
could also leak those values from an earlier trigger/clause. The crash prevented
all later parent receipts from being reached. Other lanes reported exhausted
supported candidates; raising quotas cannot fix this condition.

The isolated parser correction resets both per-clause values before dispatch.
Four candidate tests include the original Jeskai behavior, actual Loki Oracle
mapping and a preceding recipient-marker regression. No allowed-path expansion,
no weakened gate, no provider call, no manual live-job rewrite. The ordinary
remote verifier accepted it; full flip/import/build/game/focused/six-shard gate
passed and pushed bd390f7d576d5e899e4a510e3d98d2e6560f2fb1. No live deployment.
See parser-crash.log, ticket.json, remote-result.json and integration-result.json.

The dependency producer now reports failed Map measurements and continues to
independent candidates. It neither drops the failed obligation nor resets its
budget. All failures remain producer_error if nothing else is eligible; successful
production retains candidate error evidence in controller status and watchdog.
A bounded refill burst of12 uses the existing queue and sweep limits so an
available dependency stream fills reserve before slow exhausted scans.

The watchdog previously suppressed empty-supply alerts whenever *any* proposal
was waiting for verification, even when its worker was disabled. Waiting proposals
no longer hide a totally idle, empty ready queue. Healthy controllers are not
restarted for empty supply. Tests:3 error-isolation +19 refill/performance +22
reliability checks passed. Controller/watchdog were reloaded under scoped lock.

The initial source correction was followed by live refill and durable progress
verification, recorded below.

## Refill latency and follow-through

At12:34 all three enabled Codex PIDs held new work. By12:41 thirteen new
tickets existed and six had fully integrated; reserve reached5 then drained
to1 during other producer scans. This was not sufficient evidence of a stable
reserve, so refill work continued.

Measured full-ticket decoding took4.49seconds for7876 TicketSpecs. A compact
stat-validated lifecycle index takes0.95seconds warm, with equal ancestry data;
only selected contracts are read in full. Lineage changes fail closed, and tests
verify full gates/evidence reach preparation and changed/deleted files invalidate
cache. Whole-producer timings are not comparable (knowledge-query latency differs
between cards); the controlled index comparison is index-benchmark.json.

Dependency refill burst bound is now24, but ordinary per-sweep and runnable queue
caps remain unchanged. Existing bounded clean-source retry also recognizes the
exact dependency-producer revision-race reason; preparation reruns once on a clean
new source, preserving all source checks. No unbounded ticket issuance.

Final focused suites:4 isolation/cache tests,20 producer-performance/refill tests,
22 reliability tests,8 recovery tests passed (54). Embedded JS syntax and three
idle-state cases pass. Dashboard now distinguishes empty ticket production,
producer errors and waiting for assignment, instead of labeling all idle workers
as lacking compatible tickets. Dashboard reloaded under dispatcher-admin.

Productive dependency supply was moved before the exhausted finite historical
recovery producers, saving their scan latency on an empty reserve. No producer
was disabled. At12:49 there are29 new tickets,10 new full integrations and6
actually queued/runnable tickets; follow-up dispatch continues. All quotas,
worker enabled flags, resource limits and deployment-off policy verified intact.

## Closing verification, 12:57 UTC

The actual runnable reserve holds10 tickets, meeting its target. Since12:25,
43 new tickets were created and17 completed integration. All three enabled
Codex workers repeatedly received subsequent assignments; this is not a claim
of uninterrupted occupancy. Codex-3 remains disabled. Completed jobs have
passed integration receipts, retained in integrated-progress.json. The earlier
12:53 target was replenished after intervening dispatch, showing automatic refill.

The closing health check found canonical source clean, integration lock free,
controller supervised/running and live service active. Implementation hashes
match the tested files. Candidate integration failures remain visible; watchdog
is not completely green. This repair resolves the observed producer starvation,
not every candidate failure. No gate, quota, resource or deployment policy changed.

Codex usage is93% against the unchanged95% ceiling. A subsequent quota pause
is a separate constraint and must not be mistaken for absent ticket supply.
See final-audit.json, closing-limits.json and live.jsonl for bounded observations.
