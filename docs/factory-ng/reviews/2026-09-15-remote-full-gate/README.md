# Full integration gate replay on Ryzen — passed

User requested a trial of running the full gate on the remote Ryzen. This was an
isolated replay of a completed local integration, with no live routing change,
canonical mutation, new commit, push or deployment by the trial.

## Result

All seven original TicketSpec semantic contracts and all six production gate
stages passed. The generated Git tree exactly matched the locally accepted tree:
`7ed561f4ab172ec72291e45d27028cdb361870ec`.

| Stage | Local seconds | Remote seconds |
| --- | ---: | ---: |
| original-ticket-checks | 36.2 | 3.1 |
| reparse-flip | 122.4 | 12.4 |
| reparse-import | 22.8 | 3.3 |
| go-build | 30.2 | 23.6 |
| game-tests | 6.1 | 18.0 |
| focused-go | 30.7 | 21.6 |
| full-sharded-suite | 176.8 | 25.3 |

Comparable recorded checks: **425.178 seconds local, 107.343 seconds remote**,
about **3.96× faster in this one replay**. The remote runner took 107.718 seconds
including input validation and tree comparison. Source transport and private cache
preparation took another 7.007 seconds, excluding local packet preparation.
Peak container memory was 4.77 GiB, with no OOM events. The full six-shard suite
includes the existing cardfns vet/test step, which also passed.

## Inputs and limits

Local reference finished at 15:49:40 UTC. Remote replay launched at 15:58:52 UTC.
The input was the parent of its generated-corpus commit:
`395dacbe761a3ab136ec4afb45ae99da4a58c177`; expected result commit was
`892a61d4b6e3db3caeee934f0b5543e61159201c`. Both are immutable objects read from
canonical Git. Replaying the original tag and corpus reproduced the same 11
card flips. Ticket and measurement files and AtomicCards input were SHA-256
checked before execution. Original semantic checks ran through the production
integration helper; production full-gate commands were replayed verbatim except
for the Python executable location in the container.

Remote: pinned existing Python 3.12 image, Go 1.25.0, rootless Podman, eight allowed
logical CPUs 16–23, nice 10, GOMAXPROCS=4, Go -p=4, 16 GiB memory limit and no
network. These CPUs are SMT siblings of physical cores also available to existing
verification slots; this is not eight extra physical cores. Existing four remote
slots and model containers were left enabled. The trial used a private copy of
the remote build cache, so cleanup could not remove live cache artifacts.

Local reference: existing four-CPU factory pool, GOMAXPROCS=2 and -p=2, under the
live workload at that time. Both used the same effective Go 1.25.0 toolchain.
Cache warmth and concurrent workload were not controlled. This proves feasibility
and one observed runtime improvement; it is not a sustained throughput benchmark.
The slower remote game-test stage includes compilation; its test execution itself
reported 0.029 seconds.

## Handoff

Full production integration remains on the main server. No automatic acceptance
of remote full-gate results has been implemented. The next implementation would
need to bind returned evidence and generated content to the exact composed tree,
then let the canonical server check that its base has not moved before landing.
Existing canonical locks and all gates must remain authoritative.

Evidence: local-reference.json, manifest.json, runner-hashes.json, launch.json,
launch.log, result.json, comparison.json and per-stage logs. replay.py, prepare.py
and launch.py retain the exact trial procedure (paths are specific to this trial).
The trial container auto-removes, and its private source/cache directories are
removed after evidence retrieval. Source status is checked through the standard
health script; an active integration retains ownership of the canonical checkout.
