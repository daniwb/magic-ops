# Staged runner repair — September 8, 2026

Implemented after operator authorization to fix the identified runner defects
and record the remaining throughput work. This repairs preparation and the
bounded correction path; sustained card throughput has not yet been measured
with these changes.

## Changes

- Source excerpts now prioritize actual dispatch branches and declarations
  over comments and incidental references. Missing matches produce an honest
  source index. Excerpts disclose truncation. A NEED continuation can include
  up to three directly named Go types from the same package within its total
  source budget; this is not recursive dependency expansion. Context reads
  are restricted to repository source roots, independently of edit scope.
- Preparation checks reject required source references outside edit scope
  unless explicitly marked context-only. New capability tickets include
  explicitly referenced existing game/cards implementation files. Existing
  immutable tickets are not rewritten or granted extra authority at runtime.
- New capability tickets use their semantic identity hash in required test
  names. Preparation detects an explicitly demanded new test whose symbol
  already exists outside editable files. Ordinary gates selecting existing
  regression tests remain valid. Different capabilities sharing a human key
  keep their distinct semantics.
- Claude staged can make one focused correction after its first failing
  ticket gate. The correction receives the exact gate, preserved diagnostics
  and current candidate source. All ticket gates restart after application;
  no candidate is accepted with a remaining failed gate. Protocol repair and
  gate repair share a single correction allowance. The existing baseline's
  two patch calls plus one NEED permit at most three model calls for Claude
  staged; other profiles retain their previous continuation/repair limits.
- Receipts retain the prepared packet, requested context, original failed
  gates, correction response, final gates, failure category and model-call
  count. Missing counters in any call make the corresponding aggregate
  unavailable instead of reporting a misleading partial total. Provider
  definitions of cached versus input tokens have not been normalized here.
- Contradictory preparation produces `preparation_failed` before any model
  call. The controller treats it as terminal rather than an infrastructure
  retry. Its receipt asks for a corrected successor specification.

Implementation: `scripts/factory_ng_context.py`,
`scripts/factory-ng-run-engine-ticket.py`, `scripts/engine-pipeline-pack.py`,
and `scripts/factory-ng-produce-capability-dependency.py`.

## Verification

- `python3 scripts/test_factory_ng_staged.py`: 14 passed. Includes real
  isolated Git clones, strict patch application, a real Go compile failure
  followed by a passing named behavior test, a failing semantic correction
  that cannot export a candidate, complete gate reruns, zero-call preparation
  failures, and repair-budget checks with and without NEED.
- `python3 scripts/test_factory_ng_control.py`: 64 passed.
- `python3 scripts/test_factory_ng_reliability.py`: 19 passed.
- `python3 scripts/factory-ng-profile-validate.py --enabled-workers`: five
  profiles passed. Python compilation and scoped whitespace checks passed.
- Historical pinned-source replay: the original grant-keywords NEED now
  includes the dispatch at line 4797, rather than the early comment selected
  previously. See [the saved replay](staged-context-replay.md).

Provider responses in regression tests are deterministic fixtures. No paid
model trial was run. The canonical openmagic checkout remained clean. No
engine mutation, integration, push, live deployment, ticket rewrite or worker
restart was performed for this repair. New runner invocations load these
files; already-running processes retain their loaded implementation.

## Remaining

The ordered follow-up is in [IDEA_POOL](../../IDEA_POOL.md): correct old
contradictory specifications, run five distinct individual-card observations,
classify demonstrated Engine gaps, simplify one proven interface obstruction,
build incremental SQL statistics and dashboard pagination, then measure a full
quota week against 100 cards/day and investigate 400+. The Tidal Surge
zero-target premise requires a corrected semantic specification before trial.

These tests establish runner behavior. They do not establish a higher live
card acceptance rate, a 200k–500k cost per completed card, or that the engine
needs a wholesale rewrite.
