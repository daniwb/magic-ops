# Controller reconciliation CPU reduction — 2026-09-14

An eight-second `/proc` CPU-delta sample measured the live controller at 99.8%
(one logical core). Its inventory contained 6,433 ticket files (106 MB) and
19,472 run JSON artifacts (577 MB). Receipt contents were already cached, but
reconciliation reread all TicketSpecs and scanned receipt metadata twice.
Producer sweeps call reconciliation repeatedly to keep worker leases moving.

The controller now retains compact ticket lifecycle projections, refreshes
changed artifacts using `os.scandir`, and derives observation and integration
indexes from one receipt snapshot per reconciliation. Every file is statted
on every refresh. Inode, size, nanosecond mtime and ctime invalidate cached
content; replacement, edits, partial publication, deletion and missing
directories are covered. Full TicketSpecs remain authoritative for worker
packets and gates. Policy, lease ownership and admission intervals are unchanged.

During diagnosis the dependency producer was also failing in the shared symbol
resolver because `hashlib` was used without an import. Restoring the import
allows current-source evidence resolution and dependency production to proceed.
Knowledge resolution tests exercise the previously failing path.

Warm reconciliation CPU fell from **13.572 seconds to 3.500 seconds (74.2%)**.
Measured wall time was 45.447 versus 4.288 seconds under concurrent load;
CPU time is the less load-sensitive comparison. All 6,428 existing reconciled
jobs were identical. The cache starts cold after restart and rebuilds in memory.

The 117-test controller/lifecycle/cache suite passed 116 initially; one existing
real-corpus producer test returned no ticket under concurrent load and passed
when rerun alone. An additional 18 knowledge tests and nine
verification tests passed (144 distinct checks altogether). The producer test's
first failure and successful rerun are retained in the logs.

`controller.patch` contains only this task's reconciliation changes. Verification
batching was being edited concurrently in the same controller; those independent
changes were preserved. Other edits are the missing `hashlib` import, cache
regressions, and test fixtures updated for `scandir` and removal of scheduling.

Validation and activation results are recorded alongside this note. Benchmark
runs disable job/worker-pause writes and do not dispatch work. Compilation/testing
remains controlled by the dashboard switch, with shared CPUs 12,19 and nice 10.

The supervised controller restarted during concurrent verification work before
this session sent its reload signal. Successor PID 2824556 loaded the changes;
a second reload was unnecessary. After cache warmup, an eight-second live CPU
sample measured 15.6%, versus the initial 99.8%. These are workload-dependent
samples, not a CPU ceiling. The controller dispatched a worker and continued
production. Canonical openmagic was clean and compilation remained off.
