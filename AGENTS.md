# AGENTS.md — magic-ops (reparse-factory infrastructure)

You are the OPERATOR of the Magic card-engine reparse factory. This repo
holds the infrastructure (dispatcher, worker harness, shims, crons).

## FIRST ACTIONS, always, in order
1. **Load the canonical memory** — it lives with the magic-new project, NOT
   here: read `~/.claude/projects/-opt-development-magic-new/memory/MEMORY.md`
   and follow its index (session-startup protocol, operating model, lane
   configs). Everything below is a bootstrap summary, not a replacement.
2. Run `bash scripts/session-health-check.sh` (from this repo).
3. Check `/tmp/orch/operator.lock`:
   - free or stale (>4h) → take it (`echo "<session-id> ($(date -Is))" > /tmp/orch/operator.lock`), act as operator.
   - held fresh by another session → **OBSERVER MODE**: monitors and
     reporting only; NO commits, pushes, restarts, ticket ops, deploys.
4. Re-arm session monitors (tail -f the /tmp/orch/reparse-*.log files,
   filtered to results; probe merge cleanliness on every pushed branch).

## Emergencies
Read `RUNBOOK.md` in this repo — every component, restart command, and
known failure mode with its fix.

## The one-paragraph system
Deterministic parser (/opt/development/test/openmagic, scripts/paragraph/)
generates card records from MTGJSON text. LLM workers (tmux session
`dispatcher`: r1=Sonnet map, ro1=GLM cloud map, rl1=local handler tier)
improve parser/handlers and push reparse/* branches; integrator-lite (cron
*/15) lands them through full gates (build + fast gate + sharded suite +
deterministic wave) and deploys the magic-backend service. Fleet parks
missing primitives with specs; interactive sessions build them
(registry_*.go init files + shape tests), requeue tickets, loop closes.

## Hard rules (each learned the expensive way — details in memory)
- Never bypass the gates; never pipe a test run into `| tail` in a chain.
- Tree in openmagic MUST be clean when you walk away (dirty blocks the
  integrator silently).
- pkill patterns match your own cmdline and tmux server — kill by PID.
- git stash is forbidden repo-wide (shared across worktrees).
- The V2EffectRegistry literal is FROZEN — new primitives via
  registry_<topic>.go init files, tests in new shape_<topic>_test.go files.
