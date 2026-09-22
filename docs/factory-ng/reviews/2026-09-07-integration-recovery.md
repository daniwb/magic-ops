# Failed integration recovery — 2026-09-07

## Scope and disposition

The operator requested repair of the failed integrations. The 20 unresolved
Map candidate conflicts observed at 12:25 UTC now each have an immutable v2
successor, pinned to current source and retaining their original gates and
allowed paths. This is recovery work in progress, not 20 completed cards.
The original observations and failed integration receipts were preserved.

At 13:00 UTC: one Map successor awaits integration (Skysovereign), two are
blocked on genuine Engine behavior (Skull Collector and Archmage of Echoes),
one failed its semantic gate (Burning Sun's Avatar), and 16 remain queued.
Qwen is executing the automatically produced Skull Collector Engine child.
Claude remains quota-paced. The separate eight-candidate Engine integration
wave is still running; no live backend deployment was performed.

The previously queried `engine.auto-conditional-pump-on-creature-type-87200f1a92/v3`
has completed and pushed in commit `d9b2ccdfb4b07614fadc714dd28ee9e71c8a05e5`.
Its integration evidence is
`../runs/2026-09-07T121231Z-wave-6cf688c844f5-integration.json`.

## Recovery defects repaired

- Integration Map repair no longer depends on the current discovery frontier.
  Pinned cards that became auto or moved to a different miss shape still get a
  fresh, bounded repair rather than disappearing from production.
- Full ordinary runnable queues no longer starve integration repairs or their
  Engine dependencies. The controller reserves two recovery obligations per
  lane and prioritizes dependency work; it reuses existing Engine children.
- Pinned measurements validate exact Oracle text for review and auto cards.
  Map acceptance checks complete parsing, not merely disappearance of the old
  miss category. Discovery itself remains review-only.
- Recovery worker gate failures can receive the remaining bounded successor,
  with the actual failed contract included. Generic worker failures are not
  reopened and integration repair generations remain capped at two.
- Dependency resume retains changed miss categories. For integration recovery,
  an already eligible card still requires Map verification after its Engine
  lands; parser eligibility cannot silently close a known semantic defect.

## Semantic findings and evidence

Skysovereign already has the intended parser mapping. Its isolated recovery
adds meaningful regression coverage for flying, ETB-or-attacks damage 3 to an
opponent-controlled creature/planeswalker, and crew 3. All four original
TicketSpec gates passed. This operator-produced candidate does not claim a
model invocation and still requires ordinary full integration:
`../runs/2026-09-07T124043Z-map-plan-damage-skysovereign-consul-flagship-3a6f42a950-v2-operator-recovery.json`.

Skull Collector's Qwen candidate passed parser tests but used a target with
`black_creature`, not an untargeted own-controller choice. Runtime
`matchesPermanentFilter` has no such bucket, and an actual black creature
failed an isolated Go probe. The empty effect value also cannot enter
`executeBounceFiltered`. An append-only operator review blocks that candidate:
`../runs/2026-09-07T125046Z-map-plan-bounce-skull-collector-4adbf44de6-v2-operator-runtime-review.json`.
Its exact-Oracle-validated child is
`engine.auto-return-black-creature-you-control-choice-478962fbe2/v1`.

Archmage's candidate only added tests blessing `copy it` as
`target.filter=artifact_spell`. That is neither the required Faerie/Wizard
permanent-spell behavior nor an executable targeting constant. The copy
executor needs a bound stack spell identity; its documented explicit-target
path does not establish the triggering spell binding. The accepted worker
receipt is retained, but an append-only runtime review blocks landing:
`../runs/2026-09-07T125901Z-map-plan-copy-archmage-of-echoes-49f5309ea8-v2-operator-runtime-review.json`.
The validated demand is `copy_triggering_permanent_spell`.

Burning Sun's Avatar correctly failed its positive test for the optional
second creature target. Its current eligible parser result is not evidence
that both damage clauses are implemented. Preserve that failing assertion;
do not weaken it to accept the current output. Evidence:
`../runs/2026-09-07T125000Z-map-plan-damage-burning-sun-s-avatar-79640c0681-v2-qwen.json`.

The initial 20-card audit and isolated verification workspaces are retained
under `/tmp/factory-ng-map-recovery-9PXLbR/`; none is the canonical checkout.
All durable ticket/receipt evidence lives in the normal Factory directories.

## Verification and remaining limits

19 reliability tests, 64 existing control tests, and two daily-report tests
pass. These include full-card pinned measurement, frontier-independent
repair, bounded post-repair gate failure, recovery dependency priority, and
post-dependency verification of already-auto cards. `git diff --check` passes.
The health check reports enabled profile validation passing, knowledge service
healthy, and +11 enabled cards over 24 hours. Canonical Git was clean at the
final check; integration continues under its scoped lock.

This is not a completed unattended soak. Passing parser tests can still bless
wrong runtime semantics, as the two blocked candidates demonstrate. Remaining
repairs must pass their semantic contracts and the full integration gates;
bounded terminal failures remain visible rather than being reported complete.
