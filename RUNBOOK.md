# RUNBOOK — Factory NG

Updated 2026-09-07. This runbook covers only the live Factory NG workflow.
The authoritative resumption record is `docs/factory-ng/CURRENT.md`.
Historical plans under `docs/archive/` are reflection evidence, not live
policy.

## System

Factory NG derives bounded, model-neutral TicketSpecs from measured Magic
ground truth. The controller keeps a runnable reserve, assigns each ticket to
one compatible model profile, and runs the model in an isolated clone.
The harness—not the model—applies edits and owns focused checks. Accepted
patches then pass a separate integration gate: deterministic reparse/import,
Go build, focused tests, and the full six-shard suite. A completely green
integration fast-forwards and pushes `openmagic/main`. Live deployment is a
separate, disabled-by-default decision.

The queue is file-backed:

- TicketSpecs: `docs/factory-ng/tickets/*.json`
- immutable execution and integration receipts: `docs/factory-ng/runs/*.json`
- controller job state: `state/factory-ng-jobs.json`
- controller status: `state/factory-ng-runtime.json`
- watchdog status: `state/factory-ng-watchdog.json`

## Repositories

- `/opt/development/magic-ops`: Factory NG control plane, policy, scripts,
  TicketSpecs, receipts, and state.
- `/opt/development/test/openmagic`: canonical parser/engine integration
  checkout. It must be clean whenever Factory NG does not hold the integration
  lock.
- `/opt/development/magic-new`: live mirror and deployed backend binary.
- `/opt/development/factory-ng-trust`: operator-managed external trust root.
  Do not replace or rotate it implicitly.

## Live components

| Component | Location | Purpose |
|---|---|---|
| NG dashboard/API | `http://localhost:9999/dashboard` | Queue, workers, receipts, integrations, limits, controls |
| Controller | tmux `dispatcher:factory-ng` | Produce, reserve, dispatch, reconcile, integrate |
| Watchdog | tmux `dispatcher:factory-watch` | Ten-minute liveness and progress audit |
| Worker jobs | isolated `/tmp/factory-ng-*` clones | Model-specific bounded work |
| Card knowledge | `http://127.0.0.1:4103` | Compact parser/engine evidence lookup |
| Go cache barrier | `state/go-cache-maintenance.json` | Serialized cache maintenance and gate admission |
| Live backend | systemd `magic-backend`, port 8090 | Deployed game API |

Worker profiles and models are defined in
`config/factory-ng-workers.json`. Producer commands are defined in
`config/factory-ng-producers.json`. Runtime and integration behavior is
defined in `config/factory-ng-policy.json`.

## Start-of-session checks

Always run:

```bash
cd /opt/development/magic-ops
cat ~/.claude/projects/-opt-development-magic-new/memory/MEMORY.md
bash scripts/session-health-check.sh
curl -fsS http://localhost:9999/factory-ng/status | jq .
cat state/factory-ng-watchdog.json | jq .
git -C /opt/development/test/openmagic status --short
```

Also inspect `docs/factory-ng/CURRENT.md`. Do not infer current state from an
old chat or a historical receipt.

Healthy minimum:

- tmux contains `disp`, `factory-ng`, and `factory-watch`;
- `/factory-ng/status` reports `state: running` and a recent
  `updated_at`;
- the watchdog has a live controller PID and no stale-controller problem;
- the canonical `openmagic` checkout is clean outside an integration;
- runnable work, active work, or a clearly explained deferred state is visible.

## Queue and scheduling

### Continuous corpus frontier and cold history (2026-09-19)

The original 2–6-miss producer remains enabled: it admits only cards whose
every miss belongs to its explicit supported verb/runtime families. It is not
a general producer for every card with two through six missing behaviors.

`corpus-frontier` supplies a continuous fallback after the proven compilers.
It scans current review records across all miss families, caches measurements
by parser/corpus inputs, resumes bounded scan slices, and ranks unseen cards
with one through six misses. Only the next candidate is compiled to an
immutable TicketSpec; the whole inventory is never bulk-enqueued. A shared
active miss signature prevents concurrent work on the same exact measured
shape. Existing card/text ownership survives every source change and archive.

The new contracts require staged investigation of actual runtime support:
implement a bounded Map fix or return the existing validated atomic Engine
capability demand. They retain positive/negative tests, the complete-card
remeasurement gate, and full integration. The controller prioritizes existing
repairs and proven Map resumes, then Engine foundations, before more frontier
investigation. Within the frontier it prefers simpler seams, fewer misses,
more exact-detail reuse and shorter Oracle text, with deterministic ties.
Short subsystem keywords such as dungeon/attraction actions are not assumed
cheap merely because their Oracle text is short.

Read `state/factory-ng-frontier.json` (also in runtime `supply`) for candidates,
source fingerprint, occupied shapes, existing lineages, measurement errors and
explicit decomposition/eligibility blockers. These counts are measured
candidates, not promises of semantic success. Cards beyond the six-miss bound
remain visible and are reconsidered after relevant parser/corpus changes;
retry-exhausted lineages are not silently reissued. A zero candidate count with
remaining dispositions is `frontier_blocked`, never proof all cards are done.

Completed and terminal superseded jobs are archived by the controller, at most
200 per reconciliation, in `docs/factory-ng/job-archive/`. Full job snapshots
are immutable and linked from `archive_path`; compact tombstones retain IDs,
outcomes, receipt pointers, attempt history and production lineage in the
compatibility job ledger. Original TicketSpecs and receipts stay at their
existing paths. Reconciliation skips archived lifecycle processing and file
stat checks for their cached immutable ticket/receipt projections. Dispatch
sorts only ready work. Metadata indexes remain available for dependencies,
duplicate prevention and historical lookup; history is not deleted.

Do not hand-edit archive/tombstone state while the controller runs. No task is
reopened merely because its full job record has moved to cold history. An
explicit authorized state transition makes a tombstone active again, and the
next archival writes another immutable snapshot.

The controller scans enabled producers every five minutes. Below target,
successful production and unfinished scan slices continue in bounded sweeps
and on the next controller cycle, without waiting for that interval. A producer's
latest exhausted/error result stops immediate continuation. Reserve size is:

```
max(queue.target_ready, queue.ready_per_worker × enabled workers)
```

The current policy keeps two runnable tickets per enabled worker. The
`queue.max_queued` safety cap counts runnable tickets only. Runnable and
deferred are different:

- **runnable**: at least one compatible worker can claim the ticket now;
- **deferred**: preserved inventory that no currently available compatible
  worker can claim, commonly because of pacing, authentication, profile
  compatibility, or exhausted per-profile retries.

Deferred tickets do not satisfy or consume the runnable reserve. Producers
must continue looking for independent work even when deferred inventory is
large.

Running jobs reserve retry headroom only above the ready target: admission is
`max(target_ready, max_queued - working)` after raising `max_queued` to at least
the effective target. Thus five busy workers cannot reduce a ten-ticket target
to seven. This is a shared compatible reserve, not two tickets assigned to each
worker. Supply can remain below target when no eligible candidates exist.
The dependency producer is revisited while other producers make progress, so
Map verdicts arriving during a sweep can generate Engine work in that sweep.

Manual enqueue is a repair interface, not normal production:

```bash
python3 scripts/factory-ng-enqueue.py --ticket /absolute/path/to/ticket.json
```

Never edit job state or TicketSpec lifecycle fields by hand while the
controller is running.

## Worker model

A TicketSpec is model-neutral. Each enabled worker selects a registered
profile with its own executable, context shape, limits, and adapter. Current
worker identities are read from the API:

```bash
curl -fsS http://localhost:9999/factory-ng/workers | jq .
curl -fsS http://localhost:9999/factory-ng/limits | jq .
```

Models have no commit, integration, push, deployment, or live-ticket
authority. Separate compatible tickets may run in parallel. Do not send the
same ticket to multiple profiles except for an explicit benchmark or review.

Current routing is:

| Physical worker | Route | Work |
|---|---|---|
| Qwen local | `qwen-prepared-direct@1.0.2` | evidence-complete Map |
| Qwen local | `qwen-prepared-local@1.0.1` | bounded agentic Engine; auto mode prefers it while runnable Engine backlog exceeds Map backlog |
| MiniMax M3 free | `minimax-prepared-direct@1.0.0` | Map only; Engine qualification is withdrawn |
| Claude | `claude-staged@1.0.0` | Map and Engine |
| Codex | `codex-constrained@1.0.0` | Map and Engine when its usage gate allows |

Alternate profiles on one physical worker share one lease. They do not run
concurrently and do not increase the runnable-reserve worker count. Each
worker's `routing_mode` may be `auto`, `map`, or `engine`; `auto` follows the
dominant runnable workload while respecting what its registered profiles can
actually run.

Claude and Codex are usage-gated according to their configured weekly policy.
Local Qwen is unmetered. OpenRouter adapters share durable 429 cooldown state
in `state/openrouter-cooldown.json`.

## Integration and gates

`scripts/factory-ng-integrate.py` owns NG integration. It requires a clean
canonical checkout, verifies the accepted observation, composes the candidate
in a disposable clone, and runs:

1. deterministic flip and corpus import;
2. `go build ./...`;
3. focused vocabulary, V2, shape, and subtype-scope tests;
4. `bash scripts/test-cards-sharded.sh 6`;
5. canonical fast-forward and policy-controlled push.

Never bypass a gate, weaken a TicketSpec gate after failure, or pipe test
output through `tail` in an `&&` chain. The V2 registry literal is frozen:
new primitives belong in `registry_<topic>.go` init files with new
`shape_<topic>_test.go` tests.

Automatic integration and push are controlled by
`config/factory-ng-policy.json`. `deploy_after_push` is false by default.
An integration receipt is the authority for gate, commit, and push status;
an accepted worker receipt alone proves none of those.

Recovery behavior (September 7): up to `integration.wave_size` (currently 8)
accepted candidates form one wave. While workers are active, collection waits
up to `integration.collect_seconds` (120 seconds, capped at 300) from the
oldest accepted patch, or flushes at `integration.collect_min_candidates` (3).
Isolated retries, an idle fleet and already-aged patches proceed immediately;
collection never sleeps inside the controller or extends a deadline on arrival.

Multi-candidate waves apply conflict-free patches before running every original
semantic gate once on the final composition. This avoids compiling each
intermediate Engine revision. Single-candidate failures retain their individual
gate diagnostics. The complete wave then runs game tests and the six-shard cards
suite before landing. An excluded candidate has a separate per-ticket result
and is never listed among the successfully integrated parents. Failed combined
gates are isolated per candidate. An infrastructure failure retains its
accepted patch for bounded integration-only retries, with backoff and a
counter separate from model attempts.

Existing failed Engine integrations also have a bounded admission reserve
(using `queue.integration_repair_reserve`, default two). The restricted
`--engine-integration-repairs-only` producer mode can only issue fresh
successors for those failures; it cannot create new demand. Each Engine chain
retains its one integration-repair limit. Map repair ancestry follows
supersession and dependency recovery links, retaining the two-generation
limit across Engine handoffs. Exhausted jobs preserve their failed receipts
and expose `repair_blocker` plus `waiting_reason` in dashboard job data.
Never reset these counters or treat a newly queued successor as a completed
card. See the September 8 automatic-repair report linked from CURRENT.md.

`git status --porcelain` is insufficient for readiness: a checkout can have
no file diffs and still contain MERGE_HEAD. The common preflight checks Git
operation markers, command success and untracked files. Preserve any pending
operation before controlled recovery; do not automatically reset user work.

Legacy integrator-lite's retained cron is inert while NG automatic integration
is on. Reboot no longer launches legacy r1/rf1 workers. Do not re-enable a
second canonical mutation owner or automatic live deployment as a recovery step.

## Scoped locks

There is no global session lock. Shared mutations use kernel-held scoped
locks:

| Scope | Lock | Protects |
|---|---|---|
| `integration` | `/tmp/orch/openmagic-integration.lock` | canonical `openmagic` main |
| `deploy` | `/tmp/orch/factory-deploy.lock` | push, live mirror, build, service restart |
| `dispatcher-admin` | `/tmp/orch/dispatcher-admin.lock` | dashboard host and Factory control administration |

For manual commands:

```bash
scripts/factory-ng-scoped-lock.sh <integration|deploy|dispatcher-admin> command [args...]
```

Factory scripts that document internal locking must not be wrapped in the same
lock a second time. A lock conflict exits with code 75. Crashes release locks
automatically.

## Normal controls

### Dashboard history index

`/factory-ng/data` reads `state/factory-ng-dashboard.sqlite3`, a disposable
SQLite projection of the immutable TicketSpecs/receipts and current jobs.
The dashboard host refreshes it in one background loop, waiting 15 seconds
between refreshes; a dedicated `.lock` file serializes index writers. WAL
readers retain the previous complete snapshot during refresh. No HTTP request
scans receipt directories. Work, attempts and integrations have bounded pages;
individual evidence remains at `/factory-ng/detail`.

The page shows index age and unreadable-source count. Failed refreshes retain
the last snapshot and log to `/tmp/dispatcher-v4.log`; an absent index returns
HTTP 503 while the background loop builds it. Inspect or refresh:

```bash
python3 scripts/factory_ng_dashboard_index.py | jq '{indexed_at,summary,invalid_files,pages}'
python3 scripts/factory_ng_dashboard_index.py --refresh
```

The source JSON remains authoritative. This does not replace controller job
storage or define a new token-accounting policy: provider fields are copied
without weighting; complete-card, mission-cost and stage-time totals must not
be inferred from candidate counts. The legacy offline renderer
`factory-ng-dashboard.py` remains available for parity checks.

### Daily activation chart

`/factory-ng/daily-activations` serves `state/factory-ng-daily-activations.json`.
The dashboard runs `scripts/factory-ng-daily-activations.py` every five minutes
in the background. It counts committed `auto` cards at UTC day boundaries,
with 14 completed days and a separate partial today. The chart goal is 100/day;
150/day marks a high day. Neither threshold changes factory scheduling policy.

Immutable Git blob/commit caches avoid repeated history work. A failed refresh
preserves the old dated snapshot; errors appear in `/tmp/dispatcher-v4.log` and
the chart flags data older than 12 minutes. A manual refresh is read-only with
respect to canonical source and holds its own snapshot lock:

```bash
python3 scripts/factory-ng-daily-activations.py
```

Daily explanations combine import contributions, observed producer/watchdog
signals and reviewed notes in
`docs/factory-ng/measurements/activation-day-notes.json`. Add a dated source for
any operator explanation; do not infer a unique cause from a low count alone.

### Start and stop

Use the dashboard Start/Stop controls for an intentional operator pause or
resume. Serialized CLI equivalents are:

```bash
scripts/factory-ng-scoped-lock.sh dispatcher-admin \
  curl -fsS -X POST 'http://localhost:9999/factory-ng/control?action=start'
scripts/factory-ng-scoped-lock.sh dispatcher-admin \
  curl -fsS -X POST 'http://localhost:9999/factory-ng/control?action=stop'
```

Stopping the controller prevents new production and dispatch. It does not
authorize killing model jobs, changing receipts, or altering integration
state.

Dashboard Stop persists `state/factory-ng-paused`; Start clears it. Reboot and
watchdog recovery honor that marker. Controller supervision is
`bash launchers/launch-factory-ng.sh`; the idempotent startup entry point
`bash scripts/dispatcher-reparse-launch.sh` recreates missing NG, watchdog,
knowledge and visualization windows without killing the shared tmux session.

Validate current worker contracts with
`python3 scripts/factory-ng-profile-validate.py --enabled-workers`. The
all-profile audit also scans unqualified experimental profiles and can fail
without invalidating the enabled routes. Do not promote an experiment to
remove its validation error. The OKF/shunt experiment is currently disabled.

The watchdog retains unresolved integration faults and separately measures
24-hour enabled-card movement. A quota pause has a planned resume time;
restarting a controller does not resolve exhausted quota or semantic gates.
Repair regressions run with `python3 scripts/test_factory_ng_reliability.py`.

To run one non-restarting watchdog audit (it still updates watchdog state and
its append-only log):

```bash
python3 scripts/factory-ng-watchdog.py --once --no-restart | jq .
```

To inspect the receipt-derived CLI dashboard:

```bash
python3 scripts/factory-ng-dashboard.py
python3 scripts/factory-ng-dashboard.py --format json | jq .
```

## Recovery

### Controller missing or stale

Check exact processes and durable status:

```bash
pgrep -af '[f]actory-ng-controller.py'
tail -100 state/factory-ng-controller.log
cat state/factory-ng-runtime.json | jq .
cat state/factory-ng-watchdog.json | jq .
```

The watchdog terminates only an exact stale controller PID; the supervised
`factory-ng` tmux loop recreates it. If the tmux window itself is absent,
recreate only that NG supervisor:

```bash
scripts/factory-ng-scoped-lock.sh dispatcher-admin \
  tmux new-window -d -t dispatcher -n factory-ng \
    'while true; do cd /opt/development/magic-ops || exit 1; python3 scripts/factory-ng-controller.py --interval 15 --producer-interval 300 >> /tmp/orch/factory-ng.log 2>&1 & factory_controller_pid=$!; wait "$factory_controller_pid"; sleep 15; done'
```

Keep the controller as an explicit child of the tmux shell. A bare foreground
loop can be optimized into the Python process and lose the supervisor window
after a clean controller reload.

Do not use broad `pkill` patterns.

### Watchdog missing

Recreate only its supervised NG window:

```bash
scripts/factory-ng-scoped-lock.sh dispatcher-admin \
  tmux new-window -d -t dispatcher -n factory-watch \
    "while true; do cd /opt/development/magic-ops && python3 scripts/factory-ng-watchdog.py --interval 600 >> /tmp/orch/factory-ng-watchdog.log 2>&1; sleep 15; done"
```

### Producer failure

Inspect:

```bash
jq '.results, .queue, .message' state/factory-ng-runtime.json
tail -100 state/factory-ng-controller.log
jq '.problems, .recovery' state/factory-ng-watchdog.json
```

A producer timeout or nonzero exit must remain visible as
`producer_error`; one failed producer must not prevent later producers or
worker reconciliation. Fix the deterministic producer or its evidence source,
then let the next scan refill the queue.

### No runnable work

Compare the queue with worker availability:

```bash
curl -fsS http://localhost:9999/factory-ng/status | jq '{queue,deferred,active,results,message}'
curl -fsS http://localhost:9999/factory-ng/limits | jq .
curl -fsS http://localhost:9999/factory-ng/workers | jq .
```

Check, in order:

1. enabled compatible profiles;
2. authentication holds and provider cooldowns;
3. per-profile retry history on deferred jobs;
4. producer admission incorrectly treating deferred inventory as runnable;
5. producer errors or a genuinely exhausted measured frontier.

The build-plan repair and conflict lanes search the current review corpus,
with separate resumable cursors; dated plan examples only rank candidates.
They reconsider eligible stale failures on every scheduled sweep, regenerate
the bounded ticket against current source, and retain its failed receipt and
retry generation. A superseding ticket owns the work even if its production
key changed after an Engine dependency. Ticket versions, not file modification
times, determine history order. Age alone never resets a retry budget.

Build-plan producers cache compact ticket history, review shards and parser-built
subtype tables in `state/factory-ng-producer-cache.sqlite3`. Repair scans parse
only Oracle texts with an eligible retry lineage. Every file is checked for
changes; parser-result keys follow relevant input content rather than every Git
commit. Parser modules also reuse bounded compiled regex patterns. New script
invocations load updates automatically; no controller restart or cache deletion
is needed. See `docs/factory-ng/reviews/2026-09-15-producer-cpu/README.md` for the
full-corpus equivalence check and measured CPU reductions.

To inspect the next repair without enqueueing it (the disposable scan cache
may advance):

```bash
python3 scripts/factory-ng-produce-build-plan.py --lane repair \
  --plan docs/factory-ng/measurements/producer-frontier-2026-09-12-evening.jsonl
```

An exhausted fresh lane does not imply exhausted repair supply. Conversely,
old blocked or failed records are not automatically runnable: completed or
superseded work and exhausted repairs remain excluded. Unsupported or mixed
current misses remain outside the generic single-miss repair lane.

`build-plan-multi-miss` admits cards with **two through six unresolved misses**,
including different supported verb families. This replaces the two-card,
same-family pilot. Every miss must belong to an explicitly supported family
with registered runtime evidence. Unknown/static/replacement catch-all misses
and cards above six misses remain outside this lane.

The ordinary runnable queue limits bound admission. Historical blocked parents
do not occupy permanent pilot slots. Existing card history prevents reopening
failed work under a multi-miss label, and multi-miss ownership prevents a new
single-miss ticket when a dependency changes the remaining shape. Engine
dependencies are built atomically; the Map successor retains all original
whole-card gates and obligations. One fixed clause is never a completed card.
This lane obeys the configured Factory work schedule.

Do not count raw queued records as available work and do not manufacture
manual tickets merely to make the queue counter rise.

### Provider authentication failure

The controller refunds an authentication-only attempt, returns the ticket to
the queue, and pauses that worker. Re-authenticate outside the Factory, then
use **Resume after login** on the dashboard. A repeated failure will pause the
worker again without charging the ticket.

### Reviewed needs-attention recovery

The finite September 15 review is at
`docs/factory-ng/reviews/2026-09-15-needs-attention/worker-recovery.json`.
The controller validates each reviewed TicketSpec/failure hash and original job
identity, then admits at most six recoveries within the queue cap. Each entry gets
exactly one additional attempt, preserving its original attempts and failed-profile
history in `attention_recovery`. Only the individually reviewed compatible profiles
may take that attempt. No generic retry cap is increased and semantic/integration
failures cannot use this mechanism. The immutable evidence and original gates remain.
An admitted or superseded entry is never readmitted from the manifest.
Current blocked reviewed Map receipts receive dependency scan priority. Their generated
Engine children and Map resumes retain `production.attention_recovery_parent`, share
the six-active recovery limit, and dispatch after verification but before further
reviewed retries. One slot is reserved while a reviewed lineage is blocked so
retries cannot fill every opening before dependency production. Ordinary dependency
retry limits and production gates still apply.

Progress: `python3 docs/factory-ng/reviews/2026-09-15-needs-attention/status.py`.
Do not reset live jobs or edit attempts to repeat a failed reviewed recovery. Inspect
the new receipt and make a concrete correction. Codex capacity errors are reported
as `infrastructure_failed_provider_capacity` with bounded infrastructure backoff;
they are not malformed model patches.

### Codex patch-protocol recovery (September 16)

Protocol correction supplies bounded exact source excerpts and keeps registered
Codex source reads available during the final correction call. That call cannot
request another NEED continuation. The applier accepts known standalone marker
variants (`<<<REPLACE` / `===`, `<<<END`) while retaining exact unique SEARCH,
all-or-nothing application, scope checks and every test gate.

Reviewed queued protocol failures may get one finite extra attempt through the
operator manifest. Saved proposals retain that attempt's original-profile
eligibility for verification/repair; history must not exclude their owner after
drafting. This never grants a fresh drafting attempt. A further capacity-only
recovery must bind the prior review and new failure and explicitly require a
different model. Previous reviews and attempts remain visible.

New Codex jobs currently use `gpt-5.6-terra` as a temporary fallback after Luna
provider-capacity rejections. Original profiles and usage ceilings remain;
in-flight proposals retain their pinned model. See
`docs/factory-ng/reviews/2026-09-16-codex-repair/README.md` for evidence and the
saved pre-fallback worker configuration. Do not reset live jobs to recover them.

### Worker or gate failure

Use the job's exact receipt and raw artifacts:

```bash
python3 scripts/factory-ng-dashboard.py --format json | jq '.jobs[]? | select(.state != "completed")'
find docs/factory-ng/runs -maxdepth 1 -type f -printf '%T@ %p\n' | sort -nr | head
```

Infrastructure failures may receive only the bounded retries in policy.
Semantic, scope, apply, focused-test, and full-gate failures remain durable
failures; do not relabel them as infrastructure failures.

### Dirty canonical checkout

Stop and identify ownership:

```bash
git -C /opt/development/test/openmagic status --short
pgrep -af '[f]actory-ng-integrate.py'
```

Never stash, reset, or discard unknown changes. If no integration owns the
tree, preserve the evidence and resolve ownership before allowing another
integration.

### Card-knowledge service unavailable

```bash
curl -fsS http://127.0.0.1:4103/health
tail -100 /tmp/orch/kb.log
```

Restart its existing tmux window or create an NG support window:

```bash
scripts/factory-ng-scoped-lock.sh dispatcher-admin \
  tmux new-window -d -t dispatcher -n kb \
    "cd /opt/development/magic-ops && exec python3 scripts/card-knowledge-service.py >> /tmp/orch/kb.log 2>&1"
```

Reindex after an Engine landing:

```bash
curl -fsS http://127.0.0.1:4103/reindex
```

## Deployment

A green NG push does not deploy. Deploy only after an explicit operator
decision, under the deploy lock:

```bash
scripts/factory-ng-scoped-lock.sh deploy bash -lc '
  git -C /opt/development/magic-new pull --ff-only origin main &&
  cd /opt/development/magic-new/backend &&
  /opt/development/magic-ops/scripts/go-cache-run.sh build -o ../bin/magic-api-server ./api &&
  sudo -n systemctl restart magic-backend
'
systemctl is-active magic-backend
curl -fsS http://localhost:8090/api/health
```

Do not deploy from an unverified worker clone or from a revision that lacks a
green NG integration receipt.

## Manual compilation/testing switch and shared CPU budget

The **Compilation & testing** switch on `/dashboard` controls verification and
integration independently of Factory Start/Stop. It persists
`compilation.enabled` in `config/factory-ng-policy.json`. There is **no time
schedule**. It is initially off at the user's request.

- **Off:** producers and workers continue preparing fixes. Successful patch
  proposals are saved as `factory.untested-proposal/v1` files under
  `docs/factory-ng/candidates/`; the job becomes `awaiting_verification` and
  releases its worker lease. These proposals are not accepted receipts and do
  not enable cards. Existing accepted patches also wait for integration.
- **On:** a central verifier collects up to eight saved proposals with the same
  pinned source revision. Each patch first passes its own scope/diff check, then
  every required test runs on one composed checkout. Go reuses compiled packages
  across selectors; identical simple test commands run once with shared evidence.
  Collection waits at most 120 seconds while drafts are active and flushes at
  three candidates or when idle. Fresh drafts also enter this queue while On.
  Conflicts or failures return the original proposals to individual verification
  with the original worker and bounded repair allowance; no fresh proposal is
  generated merely to resume. Only checked observations enter full integration.
- With `verification.overlap_integration=true`, one focused verification batch
  (or one individual fallback) can run alongside one full integration wave in
  separate disposable clones. Both share CPUs 6,11,12,19 / nice 10; this does not
  promise twice the throughput. A second verifier and a
  second integration wait. Omitting or disabling the flag restores serialization;
  active jobs finish normally before serial admission resumes. Accepted batches
  record their tested tree and member tickets. Full integration rechecks included
  contracts on its final composition, including when only a subset is merged;
  acceptance does not claim each patch passed standalone.
  The controller admits integration before verification and between producer
  steps. With overlap enabled, verification cannot occupy the integration slot;
  in serial mode, retry-eligible accepted patches reserve the shared slot.
  Integration backoff and the collection window remain.
- A test already executing finishes safely. Worker harnesses check the switch
  before each next gate; if off, they save the current patch again. An already
  admitted integration finishes its full gate. This switch does not kill jobs.
- Turning compilation on does not clear a manual Factory Stop. Central batch
  verification makes no model calls and needs no provider quota. Individual
  fallback uses the original enabled worker and its existing quota/repair rules.

### Test queue flow tracking

The watchdog records `state/factory-ng-queue-trend.json` and appends samples to
`state/factory-ng-queue-trend.jsonl` every audit. For an extra read-only sample:
`python3 scripts/factory_ng_queue_tracking.py`. A process-held lock prevents
concurrent samples; duplicate samples within 55 seconds are skipped.

`waiting` matches the dashboard's patches waiting (focused plus integration).
`total_unfinished` also includes running focused checks and integration, so moving
work into a running slot does not appear as drain. Initial-cohort states, arrivals,
successful completions and departures through failure/supersession are separate.
No ticket is deleted or reset by this observer. The rolling window uses a bounded
history read; after 30 minutes it flags growth of at least five unfinished tickets
when at least 20 remain and testing is enabled. This catches a throughput deficit
even if fresh accepted receipts keep the existing activity watchdog moving.

`verification.local_slots=2` allows two local verifier/repair processes in the
existing four-CPU pool (Go2 per invocation). A multi-ticket batch occupies one
slot. Remote verifier identities retain one process each; original worker/model
identity, usage gates and bounded repair limits still apply. Compilation off
prevents new admission; current gates finish normally.

An isolated proposal with hash-validated remote singleton failure evidence
may run with `verification_host=model-repair`.
This holds its original model worker lease but no local compilation slot. The
runner uses `--repair-only --defer-repaired-verification`; missing evidence
saves an unaccepted proposal without local tests. A remaining correction
allowance permits one bounded repair, then the ordinary full focused gates.
An exhausted allowance produces the proven failure receipt without another
model call or test slot. This path requires an
enabled remote verifier outside backoff, the compilation switch, and the
original worker's usage allowance. It does not raise model or test budgets.
When ordinary resume validates the same exact singleton failure and the model
correction allowance is already spent, it records a terminal `gate_failed`
receipt with the failure evidence. It does not repeat the rejected candidate's
tests, make another model call, or export an accepted patch. Ambiguous and
invalid evidence still falls back to ordinary verification.

If the same conflicting patch repeatedly reenters integration, compare its
`processed_receipt` with the accepted observation in `receipt`. Integration must
preserve that consumed observation even when `verification_resume` remains set;
writing the integration receipt there makes old acceptance look new. The
controller regression `test_integration_keeps_consumed_verification_receipt`
covers this failure. Reload the corrected controller under dispatcher-admin;
do not reset attempts or manually rewrite live jobs. Conflict repair producers
retain the failed integration evidence.

### Remote full integration gate on the Ryzen 395

`integration.remote.enabled` with `include_semantics=true` sends original
composed TicketSpec checks before the six production stages (corpus flip/import,
Go build, game tests, focused cards, full six-shard cards plus cardfns vet/tests)
to `dani@192.168.1.251`. The canonical coordinator still holds the integration lock,
composes candidates, binds their original semantic contracts into the remote
packet, validates returned evidence, commits generated card data, fast-forwards
main and pushes under policy.
It rechecks canonical HEAD and cleanliness before landing. Deployment remains off.

There is one remote full-gate slot, alongside four remote verification slots.
The full gate uses CPUs 16–23 (SMT siblings, not eight additional physical cores),
Go parallelism four, nice 10 and a 12 GiB limit. A rootless, networkless container
uses the existing pinned Python image and Go toolchain. Its persistent cache is
`/data/factory-ng/full-gate-cache`, independent of verification cache cleanup.
The host `full-gate.lock` and orphan-container check prevent overlapping full gates;
Podman and its supervisor bound execution to three hours. Completed job directories
are removed, and idle full-gate cache cleanup uses the existing 40 GiB / 30 GiB
free-space thresholds. Existing model containers continue running.

`factory_ng_full_gate_remote.py` binds source revision/tree, corpus digest, tag and
ordered gate commands in a hashed manifest. A green response requires every gate
(or its matching bounded cache retry), a matching patch digest, generated-card-only
paths and regular-file modes, and an identical reconstructed result tree. Invalid
imports roll back the disposable clone before local fallback. Actual red gates
remain red; they never trigger a retry locally to hide a failed remote check.
SSH/transport/invalid-evidence errors run the complete gate locally and back off
remote full gates for five minutes. State is in
`state/factory-ng-full-gate-remote.json`; receipts record `execution.full_gate_host`
and per-gate `execution_host`. A full gate already admitted finishes when the
manual compilation switch is turned off, consistent with local integration.

Set `integration.remote.enabled=false` under dispatcher-admin to return new
integrations to local execution. Existing integrations finish with the policy
snapshot they read at admission. No controller restart is needed; each integration
is a new process. Do not kill an active integration to force a routing change.

### Remote verification on the Ryzen 395

New source pins transfer as incremental Git bundles against the mirror's known
snapshot. The exporter verifies that baseline locally; Git requires it during
remote import. An empty mirror still receives a full bootstrap bundle. This
avoids repeatedly packing the full source history for concurrent verifier slots.
The exact full-bundle 300-second export timeout has one controller-owned transport
recovery allowance per unchanged proposal, bound to its manifest/result hashes
and original identity. No model allowance or verification gate is reset.

`verification.remote` in the policy enables additional verification slots on
`dani@192.168.1.251` (`id: ryzen-395`, `slots: 4`). Up to two local verifier processes, four remote
verifiers and one integration coordinator can overlap. Remote batches use the same pinned proposals,
scope checks and ticket gates. Only the canonical server publishes validated
receipts and performs final integration. There are no model/provider credentials
in the remote verification container and no new drafting worker is created.

The remote runner uses rootless Podman, a pinned Python 3.12 image and the existing
Go 1.25.0 toolchain copied into `/data/factory-ng/toolchain`. Jobs, source mirror,
module cache and build cache live under `/data/factory-ng`; the existing llama
containers are untouched. The sixteen-CPU pool 0–15 is divided into four disjoint
four-core slots with process affinity (rootless cpuset cgroup delegation is
unavailable), nice 10, a 16 GiB memory limit per job and no container network.
Go uses four-way concurrency. The machine has 16 physical cores / 32 hardware
threads. Completed
job directories are removed; the persistent build cache is cleared under the
exclusive cache lock above 40 GiB or below 30 GiB free disk space. Each running
container holds a shared cache lock through its host supervisor; cleanup also
checks for orphaned verification containers before touching the cache. Source
mirror refresh/clone is separately serialized, and every slot has its own lock.

`factory-ng-verify-remote.py` transports selected contracts and artifacts over SSH,
includes referenced measurement files and checks returned ticket/input/patch
hashes, identities and every required gate,
then publishes immutable receipts. `execution.verification_host` identifies remote
results. A controller-side proxy PID preserves existing watchdog/reconciliation.
The dashboard switch is mirrored to remote policy while the job runs (three-second
poll); the executing gate finishes, and following gates honor the updated switch.

Previously isolated proposals are checked individually on the remote machine;
they are never recombined into a failed batch. Remote gate failures are marked
for local repair so the same unchanged patch cannot loop between remote slots.
Transport failures retain original proposals for local batch verification and
back off the remote host for five minutes. Actual gate failures retain the existing
individual repair path. Remote processes have a three-hour deadline; only the
unique job container is stopped during cleanup. Podman also enforces the deadline
if a proxy/supervisor disappears. Status/backoff is recorded in
`state/factory-ng-remote-status.json`. Setting `verification.remote.enabled=false`
stops new remote admission; active checks finish. Slot locks prevent duplicate
admission even if controller processes are interrupted. No canonical lock is weakened.

Read-only diagnostics:

```bash
ssh -o BatchMode=yes dani@192.168.1.251 'podman ps; df -h /data'
cat state/factory-ng-remote-status.json
```

GET/POST `/factory-ng/compilation` reads or updates `{"enabled":false}` (or true).
Updates atomically preserve the remaining policy under dispatcher-admin. The
controller and harnesses reread it without restarting; reboot does not change it.
`python3 scripts/factory_ng_quiet.py --check` exits 75 while compilation is off.

Controller descendants and managed Go commands share host CPUs **6,11,12,19** at
**nice 10**, limiting them together to four of this container's eight logical CPUs.
The user restored this four-CPU budget on September 15 as the verification backlog
reached 54. These CPUs belong to four distinct physical cores. Each Go invocation
still defaults to two-way concurrency, allowing overlapping verification and
integration to share the larger allocation without changing build-cache flags.
The policy persists across restarts; existing Factory threads were updated live.
Controller reconciliation caches compact ticket/receipt lifecycle fields and
checks each file's inode, size, mtime and ctime on every pass. Restarting rebuilds
this in-memory cache; no cache deletion is needed for new or edited artifacts.
The September 14 measured warm-pass CPU reduction was 74%; see
`docs/factory-ng/reviews/2026-09-14-controller-cpu/README.md`.
The three legacy corpus-scan crons retain this CPU budget, without a time gate.
The existing Magefield nightly maintenance job also skips while compilation is
off (`--if-enabled-exec`); it cannot turn the switch on, and toggling the switch
does not itself deploy anything.
Source-analysis helper executables live durably in `state/go-helpers` and are
reused without `go run`; rebuilding a missing/changed helper requires compilation
to be enabled. Proposal files replace disposable clones while testing is off.
Manual commands outside the Factory harnesses are outside the dashboard switch.

A saved proposal contains the TicketSpec hash, source revision, model/worker
identity, a hashed binary-safe diff, and continuation/repair context. Resume
validates identity and hashes before restoring it. No proposal is represented as
accepted or integrated until its actual gates pass. Infrastructure retries retain
the proposal and have a separate bounded verification-attempt counter.

## Go cache maintenance

Managed Go invocations default to `GOMAXPROCS=2` and `GOFLAGS=-trimpath -p=2`.
This bounds each invocation's concurrency and lets identical packages reuse
compiled artifacts across disposable clone paths. All test selectors and the
six integration shards remain required. Explicit caller `GOMAXPROCS` and
`GOFLAGS` settings override the defaults. This is a per-invocation limit, not
an aggregate machine CPU quota. Changing build flags causes an initial cache
warmup; do not clean the cache to accelerate it.

Factory Go build and test gates use
`/opt/development/.gocache-magic` through `scripts/go-cache-run.sh`:

```bash
(cd /opt/development/test/openmagic/backend && \
  /opt/development/magic-ops/scripts/go-cache-run.sh test ./...)
(cd /opt/development/test/openmagic && \
  /opt/development/magic-ops/scripts/go-cache-run.sh exec bash scripts/test-cards-sharded.sh 6)
```

`scripts/gocache-guard.sh` checks hourly and retains warm build artifacts until
the cache reaches 40 GiB or filesystem free space drops below 20 GiB (with at
least 1 GiB of cache worth reclaiming). These are cleanup thresholds, not a
filesystem quota: usage can exceed them between checks or while gates drain.
Override with `GO_CACHE_CLEAN_AT_GIB` and `GO_CACHE_MIN_FREE_GIB`.
Cleanup closes admission to new Go gates and waits for active gates to drain.
A missing cache
artifact during an NG full gate gets one isolated-cache retry. Compile and
test failures are not cache failures and are never retried as such.

## Scheduled NG operations

- 06:30 daily: `scripts/factory-ng-daily-report.py --send`
- hourly: `scripts/gocache-guard.sh`
- continuous: controller reconciliation every 15 seconds and producer scans
  every 300 seconds
- continuous: watchdog audit every 600 seconds

There is no separate scheduled full regression run. Every accepted NG
integration already runs the full production gate.

## Logs and durable evidence

| Data | Path |
|---|---|
| Controller supervisor | `/tmp/orch/factory-ng.log` |
| Controller application | `state/factory-ng-controller.log` |
| Watchdog supervisor | `/tmp/orch/factory-ng-watchdog.log` |
| Watchdog application | `state/factory-ng-watchdog.log` |
| Current runtime | `state/factory-ng-runtime.json` |
| Jobs | `state/factory-ng-jobs.json` |
| Watchdog snapshot | `state/factory-ng-watchdog.json` |
| Worker authentication holds | `state/factory-ng-worker-pauses.json` |
| OpenRouter cooldown | `state/openrouter-cooldown.json` |
| TicketSpecs | `docs/factory-ng/tickets/` |
| Receipts and raw artifacts | `docs/factory-ng/runs/` |

Receipts and state files are the source of truth. Logs explain execution but
must not override a durable outcome.

### Testing backlog visualization

The dashboard's **Patches waiting for tests & merge** panel distinguishes saved
patches awaiting focused checks, focused verification in progress, accepted patches
awaiting integration and the full gate in progress. Click any stage for its ticket
list and time in stage. Counts use all active jobs, exclude superseded jobs and do
not change with work-table search/pagination. Several patches can share one full
gate; these are not enabled-card counts. The panel refreshes with the normal
30-second dashboard cycle and flags stale data.

TicketSpec Go build/test/vet gates now use a 30-minute deadline, matching the full
integration build allowance under the reduced CPU limit. Other ticket commands
retain 12 minutes. Timeout diagnostics report the deadline. A passed named test
alone does not satisfy a multi-package command that later times out.

### Empty supply and model leases (September 16)

`working` rows with `verification_batch: true` are deterministic test processes.
Their original `worker` field is attribution, not a model lease. Dispatch and
dashboard worker cards exclude these rows; individual verification/repair still
owns its worker because it may call that model. Inspect actual drafting processes
separately from the test queue when diagnosing idle Codex workers.

Harnesses now run gofmt only on scope-checked regular changed Go files, before
proposal hashing and verification. All original gates remain required; formatter
syntax errors return diagnostics to bounded repair. Formatting does not compile
or test and is permitted while compilation is switched off.

The finite `reviewed-harness-corrections-sep16` producer binds 276 reviewed
pre-semantic Engine failures to immutable receipts/contracts. It emits one
current-source successor per original only while a Map parent remains blocked;
Oracle and preparation checks, unchanged behavior/scope/gates, original ancestry,
normal queue admission and a 24-active cap all apply. Never append semantic
failures to this manifest or reset historical attempts to manufacture supply.
Evidence: `docs/factory-ng/reviews/2026-09-16-four-hour-workers/README.md`.
Its opt-in `refill_burst: 12` fills several reserve slots before slow discovery,
within the existing global sweep/admission budgets. New reviewed successors
prefer Codex among already compatible profiles. Admission duplicate checks use
fresh per-file metadata projections; original contracts remain hash-checked.
The bounded trial/context-retry scans run after reserve refill, once per cycle
even when the ordinary queue is full, with their original two-active limits.

An empty factory with enabled workers and no intentional pause now generates a
watchdog supply alert after ten minutes. This is a producer/demand problem and
does not cause the watchdog to restart a healthy controller.

A failed remote composition is not proof that every member requires model repair.
Multi-member failures retain `verification_isolate` and use remote singleton
checks; only a failed singleton or a transport failure sets the local fallback.
The controller can correct the former overbroad fallback flag on awaiting saved
proposals, once per proposal, with validated old result/contract/patch identities
and recorded result hashes. It does not change any attempt or repair budget.

If a burst refill source reaches its active cohort bound, the controller now
revisits it between slower producer commands once active jobs finish. This uses
the ordinary sweep budget and all existing admission caps. Unchanged
backpressure waits for real progress; it does not trigger a controller restart.

A resumed remote singleton with a proven Go compiler failure may receive
`--repair-evidence`. The runner validates the matching one-entry manifest and
proposal identity and preserves a hashed immutable evidence artifact before
using its existing correction allowance. It still runs scope/formatting checks
and every gate on the corrected candidate. Missing, mixed, stale or transport
evidence falls back to normal verification; repair budgets never reset.

When remote verification is available, a qualified resumed worker may receive
`--defer-repaired-verification`. A successful bounded correction becomes a new
untested proposal and releases its model lease. Parent proposal hash, changed
patch, original identity/contract, successful strict application, and spent repair
allowance must validate before old remote-failure flags clear. Queued verification
still runs every final gate; failed corrected proposals cannot gain another model
repair. Repair evidence/history/model-call counts remain in hashed artifacts.
