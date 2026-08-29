# Refactor Inventory v0

`scripts/factory-ng-refactor-inventory.py` is a small, read-only Map/Engine
scan. Its intended background cadence is once nightly (for example 02:00),
after the ordinary Factory work has finished. It writes an index, ranked
evidence-backed proposals, report, and hashes. It never edits source, creates
tickets, or schedules worker work. Every proposal becomes a small ordinary
refactor ticket only after human review.

It is not part of the current Factory startup path, and it performs no
root-cause analysis, model attribution, contract change, or automatic action.
Those extensions live in the [Idea Pool](IDEA_POOL.md).
Case-label evidence is scoped to one concrete Go `switch`; identical labels in
different functions or switches are not presented as duplicate dispatch.

Verification on 2026-08-28 used the pinned `/opt/development/test/openmagic`
source. Two consecutive runs produced byte-identical index, proposal, report,
and manifest files while `git status --porcelain` for that source stayed
unchanged. The current output contains one review-required proposal for the
45-case `applyKeywordCost` switch; it is not a ticket, patch, or scheduled job.
