# AGENTS.md — magic-ops (Factory NG infrastructure)

You are the OPERATOR of the Magic card-engine Factory NG. This repo holds the
TicketSpec producers, controller, isolated worker harnesses, receipts,
integration gates, dashboard, watchdog, policy, and scheduled maintenance.

## FIRST ACTIONS, always, in order
1. **Load the canonical memory** — it lives with the magic-new project, NOT
   here: read `~/.claude/projects/-opt-development-magic-new/memory/MEMORY.md`
   and follow its index (session-startup protocol, operating model, Factory NG
   policy). Everything below is a bootstrap summary, not a replacement.
2. Run `bash scripts/session-health-check.sh` (from this repo).
3. Inspect `http://localhost:9999/dashboard`,
   `state/factory-ng-watchdog.json`, `/tmp/orch/factory-ng.log`, and
   `/tmp/orch/factory-ng-watchdog.log`. Confirm the canonical `openmagic`
   checkout is clean whenever no NG integration owns it.

The old four-hour `/tmp/orch/operator.lock` is retired. Monitoring, analysis,
ticket production, and isolated-clone workers do not take a global session
lock. Shared mutations must use the process-held scoped locks documented in
`RUNBOOK.md`: integration, deployment, and dispatcher administration are
serialized independently and the kernel releases each lock when its command
exits.

## Emergencies
Read `RUNBOOK.md` in this repo — every component, restart command, and
known failure mode with its fix.

## The one-paragraph system
Deterministic producers compile bounded TicketSpecs from the measured Magic
corpus. The Factory NG controller maintains a runnable reserve, dispatches
compatible model-specific workers into isolated clones, records immutable
receipts, and sends accepted patches through a separate deterministic wave,
build, focused gates, and full six-shard integration. A green integration may
push according to policy; live deployment remains a separate explicit
decision. Models never receive commit, push, integration, deployment, or
live-ticket authority.

## Hard rules (each learned the expensive way — details in memory)
- Never bypass the gates; never pipe a test run into `| tail` in a chain.
- Tree in openmagic MUST be clean when you walk away (dirty blocks NG
  integration).
- pkill patterns match your own cmdline and tmux server — kill by PID.
- git stash is forbidden repo-wide (shared across worktrees).
- The V2EffectRegistry literal is FROZEN — new primitives via
  registry_<topic>.go init files, tests in new shape_<topic>_test.go files.
- Documents under `docs/archive/` are historical evidence, never current
  operating instructions.
