# Test queue visualization and health check — 2026-09-14

The factory is active with manual compilation On. At the inspection, four saved
patches awaited focused verification and five accepted patches shared one full
integration run. That run advanced through corpus generation and Go build to the
final six-shard suite. No success was assumed while that suite was still running.
Five unresolved integration failures predate today's batching change.

Three recent integrations hit the old 720-second TicketSpec Go gate deadline:
08:44:53 (shared wave), 08:58:02 and 09:11:02 UTC (individual retries). Named game
tests passed near each deadline, but the command including cards had not finished.
Both ticket runners now allow 1,800 seconds for Go build/test/vet commands,
matching existing full-integration build allowances under the two-CPU limit.
Other ticket commands retain 720 seconds; all required gates and named-test
execution checks remain enforced. Timeout evidence now states the deadline.
Already-running processes keep the code they loaded; later runners use the fix.

The live dashboard adds **Patches waiting for tests & merge** with four clickable
stages: waiting/running focused checks and waiting/running the full gate. It shows
patch counts, distinct integration runs, drafting count, time in stage, individual
ticket details, compilation state and data freshness. Superseded jobs are excluded;
counts use the complete active inventory regardless of table pagination/search.
Batch verification members are classified as testing, not model drafting. Counts
are patches rather than promised card activations. Older failures appear separately.
The controller badge now says 'controller running' rather than asserting health.

Validation: 42 Python tests passed, including projection pagination independence,
verification metadata, Go timeout selection, pause/resume and reliability. JS
syntax and stage grouping checks passed. Browser checks verified actual API counts,
clickable stages and ticket details, paused/empty states and mobile layout. The
embedded dashboard was built with the managed Go wrapper and installed under the
dispatcher-admin lock. Compilation remained On; the controller and active game
integration were not restarted. See snapshot.json and desktop/mobile screenshots.
