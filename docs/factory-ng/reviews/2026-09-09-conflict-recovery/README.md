# September 9 merge-conflict recovery

## Current result — all 15 recovered

**All 15 conflict lineages are now integrated and pushed through full gates.**
The five remaining lineages passed follow-up recovery and pushed at
`474e2ba6b06b7ae132afd3dcb8c9298dc507f7e5`. Their original named gates,
reparse/import, build, full Game, focused and six-shard production suites all
passed. No candidate was excluded. All five jobs are completed, their retry
counters are unchanged, and canonical source was verified clean at 19:49 UTC.
No live deployment occurred.

See [follow-up changes and evidence](follow-up/README.md) and
[final verified snapshot](follow-up/final-summary.json). The original
`final-summary.json` is preserved as the earlier recovery snapshot.

## Initial recovery (before the follow-up)

**10 of the 15 conflict lineages are integrated and pushed through all gates.**
The eight-patch merge wave landed at `fb557922f41d2d07a313d484dc64f551449ccf1e`;
counter damage and copy v2 landed at `482cd75c21cb47afe2f5ea79e0ca3a3e7ddc5ecc`.
Neither wave excluded a submitted candidate. No live deployment occurred.

**Five remained unresolved at that stage:**

| Lineage | Remaining failure |
| --- | --- |
| Target-player hand-size damage (`5b58aa258c`) | Existing Storm keyword regex consumes the card-name prefix; original conversion test retained. See `hand-size-parser-probe.md`. |
| Self no-target pump (`9e24f96767`) | Bounded repair emitted malformed FILE blocks; no accepted correction. |
| Exiled-this-way mana value (`a737105295`) | Bounded repair SEARCH text was absent from the pinned source. |
| Destroyed-this-way per-player count (`58304e2f98`) | Bounded repair SEARCH text was absent from the pinned source. |
| Sacrifice unless discard (`3e88a33648`) | Initial malformed patch; final candidate failed formatting. |

The four bounded semantic repairs keep their original gates, scope and
integration-repair history. None is counted as completed simply because its
old conflict was superseded. `final-summary.json` binds outcomes to the actual
integration receipts. The final health check confirmed canonical source clean
with no unfinished Git operation. Its old watchdog dead-PID warning was already
reconciled to a failed job; the watchdog poll predates the final integration.

The user authorized recovery of the 15 current Engine merge conflicts.
`audit-diff3.json` reproduces all 15 against clean immutable revision
`da54953454066b60c3c996d5a273da0e1bafdd0a` in a disposable clone.
Every conflict touches `backend/game/ability_effects.go`; one also touches
`gamestate.go`. Twelve candidates collide only on independent insertions.

## Reviewed resolutions

`prepare.py` conserves both sides of the reviewed empty-base insertion
conflicts. It checks the exact historical candidate side, retains all tests,
and restricts each resolved patch to the original candidate's changed files.
The attachment-filter signature change additionally needs the newly landed
Celestial Kirin caller to pass an empty attachment filter. A combined build
caught that incompatibility before integration.

The untargeted-all pump change preserves both `group_filter` and `all=true`
exceptions while retaining the no-target/no-discriminator no-op.

Thirteen resolutions are retained in `resolutions.json`. Before submission,
copy-triggering-referent and referent-target-hand-size had entered automatic
successor repair, so the manual selection excludes them. Further negative probes rejected destroyed-this-way counting and invalid
discard handling; both have bounded v2 repairs. Eight candidates remain in
`selected/resolutions.json` for one full-gate wave. Counter-based damage is
repaired separately in `counter/resolutions.json`, including a new actual
damage assertion under its original named test. It delegates to the ordinary
damage pipeline and consumes no additional model retry. A prepared patch is
not a successful integration.

The explicit `--reviewed-resolutions` integration option binds the original
accepted patch and TicketSpec hashes, reviewed patch hash and source ancestry.
It records the exact resolution in the integration receipt. This explicitly
reviewed mode composes first, then runs EVERY original semantic gate on the
final composition, followed by all production gates. Any semantic failure
rejects the whole wave. Normal automatic integration retains per-prefix
isolation checks. Reviewed operator runs wait for the existing scoped lock;
there is no overlapping canonical integration. Normal
controller integration never discovers or applies this override implicitly.
Original receipts, tickets, model accounting and retry counters are intact.

## Semantic defects separated from mechanical merge repair

- `9e24f96767`: the proposed implicit self-pump fallback treats missing targets
  as proof of self. It contradicts the untargeted-all candidate's negative
  test for the same input and risks pumping the source of a targeted effect.
  Its v2 requests an explicit self discriminator and preserved group/all and
  targeted behavior, under the original named gate.
- `a737105295`: the candidate records mana value before successful exile and
  only clears it when consumed. It can record a filtered-out target or leak
  an unconsumed value to an unrelated spell. Its v2 requires public-resolution
  tests, successful-exile accounting and resolution-local state.

The self-pump and exile-value v2 successors were admitted with Codex routing, original scope/gates and
the existing one Engine integration-repair allowance. This is admission, not
completion. The additional destroyed-count and discard v2 successors were also admitted
with the existing one-repair allowance. The automatic copy v2 ended on a
formatting gate, and hand-size v2 failed its conversion test. Their terminal
receipts remain; none is reported as recovered merely because it superseded
a merge-conflicted ancestor.

## Validation and outcomes

Three integration-override regressions (including one/two-candidate final-gate
ordering and fail-closed behavior) and 19 existing reliability regressions pass.
The original combined focused Game/Cards gates and full Game suite passed,
but `negative-probes.log` demonstrates why these original assertions alone
were insufficient: damage without damage marking, surviving indestructible
artifacts counted as destroyed, and invalid discard escaping both costs.
Those deliberately failing probes are preserved in `negative-probes.go.txt`.
The corrected counter helper passes its strengthened named test.
Two interrupted preliminary integration attempts are retained separately;
neither reached canonical fast-forward. Final integration results belong in
`wave-*-output.json` and `counter-copy-output.json`.
Final per-candidate results are taken from immutable integration receipts.
No live deployment is authorized or performed by this task.

## Confirmed first wave

All eight selected candidates passed and were pushed at
`fb557922f41d2d07a313d484dc64f551449ccf1e`, with no exclusions.
Receipt: `docs/factory-ng/runs/2026-09-09T071132Z-wave-e6994e69884f-integration.json`.
The recorded build took 145.8 seconds; the full six-shard suite took 205.4
seconds. All original composed ticket checks passed.

Copy v2 was subsequently recovered without a provider call: formatting alone
exposed an unrelated-trigger regression in the full Cards suite, so the
converter now preserves existing effect IDs outside `copy_spell`. All original
candidate gates pass after that correction. The immutable new operator receipt
retains the prior failed receipt and raw hashes without duplicating provider
usage. Counter and copy passed and pushed together; see `counter-copy-output.json`.
