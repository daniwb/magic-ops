# September 12 — exhausted frontier and registry extraction repair

The user requested a strategy review and authorized applying evidence-backed fixes while away.

## Findings

The controller was alive but had zero runnable tickets and one deferred Engine job. In the 144 watchdog samples inspected from September 11 07:00 UTC onward, 34 had zero runnable reserve and ten had no active work. The initial daily card gain was 135, with 12,967 auto cards. The last nine samples, 05:59–07:10, had no active work. Claude was paced until 18:00; Codex remained available. Producers repeatedly reported an exhausted supported plan. This was real supply starvation, alongside provider pacing, rather than a stopped controller.

A clean disposable clone at `93fd575218838ed2e10b070efdf3153388b0ed8b` supplied a complete census of 17,097 review cards in 103.56 seconds. There were 10,787 cards with exactly one parser miss and 4,185 with two. Parser misses are not necessarily separate printed paragraphs. Source JSON and exact text are retained in `census.json`.

The existing producer supported 20 explicit verbs and required exactly one miss. Every usable candidate in those families already had ticket history. Existing history was not reset. Additional supported runtime families provide 123 unaccounted single-miss candidates:

| Family | Candidates |
|---|---:|
| draw / p_draw | 55 |
| gain_life / lose_life | 33 |
| p_discard | 22 |
| mill | 13 |

The related plain `discard` category is also enabled, with zero current single-miss candidates.

A genuine extraction defect hid another 67 prevention candidates: the registry regex stopped at `})` inside the quoted Executor description of `prevent_damage_this_turn_scoped`, before reaching ShapeTest. The primitive was already registered. The producer now uses the existing Go syntax extractor, extended to return complete Executor/ShapeTest metadata. Comments, unused functions and incomplete metadata are excluded. No game primitive or frozen registry literal was changed.

After that repair and the additional families, 190 fresh one-miss cards and 17 two-miss cards with one shared supported family are candidates. These are not guaranteed enabled-card gains. Two-miss cards with different families, and cards with three or more misses, remain excluded.

## Activated changes

- Additional draw, life, discard and mill families use explicit canonical effect mappings and exact player, amount, variable-binding and choice requirements. Prevention tickets explicitly distinguish source from recipient filtering, combat from all damage and unlimited from next-N shields.
- A separate `build-plan-two-miss-pilot` producer follows ordinary single-miss production. It requires exactly two misses of one supported family and has a two-ticket admission limit, including blocked Map tickets waiting for Engine work. Existing production keys preserve prior history. Both occurrences must pass the unchanged whole-card pinned gate; removing one occurrence or replacing it with another miss fails.
- Producer scans use separate cursors for the one- and two-miss frontiers. Current source/text revalidation and all focused/full integration gates remain required. No provider, quota, retry or deployment policy was changed.
- Producer configuration uses a fresh immutable September 12 measurement. The coverage snapshot reads that same configured plan and exposes its revision/date. The page now describes measured candidates and historical ticket linkage, rather than calling historical completions current production. Hardcoded evidence-gap claims were removed from display. Broad `?/target` and `?/if` labels in the old August plan are currently aggregated as `verb_unmapped:?` by the parser; 3,419 one-miss cards are in that broad class, with 801 static-unmapped and 306 replacement-would cards. Those counts need semantic subdivision before production.

## Validation

89 Python tests passed, covering controller/producer scheduling, vocabulary handoffs, cache behavior, one/two-miss selection, rejection of mixed families, preservation of history, the pilot bound including blocked parents, full-card rejection of partial fixes, registry strings/comments/assignments, and coverage plan selection. Initial isolated test-root mismatches in three pre-existing fixtures were corrected in the validation copy; the full final suite passed from the real operations root.

Seven named existing runtime shape tests passed for draw, life gain/loss, discard, mill/self-mill and scoped prevention. Dispatcher Go tests/build passed. Node syntax and DOM-stub rendering checks passed, and live coverage HTML/data showed the measured source and historical labels. This was not a full browser screenshot test.

Dry runs with actual ticket history produced Arachnogenesis and Alpha Brawl TicketSpecs. The latter pins both damage-by occurrences and explicitly requires complete parsing. Dry-run tickets were not manually queued.

## Strategy

Keep complete-card yield as the primary metric. Prefer useful one-miss work across more supported families, with a small two-miss same-family lane as the next step. Do not equate two arbitrary misses with twice the effort: unrelated capabilities can leave a card blocked after either task. Large target/if/static/replacement buckets are the next discovery frontier; classify narrow recurring semantics, prove runtime behavior, then generate reusable Map or Engine contracts. Their raw counts alone do not justify feeding the entire bucket to workers.

The immediate change restores supply; sustained enabled-card throughput and failure rates must be measured after gates finish. Existing unresolved integration defects and historical failures remain visible.

## Live verification

The controller consumed the changed producer without a restart. Arachnogenesis
was automatically queued at 09:13:33 UTC, assigned to Codex at 09:13:47, accepted
at 09:15:43 and started full integration at 09:15:46. Subsequent prevention
cards were automatically queued; both Codex workers received new work.
Al-abara's Carpet correctly requested a separate capability and remains blocked
on that dependency, rather than being counted as fixed.

The dashboard binary was replaced under dispatcher-admin and exact PID 2912620
was signaled for its supervised restart; the backup is
`/tmp/frontier-dispatcher-v4.previous`. Live HTML and coverage data expose the
September 12 source/date. `activation.json` records per-ticket states. Canonical
openmagic was clean at that check, with the normal integrator active.

A fresh watchdog audit reports active/moving progress. It retains two prior
unresolved integration failures and the historical two-hour integration-gap
warning; no existing failure was hidden or replayed. New full integration is
still in progress, so this handoff does not claim a new enabled-card total.
The two-miss producer is enabled for the next producer sweep; its complete
TicketSpec was verified in the dry run.
