# Codex strict patch repair — September 16

The factory was alive but had zero runnable tickets and 14 deferred protocol
failures. Claude's weekly quota was exhausted until 18:00 UTC. Codex quota was
available, but its shared profile had failed on every deferred ticket. Supported
producers found no fresh eligible candidates. Restarting alone could not help.

Reviewed Codex receipts: seven initial failures included unmatched SEARCH text,
three ambiguous SEARCH text, three malformed FILE blocks and two unrecognized
responses (counts overlap). Twelve final repair responses requested source with
NEED. The harness repeated the initial NEED offer while forbidding repair tools,
but never processed NEED at that stage. The remaining two repairs repeated bad
delimiters (`===` or `<<<END`). These failures happened before testing.

The shared Map/Engine runner now supplies bounded exact source excerpts from the
pinned clone when repairing rejected patches. Approximate anchors select evidence
only; strict exact matching still owns every edit. The final-call prompt explicitly
retires NEED, specifies the accepted delimiters, and permits Codex's already
registered source-read tools. Other profiles retain their tool restrictions.
Compile/test correction likewise retains Codex read access. The existing call and
repair bounds, checkout-mutation checks, ticket scope and all gates remain.
Repair packets are retained and hash-bound in observation receipts.

Validation: 5 source-evidence checks, 33 actual isolated-runner checks (including
real strict patch application and Go gates), 16 recovery tests, 4 strict-applier
checks, and 67 controller tests passed. Enabled profiles validated. See test logs.

Each of the 14 existing failures has an individually reviewed evidence file and
verified original raw-artifact hashes. Entries were appended to the existing finite
controller-owned review manifest, preserving its 116 entries and shared six-active
cap. Admission explicitly binds queued state, protocol failure, failed target
profile, attempts, receipt, start identity, ticket hash and review-evidence hash.
Exactly one extra attempt is allowed. No live job was manually edited, no attempt
or failed-profile history was reset, and no historical receipt was rewritten.

The corrected controller was requested to reload gracefully via SIGHUP under
`dispatcher-admin`. Fresh workers load the corrected runner. Live outcomes will be
recorded below; dispatch alone does not establish acceptance or integration.

## Activation and secondary findings

The supervisor restarted controller 2746515 at 15:57:22 UTC. Four reviewed
Codex leases dispatched at 15:57:46. Three encountered a transient canonical
index.lock before calling any model; the existing controller refunded those
leases and retained their source backoff. Source preflight now sets
GIT_OPTIONAL_LOCKS=0 for git status, preventing parallel read probes from taking
optional index-write locks. Real integration locks/unfinished operations still
block admission. All 21 reliability checks passed (146 checks total).

One Luna request returned the explicit provider error “Selected model is at
capacity.” This is preserved as infrastructure_failed_provider_capacity, not
misreported as a patch-format failure. Other Luna requests did proceed. No
worker model or usage ceiling has been changed.

At 16:01:05 UTC the counter-target-creature-spell recovery had applied its patch
and saved a hashed proposal for focused verification. This is not acceptance
or integration. Live status: `python3 docs/factory-ng/reviews/2026-09-16-codex-repair/status.py`.

At 16:03:28 UTC the counter-spell ticket passed focused verification and awaited
full integration. Three other recovery calls failed due to Luna provider capacity
(two before work and one after read-only tool calls; the latter deliberately
retains its generic transport failure plus raw partial-work evidence). After an
optional model-preference question went unanswered, new Codex dispatches were
configured to use gpt-5.6-terra as a temporary fallback under dispatcher-admin.
The original worker configuration is preserved in workers-before-fallback.json.
Existing runs retain their original model. Profiles and weekly ceilings were not
changed, and enabled-profile validation passed.

## Completed gate and final repair validation

Counter-target-creature-spell passed focused verification, full production
integration and push; controller reconciliation confirmed completed by
16:09:24 UTC. Receipt:
`../../runs/2026-09-16T160539Z-engine-auto-counter-target-creature-spell-78cf9b4a60-v2-1789574739967553127-integration.json`.

A live Luna correction still emitted <<<REPLACE despite the format reminder.
The strict parser now recognizes standalone <<<REPLACE or === as replacement
separators, and <<<END as an end marker. It still requires exact, unique SEARCH
text, rejects duplicate/nested markers, stages all changes before writing, and
retains all scope and test gates. No source/replacement text is guessed or
rewritten. Canonical output markers remain the model instruction. Four pinned
archived response replays are in delimiter-replays.json: one applies, and three
correctly stop on unmatched or ambiguous source after parsing. These are patch
application checks, not semantic acceptance.

Final validation: 150 checks across source context (5), staged runner (33),
finite recovery (17), strict application (6), controller (68), and reliability
(21). The second controller run hit one existing test's dependency on canonical
source while live integration was changing it. Its clean-source rerun passed;
all other controller tests passed. Original failed log and isolated rerun are
retained. No test expectation was weakened.

Five capacity-only failures have a second, individually bound review after the
concrete model fallback. Admission binds the prior review hash and new failure,
archives the prior review, preserves total attempts, and permits exactly one
extra attempt only on Terra. No semantic failure is admitted by these entries.
The shared concurrency cap is unchanged. The manifest was published and the
controller requested to reload under dispatcher-admin.

## Saved-proposal continuation correction

Live remote verification exposed another recovery bug: pending review overrides
ended after drafting, so original failed-profile history excluded the original
worker from individual verification/repair of its newly saved proposal. The
override now remains available only for that exact reviewed attempt in
awaiting_verification with a saved proposal and its original dispatch profile.
It never permits a new queued drafting attempt. Attempts and failed-profile
history stay intact. The runner already pins a resumed proposal's original model,
so changing configured models does not change in-flight proposal identity.

Nineteen finite-recovery tests now pass, including actual controller dispatch
of the saved proposal and rejection of a fresh queued retry. Nine verification
checks also pass. Total distinct final checks: 161. Graceful reload requested
under dispatcher-admin; active gates are retained.

## Final live checkpoint — 16:16 UTC

Fresh watchdog: active=true, moving=true. Factory inventory: four working jobs,
one saved proposal awaiting verification and one accepted patch awaiting
integration. The original 14-ticket cohort includes one fully gated/pushed
completion; remaining outcomes are explicit in live-status.json, including
capacity reviews pending admission and failures/parks needing their normal
repair paths. Two unresolved integration failures remain visible. The former
no-runnable/no-progress alert is gone. Canonical openmagic was clean with no
unowned integration changes. No live deployment occurred.
