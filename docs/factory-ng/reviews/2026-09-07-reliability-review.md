# Factory NG reliability review — 2026-09-07

Review of the live checkout, controller/dashboard/watchdog state, receipts,
cron and tmux configuration, recent staged evidence fix `1418caf`, and the
OKF/bulk-read experiment. Snapshot collected approximately 11:00–11:20 UTC.
Production code, configuration, jobs, receipts, and Git operation state were
not changed. This document is the review deliverable, not a recovery receipt.

## Result

The zero-output complaint is confirmed. The last observed `auto` increase
was **2026-09-06 10:07:06 UTC**, to **12,400**; the latest card-history sample
still has 12,400. The approximately 24-hour delta is zero; the approximately
48-hour delta is +151. This system can produce cards, but several control
and acceptance defects strand useful work and conceal the resulting outage.

Current jobs: 348 queued, 921 blocked, 842 parked, 1,302 failed, 115
integration_failed, 337 completed. All three enabled workers use the same
Claude account, currently paused at its 71% daily unlocked weekly tranche
until September 7 at 18:00 UTC. Qwen, MiniMax, and Codex are disabled. This
pause is expected under the configured daily pacing policy; it is separate
from the broken integration path and cannot explain away failed landings.

## Findings, in repair priority order

### 1. P1 — Two live integrators do not share the canonical mutation lock

`scripts/integrator-lite.sh:23` uses `/tmp/integrator-lite.lock`; NG uses
`/tmp/orch/openmagic-integration.lock`. The legacy cron still invokes
integrator-lite every 15 minutes. It merges, aborts, resets, pushes, and
deploys from the canonical checkout without either NG scoped lock. Its
deployment also bypasses NG's disabled-by-default deployment decision.

This is an actual concurrent system, not merely dead code: legacy logs show
successful landing/deployment at September 6 09:43 and 10:06. NG has 15
terminal jobs reporting `canonical checkout changed during full gate` and
21 reporting a dirty canonical checkout. At 16:00:37, the legacy log reports
`error: Unable to write index.` while handling `reparse/task-5350`, then calls
the event a merge conflict. The canonical MERGE_MSG names that same branch;
MERGE_HEAD dates from that second. Subsequent legacy cycles only log
`local main not ff-able — skip`.

The evidence connects the stranded merge to the legacy merge/abort path;
it does not prove whether disk pressure, an index race, or another cause
produced that particular index-write error. `git merge --abort`'s exit status
is ignored at line 88, so a failed cleanup does not stop/report recovery.

Repair: establish one owner for canonical integration. Retire the legacy
mutation lane or make all its canonical and deploy operations honor the
same scoped locks and policy. Preserve and inspect the stranded merge before
recovering it. Do not simply reset the shared checkout or conclude an
ungated merge. Also correct the reboot launcher, which recreates legacy
`r1` and `rf1` workers alongside NG.

### 2. P1 — An unfinished merge passes preflight; infrastructure failures strand accepted patches

`scripts/factory-ng-integrate.py:109` defines clean as empty
`git status --porcelain` stdout and does not check the command's exit code or
in-progress Git operations. On the real canonical checkout, this function
returns **True** while `.git/MERGE_HEAD` exists. Full `git status` says
“All conflicts fixed but you are still merging.” The startup check has the
same blind spot. HEAD and origin/main are equal; there are no file diffs.

**54 integration receipts** passed their production checks and then failed
canonical fast-forward with MERGE_HEAD. Their recorded gate time totals
approximately **10.1 hours**. Example:
`docs/factory-ng/runs/2026-09-07T045313Z-engine-auto-tap-or-untap-choice-target-21af274c97-v1-integration.json`.

`scripts/factory-ng-controller.py:809` makes integration infrastructure errors
terminal immediately. Worker infrastructure retries do not apply here.
`sync_jobs()` excludes integration_failed jobs from observation recovery;
`scripts/factory-ng-produce-capability-dependency.py:614` just waits for these
children forever. Of the 115 failed integrations, 94 are infrastructure
failures, 20 candidate conflicts, and one a full-gate failure.

Repair: fail preflight on merge/rebase/am/cherry-pick state, check Git command
success, pause integration on shared-source faults, and retain accepted
patches for bounded integration-only retry after readiness recovers. Retry
and conflict handling must have separate counters from model attempts. Do
not regenerate already accepted code just to repair a landing failure.

### 3. P1 — Successful bounded repairs can never be accepted

`scripts/factory-ng-run-engine-ticket.py:272` retains the initial patch failure
as a failed gate. After repair, line 326 requires **every** historical gate
to be passed. The dedicated Map runner has the same defect at lines 174/233.

**63 receipts** have a passed final patch application and no failed gate
except `initial-patch-apply`, yet are classified `gate_failed`. Example:
`docs/factory-ng/runs/2026-09-06T235426Z-engine-auto-damage-recipient-attacked-target-8aa9c754cc-v2-claude-agentic-test.json`.
Its scope, required named test, package tests, and diff check all passed.

Repair: preserve attempt history separately from the final candidate verdict.
Accept only after all checks of the final repaired candidate pass. Add
regressions for successful repair, failed repair, and repair that passes
application but fails a semantic gate. Historical candidates still require
fresh validation before recovery; this finding does not authorize mass acceptance.

### 4. P1 — Required Engine tests can silently run zero tests; integration omits game tests

The producer requires an exact `TestFactoryNG...` function, but
`scripts/factory-ng-run-engine-ticket.py:323` checks only command exit status.
Go returns success when the filter matches nothing. **130 accepted Engine
receipts** show `[no tests to run]` for both game and cards in the named gate.

Concrete staged example:
`docs/factory-ng/runs/2026-09-06T191504Z-engine-auto-damage-amount-formula-hand-size-subtracted-24ab5ad428-v1-claude.json`.
The ticket requires `TestFactoryNGDamageAmountFormulaHandSizeSubtracted`;
the patch defines `TestDamageAmountFormulaHandSizeSubtracted`. The broad
game/cards gate did run afterward, so this is not evidence that this patch
had no test coverage. It proves the declared focused gate is unenforced.

On integration, `scripts/factory-ng-integrate.py` runs a production build,
focused cards tests and `scripts/test-cards-sharded.sh 6`. The shard script
runs cards and cardfns tests, **not game tests**. New Engine tests under game
therefore are not rerun after composition onto current main. `go build
./...` does not compile `_test.go` files.

Repair: require an executed, passing named test (including its count), and
rerun the ticket's relevant semantic gates plus game tests on the composed
integration revision. Do not weaken or rename failed TicketSpec requirements.

### 5. P1 — Watchdog and daily report can declare a persistent outage healthy

`scripts/factory-ng-controller.py:925` replaces the runtime snapshot during
production without queue/deferred counts. The watchdog defaults missing
counts to zero at `scripts/factory-ng-watchdog.py:152`. During that common
phase it sees no runnable/deferred work and suppresses its no-progress check.
Live evidence: 10:58:33 watchdog snapshot says healthy=true, moving=false,
348 queued jobs, runnable=0, deferred=0, problems=[].

Accepted observations also count as productive movement even if no patch
lands. No card-output clock, canonical Git operation check, or persistent
integration-failure alarm closes that gap. Separately,
`scripts/factory-ng-daily-report.py:114` excludes unresolved failures older
than one hour from its health calculation. A stranded job effectively ages
out of the alarm while remaining broken; a producer can count as “running.”

Repair: keep complete queue state across phases; distinguish unknown from
zero; retain unresolved system faults until recovery; track last successful
integration and enabled-card movement separately from accepted attempts.
Report a configured quota pause with its resume time. A persistent shared
Git fault needs a persistent alert, not repeated controller restarts.

### 6. P1 — Receipt reconciliation depends on directory enumeration order

`scripts/factory-ng-controller.py:264` overwrites each ticket's selected
observation while traversing unsorted `RUNS.glob()`. Filesystem order is not
attempt order. Comparing its real output with timestamped filename order
found **226 different selected receipts**, including **204 different
outcomes** and **13 cases selecting an older failure over a later acceptance**.
Some already completed jobs are protected by integration reconciliation;
these counts are not counts of newly lost cards.

Example: `ticket:engine.auto-return-from-graveyard-mv-le-power-filter-23d0ea5778/v3`
selects September 5 16:14's protocol failure instead of September 5 18:18's
accepted observation. Current job state is parked. Supersession must also be
considered before deciding which historical work should recover.

Repair: use explicit deterministic attempt ordering, supersession, and
completed/integrated precedence. Test shuffled directory listings and state
reconstruction from receipts. Sorting by modification time alone is fragile
under restore/copy; use recorded attempt identity and time.

### 7. P2 — The OKF trial is not measuring OKF, and its 5% allowance is not enforced

The experiment config adds an OKF MCP server over five hand-seeded Factory
policy/rollout notes. These are not Engine capability or parser knowledge.
Across **21 observation receipts / 25 available model-call transcripts**:

- 12 accepted observations, six gate_failed, two protocol failures, one
  infrastructure failure;
- zero recorded OKF tool calls;
- zero delivered `Direct Read blocked:` summaries;
- 166 Read calls: 142 explicitly scoped, 24 whole-file calls.

The available traces cannot establish whether every hook invocation was
eligible or why it passed through. They do establish that these results
provide no observed treatment effect for either OKF retrieval or summarization.
The trial combines two interventions and uses different live tickets from the
baseline, so acceptance/token differences are not a causal comparison.

`weekly_gate_pct=5` is also ignored in paced mode. The controller exports
WEEKLY_GATE_PCT, but `scripts/lib-pace-gate.sh:90` computes the daily ceiling
from PACE_TARGET_PCT (default 100). A local calculation with configured
percentages 5 and 95 returned the same effective ceiling, 71, for both.
This is not an isolated 5% experimental spending budget.

Repair: define an actual trial allowance, record retrieval/hook decisions,
and run a bounded matched benchmark with frozen tickets and source, changing
one component at a time. No evidence here supports promoting OKF or claiming
token savings. Keep card-knowledge and operating-policy memory conceptually
separate; the former is directly relevant to Engine work.

### 8. P2 — Card-knowledge restart/reboot recovery remains unwired

`launchers/launch-kb.sh` contains supervision, but the live `kb` pane runs
`exec python3 scripts/card-knowledge-service.py` directly.
`scripts/dispatcher-reparse-launch.sh` does not start that launcher or any KB
pane. Thus a crash loses this dependency, and the reboot script does not
restore it. This is the same class of outage already recorded in CURRENT.md.
The service is healthy now; its periodic reindex is present, so a permanently
stale index is not claimed as a current defect.

Repair: wire the existing supervised launcher into startup and probe it from
the watchdog. Exercise restart/reboot behavior before calling this resolved.

## Staged fix assessment

`1418caf` makes a useful correction: it retains the actual capability
specification (including examples) and resolves named functions against live
source before consuming weak producer anchors. Keep that improvement.

It is not a complete evidence fix. Extraction still caps each function at
150 lines and the shared code budget at 420; only selected identifier forms
are resolved. Old anchors can still consume the remainder. No dedicated
regression test for this resolver was found in scripts/test*.

For September 6–7, the available staged receipts contain 145 attempts:
44 accepted, 66 parked, 32 gate_failed, three protocol failures. These are
attempt outcomes across different tickets, not matched benchmark results,
and “accepted” does not mean integrated or semantically audited. The required
named-test issue above also affects staged acceptance claims. Improve the
harness before interpreting this as model-quality evidence.

## Additional consistency issues

- `factory-ng-profile-validate.py` currently fails on the MiniMax adapter
  enum. Several runtime-supported profiles are absent from its registration
  table. CURRENT.md already acknowledges part of this drift.
- Both runners clone canonical HEAD but record the ticket's pinned revision
  as execution.source_revision without checking out that revision. Record
  the actual tested revision or explicitly repin through a successor ticket;
  do not claim an execution pin that was not enforced.
- CURRENT.md retains conflicting automatic integration/push statements and
  describes a single-worker rollout while three workers are enabled. The
  live policy is automatic integration/push with live deployment disabled;
  the legacy lane contradicts that operational boundary.
- Startup still probes legacy `/pilestats`, reports DOWN after two timeouts
  while the NG dashboard works, and checks the legacy queue. The reboot
  launcher still contains broad pkill cleanup. Update these entry points as
  part of migration completion.

## Validation and concrete recovery sequence

The existing **64 control-plane tests and two daily-report tests pass**.
The profile validator fails as above. Read-only/local mocked reproductions
confirmed that real preflight accepts MERGE_HEAD, a transient integration
failure becomes terminal without backoff, a producer-phase snapshot can
make queued stalled work appear healthy, and 5/95 paced settings produce
identical ceilings. Receipt and saved transcript counts were computed from
local artifacts; no model benchmark, API messaging, merge, push, deployment,
or runtime configuration change was performed.

Recommended implementation order:

1. Unify integration ownership and preflight; preserve the existing merge
   evidence, recover the canonical Git state under its scoped lock, and
   verify no other process can recreate the collision.
2. Fix repair verdicts, named-test execution, and composed Engine gates.
   Add deterministic regressions using the concrete failure shapes above.
3. Fix receipt ordering and integration-only retry. Recover a bounded set
   of accepted infrastructure failures through fresh full gates, then drain
   compatible candidates. Keep genuine candidate conflicts/semantic failures
   separate; do not blindly requeue all terminal jobs.
4. Fix persistent progress alarms, daily health reporting, and KB startup.
   Respect the existing quota policy unless the operator changes it.
5. Verify a fresh producer → worker → integrated patch → Map successor →
   enabled-card trace, then observe across a quota boundary and a full day.
   Check both card delta and unresolved infrastructure faults. Passing unit
   tests or merely restarting the controller is not sufficient evidence of
   unattended operation.
6. Reassess staged versus agentic performance and the OKF experiment after
   the execution and landing paths are trustworthy.

The factory remains operationally blocked at the end of this review. The
canonical file tree is unchanged, but the pre-existing unfinished merge is
still present and requires controlled recovery.

## Authorized repair follow-up — September 7, 11:59 UTC

The preceding sections preserve the pre-repair review. After authorization,
the landing collision and stale merge were repaired, integration-only recovery
and compatible waves implemented, and repair verdicts, named-test execution,
pinned revisions, receipt chronology, quota ceilings, supervision, and persistent
health reporting corrected. The staged evidence fix is retained and regression
tested. The unmeasured OKF/shunt trial is disabled; shunt telemetry is available
for a future matched experiment. Enabled production profile validation passes;
the broader experimental profile audit remains intentionally unresolved.

Verification: 81 Python tests and dispatcher Go tests pass, including a real
temporary-Git conflict/isolation/push-retry fixture. Live wave
`runs/2026-09-07T114302Z-wave-9450f1f58dc0-integration.json` passed the complete
production gates and pushed `3f7c050b2fe0c367f9dc5d447734972e0039cddf`.
Two candidates landed, five conflicts and one zero-matching-test contract were
excluded. Enabled cards increased **12,400 → 12,401** and another wave started
automatically. Canonical source is clean; live deployment remains disabled.

The recovery is demonstrated, but a fresh model-to-card cycle across the next
quota boundary and a full 24-hour unattended soak are not yet observed. Current
operating details are in `../CURRENT.md`; historical failed jobs remain visible.
