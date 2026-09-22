# Four-hour Codex operation — September 16, 2026

User requested a goal keeping all four Codex workers operating for at least
four hours. Goal started 19:02:46 UTC (original endpoint 23:02:46 UTC).
After repairs, all four live Codex leases and a nonempty reserve were verified
at 19:44:56.854616 UTC. The stability observation now runs through
23:44:56.854616 UTC, giving four additional hours after that verification.
The goal remains active. Starting a monitor or observing one busy sample does
not establish four hours of service.

At startup every worker was idle, queue runnable/deferred counts were both
zero, and the enabled producers had exhausted their eligible frontier.
Codex and Claude quota were available. Baseline: 1,461 completed jobs and
13,473 enabled cards. See `window.json` and `failure-census.json`.

## Repairs and bounded recovery

- Combined deterministic verification retained the original model worker ID
  and incorrectly reserved that worker's lease. Dispatch now excludes batch
  verifiers from model occupancy; individual verification/repair still owns
  its model lease. Dashboard model cards use the same distinction.
- Scope-checked regular Go files are formatted by the harness before saving
  and hashing a proposal, and before individual/batch verification. Syntax
  errors remain failures with diagnostics; formatting never replaces any
  semantic or full integration gate and does not compile or test.
- Fifteen immutable failures explicitly reported Luna capacity before any
  patch. `capacity-admissions.json` binds their receipts/contracts/evidence
  and admits one attempt on the already configured Terra model. Existing
  attempt history, scope, gates, quota ceilings and six-active review cap
  remain intact.
- `harness-recovery.json` is a finite review of 276 Engine failures: 167
  patch-protocol failures and 109 formatting failures. One additional
  formatting candidate was excluded because its earlier attempt history
  contained a semantic failure. Each successor binds the original receipt
  and contract hashes, preserves semantic scope/gates/behavior and retry
  ancestry, uses current clean source, and revalidates Oracle evidence and
  preparation. One successor per original; at most 24 active in this batch
  and the normal runnable queue cap still applies. Semantic failures are
  not relabeled as infrastructure or automatically included in this review.
- Empty runnable inventory now has an accurate controller message. Watchdog
  alerts after ten minutes without any work for enabled workers; an empty
  supply does not trigger a pointless controller restart.
- At 19:24 monitoring demonstrated that slow exhausted producers delayed
  reserve replenishment. The reviewed producer now has a bounded 12-admission
  refill burst, still inside the global sweep budget and all queue/cohort caps.
  New recovery successors prefer Codex among their already compatible profiles.
  Preparation skips expensive comment/string masking when a test's exact name
  is absent from the file, preserving the declaration-collision check.
  Reviewed lineage metadata and admission duplicate checks use disposable,
  per-file-stat-validated projections rather than decoding every historical
  packet repeatedly. Producer warm profile: 16.1 seconds before versus 5.5
  seconds after. These caches do not cache away contract/receipt hash checks.

At 19:11:19 all four Codex workers started actual tickets. Initial recovery
was insufficient to prevent subsequent idle gaps while the small cohort
awaited verification. Those gaps are retained in `occupancy.jsonl` rather
than counted as model work. At 19:20 four real Codex leases were active again;
two recovered patches had already passed full integration and completed.

## Evidence and observation

`observe.py` is read-only and samples actual job PIDs every 30 seconds until
the window deadline. It records individual model leases separately from
deterministic batch verification, aggregate states, and sampling errors.
`observer.pid` identifies its bounded background process.
Run `python3 docs/factory-ng/reviews/2026-09-16-four-hour-workers/status.py`
for current leases, recent occupancy, queue and net completions.

Regression checks: 69 controller, 33 staged harness, 12 verification,
12 focused batch, 22 reliability/watchdog, 8 remote verification, 2 reviewed
recovery tests, and 3 dashboard Go tests pass. The dashboard binary was
rebuilt and restarted under dispatcher-admin; fetched live HTML confirms
the batch-verifier exclusion. Controller and watchdog reloads used exact
verified PIDs and preserved all worker/gate processes.
Four admission/lifecycle cache checks, seven context-recovery checks and
thirteen producer-performance checks also passed after refill optimization.

Three historical integration failures remain terminal with their original
receipts and bounded repair blockers. They are not evidence that active
unrelated workers have stopped. Live deployment was not part of this task.

## Remote batch attribution correction during observation

Around 19:52, ten saved proposals were forced to local model-worker repair
because `import_results` treated every failed composition as a failed standalone
remote check. Evidence includes a three-member batch whose first member failed
its assertion and another whose unrelated member introduced an undefined symbol.
The comment promised standalone fallback, but the condition lacked the batch-size
check. This unnecessarily consumed the two local repair/test slots and threatened
to fill the reviewed cohort with waiting verification instead of runnable work.

Remote fallback now requires a failed single-member check. A multi-member failure
retains `verification_isolate` and receives individual deterministic remote checks.
The controller corrects old awaiting-only flags once per saved proposal, after
validating the old multi-member result, exact proposal identity, contract hash,
patch hash and original worker/profile/model. It records the result hash in
`remote_batch_isolation_recovery`; attempts, failed profiles, patches, receipts,
scope and gates stay intact. Active jobs and genuine standalone/transport
failures are excluded. See `remote-isolation-review.json`.

Validation: 10 remote-import/recovery tests, 12 verification tests and 69
controller tests passed. Controller reload preserves in-flight workers and gates.
At 19:58 the chosen-color-count proposal passed every focused gate on the remote
host without another model attempt: receipt
`docs/factory-ng/runs/2026-09-16T195801Z-focused-e63b72a2060f4013be982f15b3ba1f31-0.json`.

## Refill before historical cohort scans

Monitoring around 20:00 showed the queue empty again during a historical trial
scan, despite eligible reviewed work. The trial and context-retry producers ran
as an unconditional preamble, adding minutes before ordinary replenishment.
They now run after the bounded reserve refill, still exactly once per producer
cycle, even if the ordinary queue is full, and retain their original two-active
limits. No producer is disabled. Fourteen producer-performance, eight staged-trial,
three retry-batch and 69 controller tests passed, including a full-queue scenario
proving both special cohorts still run after replenishment.

### 20:20 UTC observation

Read-only warm controller replay (durable job and worker-pause writes disabled)
measured reconciliation plus all six worker quota probes at 4.72 seconds:
2.83 seconds reconciliation and 1.89 seconds quota checks. See
`controller-warm-profile.txt`. This does not justify another controller restart
or speculative scheduler rewrite.

The long-running activated-linked-referent individual repair completed its gates
and entered integration at 20:16:29; its Codex lease immediately returned to
fresh drafting. All four live Codex leases were verified again at 20:17:59.
Occupancy subsequently dropped as drafts finished. The finite reviewed cohort
reached its existing 24-active limit again at 20:19:22; verification and
integration must drain before it admits more. Preserve that backpressure and
record these gaps, rather than treating waiting verification as model activity.
At 20:20 there were 1,479 completed jobs (+18 since request), four integrating,
nine awaiting verification, and four unresolved integration failures. The
watchdog correctly reports the growing test backlog. The full four-hour goal
remains unproven and active through 23:44:56 UTC.

### 20:27 UTC — refill after test capacity drains

At 20:22 all four Codex leases were idle although four completed integrations
had reopened the finite reviewed cohort. The controller was still finishing
slow corpus scans after the producer's earlier `reviewed_harness_reserve_full`.
It now records active jobs when an opt-in burst producer reaches that bound and
revisits it between producer commands once an active job finishes. Unchanged
backpressure does not trigger repeated calls. All publication remains on the
controller thread, every retry consumes the ordinary sweep budget, and the
producer's 24-active bound, queue cap, hashes and gates remain unchanged.

Validation: 16 producer-performance tests (including newly drained versus
unchanged capacity), 69 controller checks, eight staged-trial checks and three
retry-batch checks pass. Exact-PID supervised reload requested under the
dispatcher-admin lock; workers and verification children were not interrupted.
Goal stays active through 23:44:56 UTC; occupancy gaps remain in the evidence.

**Live drain-refill proof, 20:35 UTC:** reviewed source reported full at
20:33:12. After integration freed capacity and the dependency producer returned
at 20:33:55, reviewed tickets were admitted at 20:34:27 and 20:34:52, before
the next slow corpus producer. At 20:35:11 all four Codex processes were live
and two tickets queued; completed count 1,486 (+25). See
`drain-refill-live-proof.json` and controller log. A separate candidate conflict
remains an integration failure subject to the unchanged bounded repair policy.

### 20:46 UTC — isolated verification collection delay

During a drain at 20:43, remote slots were idle with three remote-eligible
isolated proposals while a local batch occupied the second local gate slot.
The shared collection helper recognized only integration isolation; remote
verification isolation therefore still waited up to 120 seconds despite being
required to run alone. dispatch_verification_batch now skips collection only
for its isolated singleton. Ordinary verification and integration collection
are unchanged. Eight batching checks (including actual remote dispatch versus
ordinary collection) and seven gate-priority checks pass. Reload uses the scoped
dispatcher-admin lock and leaves active children intact. No gate or repair
budget change. Goal remains active through 23:44:56 UTC.

### 21:00 UTC — bound compiler failure as repair input

Local resumed proposals repeated already-failed remote compilation before
using their one allowed model correction. For explicit singleton Go compiler
failures, the runner can now use the original error as repair input before
recompiling the unchanged broken patch. The job-output result and matching
single-entry manifest must identify the exact immutable proposal, ticket,
source and original worker/model/profile. Combined failures, transport errors,
changed identities and corrupt input fall back to ordinary checks. Scope,
formatting and Engine registration prechecks still run locally. The correction
uses the existing allowance; all ticket gates run afterward before acceptance.
No passed gate is inferred from the old error.

A unique immutable evidence copy records result/manifest/proposal/ticket/patch
hashes and source revision; receipt attempt history and raw artifacts retain
its provenance. Compilation-off deferral preserves this context. Four current
proposals qualify with remaining correction; one compiler failure already spent
its allowance and is excluded (`compile-evidence-eligibility.json`). Thirteen
verification tests include an actual repair/acceptance round trip demonstrating
all final gates, no repeated failed compile, one model correction, artifact
hashes and rejection of mixed/stale/transport evidence. All 33 staged harness
and 69 controller checks pass. Controller reload is scoped; active children
continue with their existing code. Goal remains active through 23:44:56 UTC.

### 21:17 UTC — release repaired proposals for queued verification

Two local slots were spending their capacity both finding failures and testing
model corrections while remote slots could do the final verification. With
remote verification enabled and available, resumed qualified workers now save
a successful bounded correction as a new untested proposal, release the model
lease, and return it to ordinary focused verification. The controller clears
the previous remote-failure/isolation flags only for a changed patch linked by
hash to the current parent proposal, with the original contract/identity, an
unspent parent repair allowance, spent child allowance, and successful strict
repair application. An unchanged or unlinked proposal cannot reset flags.
Every final gate still runs. A failed corrected proposal has no additional
model repair allowance; normal fallback verification retains that budget.

Gate-repair raw responses and prior compiler evidence are confined to public
run artifacts, hashed, exported with selected inputs, and validated on transport.
Focused receipts preserve failed-attempt history and the original total model
call count. Compilation-off deferral retains this information. No CPU/slot,
queue/cohort, retry, integration or deployment limit changed.

Validation: 14 verification, 11 remote transport/import, 12 focused composition,
33 staged harness, and 69 controller checks (139 unique). Three controller checks
initially encountered live cache/source interference; two now use private
caches and the versioning test uses its own cloned checkout and cache. All three
passed in isolated reruns; original failure log and recheck summary retained.
Controller reloaded under dispatcher-admin; active gates/worker children kept.
The live observation is still incomplete and ends no earlier than 23:44:56 UTC.

**21:20 checkpoint:** controller PID 3240856 is live; all four Codex
processes were active at 21:20:21, completed count 1,501 (+40). The two
individual repair processes were started before the latest reload and therefore
do not have `--defer-repaired-verification`. No in-flight worker was restarted.
First production proof of the new repaired-proposal path is still pending; the
unit/real-Git round trip is not claimed as that live proof. See
`checkpoint-2120.json`. Observation and goal remain active through 23:44:56 UTC.

### 21:28 UTC — declared singleton test failures as repair evidence

Backlog inspection showed repeated local compilation before reproducing named
Go test failures already observed on exact saved proposals. Repair evidence now
also permits a `--- FAIL: Test...` name explicitly present in the TicketSpec's
Go gate command. The same singleton manifest/proposal/contract/identity checks
apply. Unrelated tests, timeouts, killed processes, transport failures and mixed
batches remain ineligible. This is failed-test input to the existing bounded
correction, never a passed gate or an acceptance. Every corrected-candidate
gate still runs. Already-spent repair allowances remain excluded.

The generic artifact schema is `factory.singleton-repair-evidence/v1`, retaining
compile versus test failure kind and full provenance. Earlier compiler-only
artifacts remain immutable. Fifteen verification, eleven remote and 33 staged
checks pass (59). Ten waiting proposals were eligible with unused correction
allowances (`singleton-evidence-eligibility.json`). Fresh runner processes load
this change; the controller protocol did not change and was not restarted.
Production proof of a corrected proposal completing the new path remains
pending. The four-hour goal is still active through 23:44:56 UTC.

### 21:41 UTC — live repaired-proposal proof and model-only correction scheduling

The bounce-with-mana-value-filter v4 and conditional-destroy-by-predicate v4
corrections both completed remote focused verification, preserving their exact
parent proposal hashes, spent correction allowances, attempt histories, and
failure-evidence artifacts. Every declared gate passed before acceptance. Both
entered integration. See `repaired-verification-live-proof.json`; this resolves
the earlier pending live-proof note.

Ten pending Codex proposals had valid singleton evidence and unused repair
allowances but waited behind occupied local verification slots. The scheduler
now admits these bounded corrections as model-only leases. Eligibility requires
the exact proposal/contract/identity failure evidence, unused model allowance,
and enabled remote verification outside backoff. Original worker identity,
usage limits, compilation switch, and one lease per worker remain enforced.
The runner's explicit --repair-only mode cannot fall through to backend tests
if evidence is missing or invalid; it saves an unaccepted proposal instead.
Successful corrections return to the full focused verification queue. Neither
local test slots nor the reviewed cohort cap were increased.

Validation: 15 verification, 9 scheduling/gate-priority, 8 batching, 12 focused
batch and 11 remote checks passed (55). The real-Git round trip proves no model
or gate call on invalid evidence, no acceptance before corrected gates, and
all required gates before eventual acceptance. Scheduler checks cover four
separate workers with two occupied local slots, duplicate-worker exclusion,
and actual guarded runner arguments and model-repair host assignment.
Controller reload requested under dispatcher-admin lock; existing workers kept.
The goal remains active through 23:44:56 UTC; no continuous-occupancy claim.

At 21:44:18 the replacement controller PID 3283483 dispatched actual model-only
repairs to codex (copy-spell-as-artifact-token v3) and codex-3
(conditional-discarded-card-power-damage v3). Both PIDs were live at 21:44:54,
with codex-2 still drafting; codex-4 remained idle. See
`repair-only-live-dispatch.json`. Corrected-gate completion for these two new
leases remains under observation. Net completed since request: 46; quota 40%.
Canonical source clean at 21:42 health check. Existing eight integration
failures remain visible; they were not reset to manufacture progress.

### 21:51 UTC — avoid repeating proven failures with spent correction budgets

The first two model-only corrections returned new hash-linked proposals with
exactly two total Codex model calls. Both reached remote verification; remaining
failures were real candidate failures, not harness acceptance. Four live Codex
leases were independently observed at 21:45:56, including a fresh fourth-worker
ticket; subsequent finish/dispatch gaps remain recorded.

When an exact singleton remote failure is validated but the existing model
correction budget is spent, ordinary resume now writes a gate_failed receipt
from that failure evidence instead of recompiling the same rejected proposal.
There is no extra model call, acceptance, or exported candidate. Invalid or
ambiguous evidence retains ordinary verification; model-only mode still refuses
spent budgets. Already-running verifiers are left to finish. Fresh runner
processes load the change; no controller reload needed. Sixteen verification
checks pass, including a real-Git terminal-failure test with zero repeated gates,
unchanged model-call count, and immutable failure evidence in the receipt.

The 33 staged-runner regressions also pass (49 checks for this change).

### 21:54 UTC — proven terminal failure does not reserve a backend test slot

Follow-up queue inspection confirmed that requiring a local test slot even to
finalize an exact proven singleton failure blocked otherwise idle workers and
kept the reviewed cohort full. The guarded evidence-only stage now permits both
unused bounded corrections and spent-budget terminal failures. The original
worker/profile/usage policy still controls admission, but no backend gate runs
in this stage. A spent budget cannot trigger a new model call. Missing evidence
saves pending for ordinary verification. Thus the earlier requirement that this
stage have an unused allowance is superseded; the model-call budget itself is
unchanged. Fresh failed proposals still require valid singleton evidence.

Seventeen verification and nine scheduling checks pass, including actual
spent-budget eligibility and runner terminal failure with zero model/test calls.
The previous 33 staged checks cover the same unchanged correction accounting.
Scoped graceful controller reload requested; active workers retained. Six
pending proposals currently qualify for repair or evidence-based finalization.
Goal remains active through 23:44:56 UTC.

At 21:55, production receipts prove two model-only repairs (create tokens from
exiled toughness v3; graveyard name-match damage v4) passed every required
focused gate remotely, each with two total model calls. The exhausted copy-spell
artifact-token v3 finalized gate_failed from its exact remote failure evidence:
no repeated ticket-gate entries, unchanged two-call total, no exported candidate,
and observation_only integration authority. See `model-only-repair-outcomes.json`.
The reviewed producer then admitted fresh damage-from-chosen-creature work at
21:55:40 as capacity drained. Full four-hour observation remains in progress.

21:59 checkpoint: +48 completed since request (1509 total), seven integrating,
two awaiting integration, seven awaiting verification, and three live Codex
leases. Codex-2 idle; dispatch/cohort gaps remain real. Dashboard HTTP 200;
observer PID 3054933 independently confirmed live. Waiting verification fell
from 21 at 21:52 to five at 21:57 before new drafts arrived. Eight unresolved
integration failures remain visible. No claim of uninterrupted occupancy.
See `checkpoint-2159.json`. Continue observation to 23:44:56 UTC.

22:10 monitoring checkpoint: +56 completed since request. All four live Codex
leases observed repeatedly around 22:02–22:05; subsequent completion/refill gaps
remain recorded. A fresh queued ticket at 22:07:11 dispatched at 22:07:41 (30s),
not a stuck queue. Usage 44%, configured ceilings unchanged. The 22:02 watchdog
reports movement with nine unresolved integration failures and no backlog-growth
alert. One failed multi-member integration is undergoing ordinary singleton
attribution after a duplicate-variable compile failure; no gate was bypassed.
Local disk 22 GiB free, shared Go cache 36 GiB; existing 40 GiB / 20 GiB-free
maintenance thresholds unchanged. Active source integration owns its scoped lock.
This turn was verified observation of live worker/integration/observer processes;
no new implementation change was indicated. Goal remains active to 23:44:56 UTC.

22:19 checkpoint: +61 completed. Codex-4's long individual verifier was checked
through its actual go/cards.test child (CPU ticks increasing); it finished,
saved its bounded correction, and took a fresh destroy-target-and-same-name
v3 ticket at 22:16:36. Do not restart a live verifier just for elapsed time.
One Terra call (destroy-attached-to-trigger-referent v3) returned explicit
capacity failure after successful read-tool events; no patch was produced.
The existing generic bounded infrastructure retry preserves its receipt and
backoff. Other Terra workers continued; no model/quota changes were made for
this isolated failure. The 22:12 watchdog reports forward movement and ten
unresolved integration failures, with no current backlog-growth alert. Goal
remains active through 23:44:56 UTC. See checkpoint-2219.json.

At 22:19:12 the capacity-failed ticket was live on codex-2 under its bounded retry; two other Codex leases had just finished. Three further tickets completed integration.

### 22:27 UTC — bounded refill after an integration changes the source pin

At 22:22:50 the reviewed producer correctly rejected its prepared result because
integration advanced the canonical source during preparation. That discarded
its ready frontier for the remaining slow sweep while Codex leases were idle.
The controller now retries that exact reason once per producer per sweep, only
for opted-in burst producers and only after the source preflight is clean. The
retry spends the ordinary sweep budget and runs complete preparation again on
the new pin. Dirty source, other unavailable reasons, exhausted budget, and a
second source race do not trigger this retry. Queue, cohort, model and gate
limits are unchanged. Both ordinary bursts and capacity-drain refills use the
same once-per-sweep allowance.

Nineteen producer performance/refill and nine scheduling checks pass (28).
Coverage includes successful refill ahead of slow scans, repeated source races,
dirty source, exact reason matching, and final-budget exhaustion. Scoped graceful
reload requested for controller PID 3305305; existing workers retained. Live
source-race recurrence and recovery remain to be observed; tests are not claimed
as that production proof. Four-hour goal remains active through 23:44:56 UTC.

22:29:46 checkpoint: all four Codex leases independently live, +65 completed
since request. Replacement controller PID 3361163 started22:26:54, dispatched
Codex/codex-2 at22:28:34, codex-3 at22:29:00 and codex-4 at22:29:34. The capacity
retry produced proposal cc233029e58a47b5a9c369f38e313192 with a passed strict apply
by22:22; verification remains required. See checkpoint-2230.json. Source-race
retry is deployed and tested but its particular production branch has not yet
recurred. The goal remains active through23:44:56 UTC.

22:40 checkpoint: +66 completed; the source-race branch now has production proof.
Reviewed preparation rejected a changed pin at22:37:56; controller admitted one
clean-source retry at22:37:57 with eight ordinary sweep attempts remaining. It
queued dual-target-fight-atom v3 at22:38:55 and Codex started it at22:39:20. See
source-race-retry-live-proof.json and checkpoint-2240.json. No stale ticket was
accepted and no queue/cohort bound increased. All four workers were live during
multiple earlier checks this turn; two currently live, two idle pending supply.
Quota49%, free disk24GiB at22:34. Goal remains active through23:44:56 UTC.

### 22:48 UTC — remote verifier export timeout repaired

The remote slots were idle with a five-minute backoff: each new pinned revision
triggered a full-history Git bundle even though the remote source mirror already
held an ancestor. Concurrent full exports reached the 300-second timeout and
stranded proposals in local fallback. The exporter now queries the remote
snapshot commit, confirms it exists locally, and sends only objects missing
relative to that snapshot. Git verifies bundle prerequisites at import; initial
bootstrap still uses a self-contained full bundle. Commit identity and every
verification gate are unchanged. Pack threads are bounded to two inside the
existing local CPU affinity.

A real export of current source b2ade26d4fb116d6b16851d7c053257945a4769e relative
to remote af8d88f89e490b8615c5d56834d9a191bca68ec7 took1.889s and18,125 bytes:
`incremental-bundle-benchmark.json`. Thirteen remote and nine scheduling checks
pass (22). Real-Git coverage proves exact pinned commit/tree after incremental
import, rejection without the prerequisite, and full bootstrap on an empty mirror.

Controller recovery grants one transport retry per unchanged saved proposal
only for this exact bundle-create300s timeout, with matching result, manifest,
TicketSpec and original worker/model/profile. Hashes bind the allowance; active,
superseded, changed-identity, unrelated transport failures and repeated allowances
are excluded. Model calls, failed profiles, attempts and gates remain unchanged.
Seven pending proposals qualify (`bundle-recovery-eligible.json`). Scoped graceful
reload requested for controller3361163; active workers retained. Live remote
completion after this change remains under observation. Goal still23:44:56 UTC.

22:53 production proof: six unchanged pending proposals received the exact
bundle-transport recovery allowance; the seventh was already running locally
and was untouched. Two recovered proposals (destroy permanents with attribute
equal to count v4; destroy trigger-block counterpart referent v3) passed every
declared focused gate on the remote host. Their proposal hashes match recovery
records and receipt model-call totals match saved context. See
bundle-recovery-live-proof.json. Remote transport status error is null; mirror
advanced to49048a7d2b7be525a8eac96031a1d0c309c402a4. Controller PID3396268.

23:03 checkpoint: all four Codex worker PIDs live, one runnable ticket queued,
+74 completed since request. The six-member wave completed full green integration
by22:59:59, including both bundle-recovered acceptances. See
bundle-recovery-integrations.json. Canonical source clean with all scoped locks
free at23:00 health check; service active and disk23GiB free. Remote transport
error remains null. Existing eleven integration failures remain visible. The
observer was inspected and still targets23:44:56.854616 UTC, covering the full
four-hour stability observation rather than ending at original23:02:46. No new
implementation change in this monitoring turn; actual worker/observer/controller
handles were repeatedly checked. Goal remains active. See checkpoint-2303.json.

23:11 checkpoint: +81 completed. Four live Codex leases observed at23:03 and
23:05, followed by finished-job/refill gaps; no claim of uninterrupted occupancy.
New sweep is replenishing the queue and a three-member wave entered integration
at23:09:33. Quota55% at23:07, all recorded implementation hashes matched tested
files, observer/controller live. Earlier sample audit (through23:03:29) had392
samples since19:44:56: concurrency4 in90,3 in107,2 in97,1 in91,0 in7. Eachworker
had20–29 distinct live tickets. These gaps are retained, not hidden; the final
report must distinguish timed supervision and recovery from continuous four-way
occupancy. Goal remains active through23:44:56 UTC. See checkpoint-2311.json.

23:20 checkpoint: +89 completed. All four Codex processes live at23:11 and
23:14, with explicit refill gaps afterward; two live at23:19. Worker-specific
completed-job counts at23:12 were codex19, codex-2 17, codex-3 16, codex-4 17
(plus15 Claude completions), demonstrating durable output for every Codex lease.
A new three-member integration wave began23:18:53. Thirteen unresolved candidate
integration failures remain visible; they do not hold the integration dispatcher
stopped. Remote transport remains operational after the incremental-bundle fix.
No implementation change in this verified-wait turn; observer and controller
handles remained live. Goal remains active through23:44:56 UTC. See checkpoint-2320.json.

23:31 maintenance checkpoint: the existing gocache guard was invoked at23:27
when free space crossed its20GiB reserve. It waited for active Go gates, closed
new local gate admission, and cleaned37.18GiB of derived cache after the last
active gate drained. Cleanup completed23:30:05 and command exited0; gate
admission reopened. No worker was killed, no artifact/receipt was deleted, and
thresholds/CPU/slot policy were unchanged. All four Codex leases independently
live after cleanup. See cache-maintenance-completed.json. +96completed at23:30,
six fresh tickets queued. Goal remains active through23:44:56 UTC.

## Closing audit — 2026-09-16 23:45 UTC

The observer covered the full 19:44:56–23:44:56 UTC window, following initial
recovery work from 19:02:46. Factory completed count increased by107 to1568;
87 completions were attributed to Codex (27/20/21/19), with20 from Claude.
All four Codex workers remain enabled on Terra and receive new tickets. The
supervised controller and watchdog continue operating after this observation.

This was **not uninterrupted four-worker occupancy**. Of474 actual-PID samples,
119 had4 live leases,130 had3,117 had2,101 had1 and7 had0. Per-worker lease
occupancy was60.8%,67.7%,65.8%,59.1%, including harness processing/individual
verification but excluding model-free batch verification. Each worker handled
25–39 distinct live tickets. Refill, verification and repair gaps are retained
in occupancy.jsonl. At23:43:39 all4 were live; at the closing snapshot2 had just
finished and2 were live, with refill ongoing. Do not describe these results as
100% worker uptime or a completely green backlog.

The final audit confirms HTTP200 dashboard/status/workers, controller3396268
with CPU[6,11,12,19]/nice10, unchanged quota/resource/compilation/integration
policy, all tested implementation hashes matching, remote transport error null,
completed cache maintenance and58GiB free. Compilation and full gates remain
required; deployment remains off. Sixteen unresolved candidate integration
failures (merge conflicts or full-gate failures) remain visible; they do not stop
subsequent independent integration. An active integration owns canonical source
at closing, so its working tree was not altered. The last unowned clean-source
check was23:00; final health check explicitly records current integration ownership.

See [final-audit.json](final-audit.json), [final-health-check.txt](final-health-check.txt),
and [evidence-audit-2333.json](evidence-audit-2333.json). Regression checks and
live fully gated proofs are recorded alongside each repair above. No new code
changes were made after the incremental bundle fix; no unverified deployment.
