# Native-host recovery (2026-09-18)

This snapshot publishes the native-host Factory NG fixes together with previously
unpublished source modules required by the running controller. It excludes live
queue state, logs, credentials, host worker/policy configuration and unrelated
dashboard changes. Review before merging; this is not a complete host backup.

## Host layout

The host uses `/data/magic-stack` with `development/magic-ops`,
`development/test/openmagic`, `development/magic-new`, `toolchain/go/bin`,
and `pydeps` underneath it. `FACTORY_NG_SOURCE` can override the engine checkout.
Install Python extension dependencies for the host Python version; copied binary
extensions from a different Python version are not compatible.

`launchers/start-magic-control-native.sh` is the repository copy of the host
supervisor. It accepts `MAGIC_STACK_ROOT` and requires the configured service
binaries, Python dependencies, tmux, codex and claude. Do not run a second
supervisor while the existing host startup process is running. Keep `.env` local.

The controller launcher uses the `dispatcher:factory-ng` tmux window. The watchdog
recognizes native absolute paths and parses UTC timestamps independently of the
host timezone. Go cache execution discovers Go from PATH. Legacy ticket gate
paths are translated at execution time without rewriting immutable contracts.

## Validation and scope

The reliability (24), focused-batch (12), gate-timeout/path (3) and Go-cache (4)
tests pass with the native Go toolchain on PATH, `PYTHONPATH` pointing at host
dependencies and `FACTORY_NG_SOURCE` pointing at the engine checkout.

The baseline control suite has a policy assertion expecting only three usage
policies, while the checked-in worker configuration also uses
`openrouter-cooldown`. The larger unpublished local version of that suite also
depends on old `/opt/development` paths, local policy and generated ticket fixtures.
Neither suite is claimed fully passing by this publication. Live policy and
worker configuration are deliberately not overwritten by this source snapshot.

Reviewed engine recovery patches and receipts are in
`reviews/2026-09-18-local-recovery/`; the engine fixes were already integrated and
pushed separately to `openmagic/main` through full gates.
