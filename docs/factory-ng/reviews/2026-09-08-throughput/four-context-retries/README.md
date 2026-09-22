# Four context retries and dashboard count correction

The user authorized retrying Rakdos Roustabout, Machine Man, Model X-51,
Barge In and Thorntooth Witch. `manifest.json` pins their original tickets.
All four compiled into fresh context-repair successors and passed preparation
checks against isolated revision `54609c76ee6064d1b7081e26461618744c3e926a`;
see `preflight.json`. Preview files are not live ticket submissions.

The registered `context-retry-batch` producer emits successors through the
existing hash-verified recovery compiler. At most two selected lineages may
be queued, working, awaiting integration or integrating. The compiler and
controller admission both enforce this, including candidates emitted through
another producer. Closed or replaced versions do not consume a slot. Existing
five-card trial capacity is also respected; a full trial does not prevent
the other selected cards from advancing.

Selected successors use Claude staged workers. Their original scope, tests,
routing contract, previous costs and existing repair limits are retained.
Rakdos remains in its original exact-profile five-card trial. The other
ordinary staged tickets retain the existing bounded evidence-helper policy.
Worker configuration, including MiniMax, was not changed. Activation and live
admissions are recorded alongside this report. No live game deployment.

Dashboard audit: the API and SQLite index both reported 174 problems. The
SQL rollout had changed the display to include unresolved failures of all
ages; it did not create these old worker and integration failures. However,
43 superseded ticket versions were incorrectly still counted as current.
The projection now excludes those versions from the problem count and
attention list while retaining them in historical job and receipt views.
It refreshes the classification even if the underlying jobs file is unchanged.

The corrected live snapshot showed 131 unresolved ticket failures: 90 worker/
infrastructure failures and 41 integration failures. These counts can move as
the factory runs. `dashboard-count-audit.json` retains the exact before/after
breakdown. Background refresh applied the fix without rebuilding the dashboard
host or modifying authoritative job/receipt history.

Validation: 111 tests passed: controller 65, reliability 19, context 10,
five-card trial 7, dashboard index 7, replay batch 3. Tests cover bounded
admission, supersession, integration occupying a slot, staged worker selection,
and old failures disappearing from current counts while remaining in history.
