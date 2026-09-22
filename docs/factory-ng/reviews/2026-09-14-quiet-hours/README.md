# Off-hours Factory admission and aggregate affinity — 2026-09-14

User request: reduce development-machine CPU/noise and compile overnight; the
previous batching/cache session did not make the machine quiet enough.

## Finding

Eight logical CPUs are available in this container, with non-contiguous host
CPU IDs. Initial 3-second /proc CPU-delta sample: two Factory compilers used
325.4% combined, integration reparse 96.3%, controller 94.0% (515.7% in those
processes alone). A separate interactive census used 101%; it was not changed.
`ps %CPU` was misleading on this container, reporting zero alongside anomalous
process elapsed times. Measurements therefore use deltas of /proc CPU ticks.

Previous changes supplied trimpath/cache reuse, per-Go GOMAXPROCS=2 and p=2,
and bounded integration batching. They did not close daytime admission or put
all concurrent invocations under one shared CPU budget.

## Active policy

- Automatic producers, worker leases and integration starts: daily 22:00–07:00
  Europe/Zurich, using zoneinfo for DST. This was the stated default; no alternate
  window was supplied during implementation.
- Work already running drains safely; no hard deadline or job termination is
  claimed. Completed receipts reconcile during quiet hours; accepted patches wait.
- All controller descendants and managed Go commands share host CPUs 12,19 at
  nice 10. This limits their combined execution to two logical CPUs. Existing
  active Factory trees were moved by exact PID/ancestry, including every thread.
- The cron entries for legacy refill-map-queue, flip-frontier and miss-tracker
  now use --scheduled-exec; skipped daytime runs exit successfully.
- Manual Stop remains authoritative. Supervised reloads/Start cannot bypass the
  clock. Watchdog suppresses expected no-progress alarms during scheduled pauses
  while retaining process-health and real integration-failure diagnostics.
- Full gates, cache cleanup barrier, push policy and live deployment policy remain.

Policy lives in config/factory-ng-policy.json; behavior is documented in RUNBOOK.
The schedule is enforced at every admission path, including producer callbacks,
and in a cheap quiet-hours reconciliation path. No waiting Go wrapper is placed
inside worker timeouts. Manual Go commands through the cache runner receive the
resource budget but are not clock-blocked. Unrelated interactive processes are
outside this automation policy.

## Validation and activation

102 focused tests passed: six quiet-hours/resource tests, seven batching,
67 controller, three non-compiling cache-barrier/resource checks and nineteen
reliability checks. The final quiet-hours tests were rerun after resource/queue
refinements. No game or dispatcher binary was compiled for this change.

Tests cover start/end boundaries, summer/winter and DST changes, invalid-policy
closed admission, daytime reconciliation without dispatch, admission closing
inside a sweep, child affinity/priority inheritance, and existing gate/recovery
behavior. A scheduled daytime sentinel command was verified skipped.

Activation used dispatcher-admin for atomic policy replacement, crontab updates
and exact controller/watchdog PID reloads. Original crontab:
/tmp/magic-crontab-before-quiet-20260914. No worker/integration was killed.
Dashboard API confirmed quiet_hours_draining and next_start
2026-09-14T22:00:00+02:00. The successor controller was observed at nice 10 with
affinity [12,19]. A 5-second sample after throttling measured 162.8% across the
active worker/integration trees plus about 20.6% in the draining controller:
roughly 1.8 logical CPUs versus the earlier 5.2 in sampled Factory processes.
These are short samples, not a noise measurement or a throughput forecast.

Canonical source was owned by the in-flight NG integration; no source files were
changed by this task. Existing five integration failures predate this work.
