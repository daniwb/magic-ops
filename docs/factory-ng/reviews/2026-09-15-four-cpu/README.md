# Four-CPU factory allocation

The user requested restoring four CPUs as the focused-verification queue reached
54. Live jobs showed concurrent integration and verification restricted to CPUs
12,19. The pre-change six-second sample observed 1.59 CPU equivalents among the
tracked factory processes, including a compiler and test shard competing on that
same mask. The container exposes eight CPUs without a cgroup CPU-time quota.

At 12:44:07 UTC, policy was atomically updated under dispatcher-admin to CPU mask
6,11,12,19. Topology checks confirmed four distinct physical cores. The controller,
active job roots and their descendants had 114 threads updated in place. No
process was killed/restarted and no canonical source was edited.

Verification found no affinity mismatches among 34 still-live threads inspected
after activation. A fresh managed command used the same four CPUs at nice 10.
Live Go environments retained GOMAXPROCS=2 and GOFLAGS=-trimpath -p=2. This expands
the aggregate factory budget; each Go invocation retains its existing concurrency
and cache configuration. Bounded overlap, all gates and compilation policy remain.

An eight-second follow-up sample observed 2.92 CPU equivalents among tracked
processes, including two compiler processes. The workload advanced between samples;
this establishes use of added capacity, not a controlled speedup benchmark. The
backlog's sustained drain rate is not yet established. No cache cleanup or deployment.

Evidence: `policy-before.json`, `activation.json`, `cpu-before.json`, `cpu-after.json`.
