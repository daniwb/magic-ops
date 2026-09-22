# Bounded verification and integration overlap

The user requested parallelism to drain the testing backlog. The controller now
supports `verification.overlap_integration=true`: one central verification batch
or individual fallback may run alongside one integration wave. Each uses its own
disposable checkout and original pinned contracts. Integration keeps its exclusive
canonical mutation lock and all final-composition/full-production gates.

The existing shared CPU affinity (12,19), nice 10, per-Go defaults, cache maintenance
barrier, manual compilation switch and model repair limits are unchanged. There
is no additional CPU allocation. Throughput improvement has not been measured;
the overlap can use capacity during single-process parsing and preparation, but
CPU-heavy stages compete for the same two CPUs.

The default without this setting remains serial. Disabling it lets active jobs
finish and prevents new overlap. Accepted patches retain integration admission
priority; only one integration can run, regardless of verification policy.

Validation: 102 tests passed, including overlap in both directions, batch member
grouping, duplicate-start exclusion, serial fallback, the manual switch, original
verification/repair contracts and the shared Go cache maintenance barrier. An
initial command included a nonexistent test-module name; the corrected complete
run passed and is recorded in `tests.log`.

`controller.patch` records the change against the pre-turn controller;
`policy-before.json` records policy before enabling overlap. No game source edits
or deployment were performed.

Live activation: the controller restarted at 08:55:33 UTC. `live-overlap.json`
records integration PID 4021982 with seven tickets and verification PID 4055307
with five tickets alive simultaneously, both restricted to CPUs 12,19. These are
in-progress batches, not completed or accepted-card throughput measurements.
