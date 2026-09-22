# Manual compilation/testing, continuous drafting — 2026-09-14

The user corrected the initial quiet-hours implementation: drafting should keep
running while compilation waits. They then explicitly replaced scheduling with
an On/Off dashboard switch. The previous 22:00–07:00 policy is removed.

## Result

`Compilation & testing` on `/dashboard` uses GET/POST
`/factory-ng/compilation`. It persists `compilation.enabled`, initially false.
The API validates booleans, atomically preserves the remaining policy, honors
`dispatcher-admin`, and rejects concurrent writes. There is no timer or daily
reset. Factory Start/Stop remains independent.

While off, producers and models prepare fixes. Both worker harnesses save a
hashed binary-safe diff, pinned ticket/source identity, original model identity,
and continuation/repair context as `factory.untested-proposal/v1`. They release
the disposable clone and worker lease. Controller state is
`awaiting_verification`; the dashboard labels it “Awaiting tests”. There is no
accepted observation receipt yet, and these proposals cannot enable cards.

When on, the controller prioritizes saved proposals for their original enabled,
compatible worker under normal quota rules. It restores the original patch,
runs all original gates and preserves the existing bounded correction allowance.
It does not regenerate a proposal just to resume verification. Only verified
observations proceed through the unchanged full integration gate. A test already
running finishes; the next worker gate checks the switch again and can save a
new checkpoint. A full integration already admitted finishes safely.

Resume dispatch does not consume another model attempt. Verification has its
own bounded infrastructure retries, preserves checkpoints across controller
restarts, and marks reconciled receipts so the next sync cannot replace a saved
proposal with fresh model work. Source/provider waits retain the proposal and
back off without consuming a verification retry. Existing bounded trial/repair
inventories recognize pending verification as active work.

All automatic work and managed Go invocations retain shared CPUs 12,19 at nice
10. Installed source-analysis helpers now live in `state/go-helpers`, keyed by
source content, and run directly instead of invoking `go run` while drafting.
Missing/changed helpers require compilation to be enabled before rebuilding.
The three legacy scan crons retain resource limits with `--exec`; their time
conditions were removed. The existing Magefield nightly maintenance job now
also skips when the switch is off; it never turns the switch on. Manual commands outside the factory are not governed
by the dashboard switch.

## Validation

- Full dispatcher Go test suite passed, including new API tests for Off→On→Off
  persistence, policy preservation, malformed input and lock contention.
- Seven proposal/controller tests exercise both real disposable Git harnesses:
  off saves without tests/acceptance, resume while still off preserves work,
  on restores and verifies without another proposal call, and a failing saved
  patch retains the original bounded gate-repair step. Integrity tampering is
  rejected; canonical fixture source remains untouched. Dispatch and interrupted
  resume preserve model/verification attempt accounting.
- Batching, controller, reliability, multi-miss, dashboard-index, knowledge,
  vocabulary, trial, repair-batch, recovery and capacity regressions passed.
  Three initially failing controller checks passed when rerun after the previous
  integration finished; its source-dependent producer tests read live ground
  truth. One stale knowledge-test parser fixture was updated to expose the
  existing map_atom tracing interface. Obsolete scheduling tests were removed.
- Browser inspection of the live dashboard showed the accessible switch Off.
  Real UI On/Off click/save/reload paths were exercised with browser-local fixture
  responses; the live backend stayed Off throughout. API persistence was tested
  independently against temporary policy files. Live GET and POST false also
  confirmed persisted manual mode. See dashboard.png.
- JavaScript syntax, Python compilation and whitespace checks passed. Only the
  dispatcher and tiny source-analysis helpers were built to install this feature;
  no game source edit, game build or live game deployment was performed.

## Activation

Policy/cron edits, dashboard binary replacement and controller/watchdog reloads
used dispatcher-admin. The policy has no work_schedule field and compilation is
off. The dashboard API returns {"enabled":false,"mode":"manual"}; controller
status shows production running with compilation.allowed=false. Already-accepted
patches remain awaiting integration. The earlier full integration finished and
the canonical checkout was verified clean before the switch installation.

Rollback binary: /tmp/dispatcher-v4-before-manual-compilation.
Prior crontab: /tmp/magic-crontab-before-manual-20260914.
The current operating instructions are in RUNBOOK.md and CURRENT.md.

Final live check: controller 2775102 was producing tickets with CPU affinity
[12,19] and nice 10 while the API remained Off. It dispatched
`ticket:map.plan-damage-cinderheart-giant-d7b092318b/v3` during daytime, confirming
that drafting is no longer clock-blocked. Canonical source was checked clean
under the integration lock. Proposal save/resume acceptance is covered by the
disposable-clone tests above; a live worker dispatch alone is not a verified card.
