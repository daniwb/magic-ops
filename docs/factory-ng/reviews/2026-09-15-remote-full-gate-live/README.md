# Remote full production gate — enabled

At the user's request, `integration.remote.enabled=true` was activated under the
dispatcher-admin lock at 2026-09-15T16:12:40Z. New integrations route all six
production stages to the Ryzen: corpus flip/import, Go build, game tests, focused
cards and the complete six-shard/cards/cardfns suite. Existing integrations finish
using their initial policy snapshot; no worker or controller was killed.

The canonical coordinator retains candidate composition and original semantic
checks, the process-held integration lock, final source/base checks, generated-data
commit, fast-forward and policy-controlled push. Live deployment remains disabled.

One remote full gate uses eight logical CPUs 16–23, Go parallelism four, nice 10,
12 GiB memory, a rootless networkless container and a three-hour deadline. These
are SMT siblings of cores available to focused verifiers. Four focused remote
slots remain enabled. The dedicated persistent full-gate cache and host lock keep
verification cache maintenance independent and prevent duplicate full-gate jobs.

Source revision/tree, corpus digest, commands and tag are bound in a hashed
manifest. Import checks the exact ordered gate list and successful cache retries,
patch digest, generated-card-only paths/regular file modes and reconstructed Git
tree. Invalid patch imports restore the disposable clone before local fallback.
A valid red gate blocks the wave. Transport/invalid-evidence failures fall back to
the full local gate and impose a five-minute remote backoff; they cannot publish
an untested tree. Receipts identify the execution host and returned tree.

Validation: all 60 regression checks passed (including nine new import/fallback
checks); 13 focused checks passed after final cleanup. A real production transport
pilot passed all six full-gate stages and reconstructed the known locally accepted
tree `7ed561f4ab172ec72291e45d27028cdb361870ec`, without committing or landing.
Transport, checks, import and cleanup took 126.614 seconds in that pilot.
See transport-pilot.json/log and test logs. Earlier full-gate comparison is in
`../2026-09-15-remote-full-gate/`.

At handoff, the pre-activation integration PID 378845 was still compiling its
original Engine ticket checks locally. No live remote integration completion was
claimed; the real remote transport/import pilot passed, and the persisted policy
was read back as enabled. See handoff.json for the timestamp and active jobs.
Rollback: set `integration.remote.enabled=false` under dispatcher-admin; active
integrations finish and later integrations run locally. Policy is read by each
integration process, so no controller restart is needed.

Follow-up: live remote integration was observed at 16:48:57 UTC, and original
semantic checks moved remotely at 16:51:43. Multiple subsequent live waves passed
and pushed. See [queue-drain evidence](../2026-09-15-queue-drain/README.md).
