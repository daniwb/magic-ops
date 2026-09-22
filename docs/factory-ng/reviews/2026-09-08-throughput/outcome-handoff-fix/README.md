# Factory handoff and source-wait fixes — September 8, 2026

The five-card trial exposed two avoidable failures: a staged repair saw the
original parser header instead of its changed branch, and workers consumed
dispatch retries on a transient canonical `index.lock` before calling a model.

Implemented:

- Map packets execute the real card parser and record actual `map_atom`
  arguments, clause, kind and result. AST-based excerpts follow current verb
  locations; missing arguments also include matching raw-clause helpers.
  Siegfried's captured packet shows `put_counters` receiving `None`, plus the
  existing `_put_counters_per_count` helper. A test with fabricated arguments
  cannot demonstrate that this real handoff works.
- Compile/test corrections receive current changed hunks, before diagnostic
  locations or file headers. Original requirements and all gates stay intact.
- Dispatch waits when canonical source is unavailable. A race after dispatch
  produces a durable zero-model `source_unavailable` receipt; reconciliation
  refunds that dispatch once and backs off. Only a matching ticket receipt
  explicitly recording no model call can authorize the refund. Historical
  attempts are not reset without evidence.
- The trial producer can request its own bounded Map recovery through the
  existing repair compiler. It keeps the two-active-job reserve, two-repair
  limit, immutable ancestry, scope, tests and exact staged profile.

Validation: 127 tests passed: staged runner 24, Map context/source waits 4,
controller 65, reliability 19, recovery 8, trial 7. Logs are beside this file.
Runner tests use real isolated Git clones, strict patch application and gates;
provider answers are fixtures. Controller build-plan tests use the stable
isolated source at `/tmp/magic-ops-recovery-control-source` to avoid integration
races. The saved Siegfried packet is diagnostic evidence from that checkout,
not an accepted card implementation or a live-source snapshot.

Activation uses graceful SIGHUP under the dispatcher-admin lock; see
`activation.json` and `live-handoff.json`. Running children are preserved.
Worker configuration and the separate MiniMax adapter work were not changed.
No live game deployment.

Remaining: finish the five-card Maps and fresh whole-card runtime verification;
give Sigil's historical malformed-NEED failure an evidence-backed disposition;
correct old scope/test contracts; resolve the older integration failures; then
measure total tokens and time per fully verified card. The 200k–500k token
target remains unproven. New factory mechanics alone do not count as card
completion.
