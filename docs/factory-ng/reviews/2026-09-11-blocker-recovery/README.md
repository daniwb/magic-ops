# September 11 blocker recovery

User request: fix the diagnosed blockers and search for more. Live deployment remains disabled.

Factory changes:

- Engine acceptance checks newly added public effect dispatch cases against real Go registry declarations. Comments and Python `REGISTERED` overrides cannot satisfy this check. A failed check enters the existing bounded correction path.
- Pinned Map measurements inspect the emitted effect vocabulary against Go declarations before corpus import/build. This also isolates old accepted invalid Map patches during composition.
- Dependency messages follow Engine successors and distinguish admission, active work, completed prerequisites, and inactive failures.
- Runnable inventory excludes failed profiles, matching dispatch. Exact-profile tickets with every profile exhausted become explicit failures without resetting attempts. Sigil's verification exposed this reserve-accounting defect.
- Codex-2 uses the already active primary worker's 70% weekly ceiling; both share the same account usage. A live Codex-2 dispatch was observed after activation.

Control tests: 139 pass (65 controller, 31 staged, 19 reliability, 10 producer, 8 recovery, 6 vocabulary/dependency). Original runtime policy and production gates remain required. Controller reloads use SIGHUP under dispatcher-admin and leave active isolated work running.

The isolated recovery clone is recorded in `clone.txt`. `originals.json` binds all original receipts and TicketSpecs; `selected-originals.json` selects nine cards while Selfcraft's obsolete negative assertion remains pending user input. The recovery restores seven older exhausted Map integrations plus Dong Zhou and Crown of Empires. It preserves every selected original test assertion and semantic gate, resolves parser conflicts without dropping newer mappings, and adds nine missing `regEffect` entries. Existing executor tests and new public-path shape tests remain required.

Additional defects found:

- Some Map attempts fabricated Python-only registry entries; recovery removes those shortcuts.
- The parser mirror omitted real direct assignments made by existing registry init files; recovery recognizes those declarations.
- Trigger `subject.whose` was dropped during Go conversion. Recovery preserves your/opponent/each ownership for upkeep, end-step and beginning-of-combat triggers. A Skullcage shape test exercises the public event/stack path and rejects firing on the controller's upkeep.
- Selfcraft's historical negative test requires a two-draw compound to remain unparseable. `selfcraft-baseline.json` proves unmodified current main already parses the correct two-effect sequence. `selfcraft-proposed-test.py` preserves the positive card test and would require exactly two draws plus rejection by the one-draw compound helper. The user has been asked explicitly about this correction; it is excluded from the independent batch.

Completion: all 21 candidate gates passed. The recovery applied cleanly to
newer main and passed every composed semantic gate, reparse/import, backend
build, full Game, focused card checks, and the complete six-shard production
suite. No candidate was excluded. It pushed at 22:44 UTC as
`48df17966616e95744efb87722a62b0fa8d50040`.

Integration receipt:
[`2026-09-11T222818Z-map-operator-registry-recovery-sep11-v1-1789165698016319588-integration.json`](../../runs/2026-09-11T222818Z-map-operator-registry-recovery-sep11-v1-1789165698016319588-integration.json).
`completion-evidence.json` records the gates, source/remote match, clean
checkout, cards and job histories. `card-status-changes.json` proves ten
review-to-auto transitions: the nine targets plus Glimpse the Sun God. The
canonical auto count rose from 12,946 to 12,956. No live deployment.

All nine current lineages reconciled to completed. Crown v3 and Dong Zhou v3
remain superseded historical failures. Dong Zhou v4 was created after the
initial snapshot and parked while this recovery waited; its identical
semantic gates were already green on the exact pushed revision. A fresh
read-only check and immutable observation in `dong-closure-receipt.txt`
closed that current contract without another worker or integration run.
All snapshotted attempt counters are unchanged; Dong Zhou v4 retains its
single worker attempt. No retry budgets or original receipts were rewritten.

Remaining: Selfcraft's prepared test correction still awaits the user's
answer. Serial integration compilation is a separate measured throughput
limit: the preceding successful eight-candidate batch spent 43.1 minutes in
composed TicketSpec checks, out of roughly 54 minutes total gate time.
`integration-bottleneck.json` binds those timings to its receipt. Its
per-prefix and final-composition gates were retained unchanged. The recovery
itself waited behind that batch under the process-held integration lock.

The final watchdog refresh at 22:47 UTC reports movement, a runnable reserve
of eight against a target of eight, and one unresolved integration failure
(down from eight). Another automatic eight-candidate wave is integrating.
The canonical checkout remains clean. See `final-watchdog.json`.
