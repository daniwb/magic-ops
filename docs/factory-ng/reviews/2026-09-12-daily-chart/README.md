# Daily activation chart and evidence-backed explanations — September 12

The user requested the preceding 14-day activation figures as a live dashboard
chart, then asked for reasons below 100 cards/day and for unusually high days.

The dashboard now shows 14 completed UTC days plus a distinct partial today,
with a 100-card target line, completed-day total/average and today's progress.
Days below target are amber; today is blue/dashed and excluded from the average.
Selecting/focusing a bar shows the day's explanation and supporting observations.
A collapsible table exposes every daily explanation. High days start at 150.
Negative values extend below zero, and missing baselines remain unknown.
Mobile displays retain readable labels with horizontal scrolling to recent days.

A background snapshot reads immutable first-parent Git history and card blobs,
so working-tree edits cannot change the chart. Counts are cached by blob ID and
import contributions by commit SHA. Completed-day boundaries use UTC committer
timestamps. This measures net status-auto growth, not deployments or independent
semantic re-verification. The 14 completed totals reproduce the prior report:
1,504 cards and 107.43/day. All daily import contributions matched those totals.

Explanations combine measured import contributions, producer responses, watchdog
samples and dated operator notes in `measurements/activation-day-notes.json`.
Notes distinguish documented incidents from unquantified contributors. High-day
explanations identify large imports or cumulative waves. A lack of verified cause
is explicit; producer-error counts and idle samples do not become invented lost
hours or a count of cards lost. Today is not marked as having failed its goal.
No throughput, retry, quota, integration or deployment policy was changed.

The dashboard starts one refresh subprocess every five minutes, with a five-minute
timeout and a process-held file lock. HTTP only serves the small atomic result at
`/factory-ng/daily-activations`; a failed refresh preserves the dated prior file,
and the UI reports delayed refreshes after 12 minutes. A warm refresh measured
1.35 seconds before the final metadata-exclusion adjustment. The initial cold
history backfill takes longer and is not run on an HTTP request.

Validation: seven Python tests cover midnight/rolling boundaries, negative and
missing data, immutable source/cache behavior, goal/high/partial-day reasons,
import attribution excluding metadata, and distinguishing fresh exhaustion from
exhausted repair lanes. Dispatcher Go tests and build passed. JavaScript syntax
and rendering/selection/error/escaping checks passed. Real Chromium desktop and
mobile screenshots were inspected; these are saved here. No new external chart
library was added.

Activated under dispatcher-admin, signaling exact old dashboard PID 3633609.
Successor PID 3849606 served the chart and explanations. Its background refresh
published a new snapshot at 11:40:26 UTC, showing +68 for partial September 12.
The snapshot endpoint returned 16,971 bytes in 0.003 seconds in one measurement.
Backup binary: `/tmp/daily-chart-dispatcher-v4.previous`. The controller and game
service were not restarted, and no live game deployment was performed.
