# Needs attention recovery — 2026-09-15

User requested checking and fixing every Needs attention ticket, with an active goal.
The complete initial dashboard inventory is [baseline.json](baseline.json): **121 tickets**,
five failed integrations and 116 worker failures. No TicketSpec literally contained
“needs attention”; the dashboard derives the label from unresolved job outcomes.

## Completed integrations

All five original integration tickets passed the composed original semantic selectors
and full production gate, and pushed commit
`5a16c070bd7f94b358f74900cccaeea9d5c3a392`. Controller reconciliation confirms all five
completed. No deployment. Receipt:
`../../runs/2026-09-15T190555Z-wave-901fb39072ba-1789499155059339605-integration.json`.

- Each-player discard hand: preserve newer target-player conversion alongside exact
  hand-only spell execution and its original unequal-hand-size end-to-end test.
- End-of-combat counter removal: retain the current event-card-aware executor, add
  the accepted explicit-target guards and original timing/amount regression.
- Butcher's Glee: combine independent enchanted-creature and spell-referent mappings.
- Assert Perfection: merge accepted referent-power/optional-target mapping with newer
  damage, modal and independent-target support.
- Selfcraft Mechan: the missing primitive was already registered on current main.
  Restore its whole-card mapping. The old negative test forbade a now-supported
  two-card draw sequence; replace it with exact general-sequence output plus a
  negative assertion that the one-card-only combined helper must reject it.
  All original gate commands remain, with stronger explicit draw-count coverage.

Reviewed patches bind original candidate hashes, TicketSpec hashes and current
canonical ancestry in [merge-resolutions.json](merge-resolutions.json). The canonical
checkout was never edited directly. Five patches were composed and gated together.

## Worker recovery in progress

Every worker failure has retained evidence and an individual review entry in
[worker-recovery.json](worker-recovery.json). Causes: 23 provider-capacity rejections,
23 historical dirty-source preflight exits, 11 unsupported-profile preflight exits,
three clone failures, one missing hashlib import, three provider-quota failures,
27 missing-source/context failures and 25 empty/truncated/malformed responses.

The finite controller-owned recovery admits at most six active tickets and respects
the queue cap. It binds ticket and failure evidence hashes plus original attempts,
receipt and start identity. Each reviewed ticket gets exactly one additional attempt
under its current compatible staged/Codex profile, without resetting attempts or
clearing failed-profile history. No semantic/integration failures are reopened by
this mechanism. Current scope, named gates, usage policy, focused verification and
full integration remain mandatory. Admission is not completion.

Codex's explicit capacity error now has its own provider-capacity gate/outcome with
normal bounded backoff. The dashboard prioritizes provider failures over the downstream
“no edit blocks” symptom. Original immutable receipts remain unchanged.

Activation: manifest published under dispatcher-admin; controller 478136 gracefully
exited at 19:11:57 UTC and its existing supervisor restarts it. Existing workers remain.

Validation: 110 control/receipt/dashboard/integration tests, 51 context/priority tests,
and seven final finite-recovery checks passed. Earlier mixed-version test execution
was rerun after edits settled. Eight parser checks and both targeted Engine checks
passed in the isolated clone; the full integration receipt is the landing authority.

Read-only progress (follows superseding tickets):

```sh
python3 docs/factory-ng/reviews/2026-09-15-needs-attention/status.py
```

The goal remains active until all baseline tickets are resolved or concrete external
blockers are established. Historical failures must not be hidden to make the count zero.

## Follow-up: queue admission and staged Claude

Recovery admission now runs at dispatch, counts runnable inventory rather than
all deferred queued jobs, and still permits at most six active reviewed entries.
The controller restarted as PID 757656 after the 19:23 UTC graceful reload.
The expanded admission suite had one transient canonical-source conflict-producer
failure during integration; its isolated rerun and the focused recovery suites
passed (20 checks in `admission-focused-tests.log`).

Windswift Slice's reviewed attempt returned NEED, then hit Claude's ten-turn
limit without a patch. The staged adapter previously denied mutation tools but
left read tools available despite the profile's empty allowed-tools list. It now
passes `--tools "" --strict-mcp-config --mcp-config '{"mcpServers":{}}'`.
`staged-tools-tests.log` records 20 passing recovery, packet and investigation
checks. A finite operator Engine correction is being prepared in
`/tmp/factory-ng-attention-excess`; it is not yet accepted or integrated.

Retromancer subsequently passed normal full integration:
`docs/factory-ng/runs/2026-09-15T192441Z-wave-513a5c618bc7-1789500281789761910-integration.json`.
At that checkpoint six of the original 121 tickets were completed. The two new
capability-blocked Map outcomes remain unresolved dependencies. Parser eligibility
in `current-corpus-audit.json` is discovery evidence, not runtime completion proof.

## Follow-up: rejected deferred proposals

Incremental Blight's reviewed attempt changed `effect_sequence.go` outside its
immutable ticket scope. The deferred proposal saver correctly rejected the
patch, but its exception escaped from the runner's exception handler, so no new
observation receipt was emitted. `incremental-blight/review.json` and
`rejected.patch` retain the unaccepted candidate and review gaps. The Engine
runner now emits a terminal failed-gate receipt for scope/empty-patch rejection,
or an infrastructure receipt for a save error. `proposal-receipt-tests.log`
records 18 passing checks, including a complete deferred out-of-scope run.

The three existing named tests found by `test-presence-audit.json` cover other
capability instances with the same test name (different counter, threshold, or
zone semantics). Their presence cannot discharge these original obligations;
none was marked completed from that audit.

A review wording correction: some old capacity-terminated raw logs include tool
work before the rejection, including Incremental Blight's earlier attempt.
Capacity manifest entries now say no accepted proposal resulted, rather than
claiming no model work occurred. Their retained evidence and attempt counts are
unchanged. The new adapter deliberately classifies only error-only transport
rejections as `provider-capacity`; it does not discard partial-work evidence.

## Current operator candidates

- `/tmp/factory-ng-attention-excess`: Windswift Slice's Engine correction. The
  new registered damage instruction records actual post-prevention excess in
  sequence-local state. Token creation consumes that value without retaining it
  in the card definition. Focused Game/Cards checks passed; final candidate gates
  are recorded under `excess/` when complete.
- `/tmp/factory-ng-attention-incremental`: Incremental Blight's Engine correction.
  Explicit `sequence_target_index` metadata routes independently selected counter
  atoms. Illegal targets retain empty slots at resolution so later amounts stay
  with their chosen creatures. Unindexed legacy sequences retain their routing.
  The operator ticket explicitly adds the missing sequence file and a shape test.
  Gates are running under `incremental-blight/`; this candidate is not accepted.

These candidates use original semantic selectors and complete Game/Cards gates.
No original TicketSpec, historical receipt, retry counter, or frozen registry
literal is rewritten. Both remain subject to normal full production integration.

Greater Werewolf is now being corrected in `/tmp/factory-ng-attention-werewolf`.
Its retained candidate was semantically unsafe despite stopping first on
formatting: it subscribed to every event, used mirrored combat flags, and did
not make the requested counter alter toughness. The finite operator correction
uses the existing end-combat trigger and canonical CombatState relationships,
with a bounded `counters.go` prerequisite for -0/-2. Gate evidence lives under
`greater-werewolf/`; no acceptance is claimed before those gates finish.

Incremental Blight's new missing-target regression exposed an executor error
that aborted later legal atoms. The indexed sequence now skips an invalid slot
before execution. Failed setup and illegal-slot runs remain in
`initial-gates.json` and `illegal-target-gates.json`; the complete gate list is
being rerun on the final correction.

## Follow-up: reviewed dependency priority and completed semantic corrections

Incremental Blight passed all candidate gates and normal full integration, pushed
`5185317eb409753dbe382727f0973b5925c5edb3`; receipt
`../../runs/2026-09-15T202125Z-engine-operator-independent-counters-recovery-sep15-v1-1789503685555875234-integration.json`.
Greater Werewolf likewise pushed `aff3bfe89bd7a9577ae9455b2f24c7e6db45710f`; receipt
`../../runs/2026-09-15T202800Z-engine-operator-combat-counters-recovery-sep15-v1-1789504080846256812-integration.json`.
Original parent jobs reconcile from these receipts. Both isolated candidates are committed and clean.

Current blocked reviewed Map receipts are scanned before historical capability demand.
Their emitted Engine dependencies and resumed Map tickets carry the original review root,
count toward the same six-active cohort limit, and dispatch after verification but before
further reviewed attempts. Ordinary producer admission and dependency retry limits remain.
Controller PID 757656 was gracefully reloaded; supervisor started PID 836853 with the
new cap enforcement before its first new producer scan. Worker processes were untouched.
Validation: `dependency-tests.log`, 56 passing recovery, priority, producer performance,
supply and context tests. Tests cover current receipt selection, root propagation,
six-active admission, ordinary traffic, and the actual producer emission path.

Three original named selectors collide with tests for older distinct capabilities.
`legacy-shapes/` records one indivisible operator candidate retaining all three original
contracts and every distinct original gate. It preserves old test assertions and adds
new shape coverage; completion requires all candidate and normal integration gates.

Dependency follow-up: admission reserves one slot while any reviewed lineage is blocked,
so new reviewed retries cannot consume every opening before the producer runs.
PID 836853 was gracefully reloaded to activate this reservation. Regression verifies
five active jobs plus a blocked review admit no further retry, while four active jobs
still permit one. Deep Spawn's new gate-failed receipt is under concrete operator
correction in `mill-unless/`; the rejected response is retained there. Its compile
errors hid two semantic defects: compulsory milling and an ETB fixture instead of
an own-upkeep choice. It is not yet accepted or integrated.

The producer's conservative lane-full heuristic no longer diverts a reviewed
blocked receipt behind unrelated Map resumes; the controller still enforces exact
lane capacity and the shared six-active cap. Regression exercises that saturated
heuristic with the real producer emission path. At 20:46:17 UTC it admitted
`ticket:engine.auto-grant-keywords-until-eot-conditional-on-target-c-97e6661211/v1`
for Revelation of Power, with the retained review root (see
`dependency-live-evidence.json`). Controller PID 854778 owns reconciliation.

Meteor Blast's reviewed attempt failed the strict patch format twice. Inspection
also found its proposed converter-only change could not enforce the original
paid-X cardinality: CastXSpell never validated the target list. The finite operator
candidate in `meteor-blast/` adds explicit exact-X metadata and uses the shared
prepayment validator, preserving legacy X spells without this metadata. Its named
public-cast tests exercise payment, X=0/1/2, illegal/duplicate targets, one target
leaving before resolution, and dynamic-damage negatives. Gates are still running.

Deep Spawn passed all candidate and normal full production gates and pushed
`d3271e5c644d3b38f384b013daf5237005c8c378` (see `mill-unless/README.md`).
All eight candidate gates passed for the combined three legacy test-name collisions;
`legacy-shapes/` is now accepted and entering normal full integration.
`sigil-proof/` adds the missing full-card functional proof from fresh corpus reparse,
without replacing its real abilities. This is an operator test correction; the
failed exact-profile trial receipt remains historical evidence and is not recast
as a successful staged-model trial.

## Checkpoint 2026-09-15T21:09:47.530061+00:00

21 of 121 original tickets completed; 35 reviewed attempts admitted.
The goal remains active; `progress.json` preserves this snapshot. New terminal
receipts are collected in `new-terminal-evidence.json`, with parked follow-up analysis
in `parked-followup-review.json`. The finite manifest remains active for originals
that have not taken their one reviewed attempt.

Meteor Blast passed normal full integration and pushed
`62f895ca4499af76b0bef13a486ba8c9eefaf4ae`. All accepted operator clones through
Meteor Blast are committed and clean.

Outstanding local candidate: `/tmp/factory-ng-attention-sigil`, ticket/evidence in
`sigil-proof/`. Check `sigil-proof/check.log` and `gates.json`; current final check
exec session is 21801. The scope now includes handler-binding retirement and generic
post-prevention combat notification repair, plus a temporary actual-combat collector
that excludes noncombat damage caused by observers from the group total. The exact
full-card test covers normal phase execution and the direct public combat resolver.
Only if every candidate gate passes, run `accept-operator.py sigil-proof`, then
`integrate-operator.py sigil-proof` through the normal full integration gate.
Do not count it complete or suppress its failed exact-profile trial evidence.

Next unresolved operator work includes Structural Collapse, Ulalek, Subterfuge and
Artificer's Dragon. Subterfuge's retained proposal is
`../../candidates/proposal-8d55a666ee434412a57278ad92282b45.json` (the `patch` field
contains literal diff text). Review against current main: much of the requested
triggered-grant path already exists; do not add its duplicate executor blindly.
Artificer's Dragon's reviewed provider run was rejected for direct checkout mutation.
Do not reset attempts; review retained artifacts and make a concrete correction.

### 2026-09-15 21:24 UTC — Sigil candidate green; next two bounded corrections

- Sigil correction passed every original candidate gate plus the actual-combat notification regression. Accepted receipt: `docs/factory-ng/runs/2026-09-15T212319Z-engine-operator-sigil-proof-recovery-sep15-v1.json`. Normal full production integration is running; not counted as completed yet. Original staged-profile failure remains preserved.
- `filtered-pump/` contains an isolated correction connecting explicit native `Affects` to the existing mass pump executor in all three converters, plus public action tests. No runtime empty-target inference; unsupported qualifier combinations fail explicitly instead of broadening recipients. Original named and full gates are running.
- `grant-ability/` contains an isolated correction for the missing activated-to-triggered nested conversion and unique temporary trigger instances per repeated grant. Public spell/activation/combat/draw/cleanup tests preserve the existing activated grant path. Original named and full gates are running.
- Reviewed retry inventory has reached 38 admitted originals; 21 original lineages completed as of 21:23:36 UTC. Current watchdog is healthy with no problems. Goal remains active.

### 2026-09-15 21:27 UTC — Sigil production integration green

Sigil passed full production integration and pushed `8777a731a2512ca56a76e977ac3137b7668a23d7`. Immutable receipt: `docs/factory-ng/runs/2026-09-15T212319Z-engine-operator-sigil-proof-recovery-sep15-v1-1789507400000856091-integration.json`. The distinct operator proof resolves the functional ticket; it does not turn the original failed staged-model observation into a successful profile benchmark. Canonical checkout was clean after integration.

`exile-filter/` adds the next isolated correction: retain parsed disturb ability identity for a creature-with-disturb target bucket and reuse existing Spirit/enchantment union targeting and exile. Public positive/negative, legacy/native conversion, resolution recheck, and neighboring plain exile tests are running with all original gates.

### 2026-09-15 21:35 UTC — candidate follow-up

- Filtered-pump initial gate exposed a missing `artifact_creature` runtime filter bucket as well as fixture priority/main-phase setup errors. Added the conjunctive type bucket and corrected those fixtures. The executor rejects unsupported recipient qualifiers without broadening the set; the public spell resolver currently discards executor errors, so the negative test observes absence of a pump rather than expecting that API to propagate an error. Failed evidence is retained.
- Grant-ability initial check found test compilation errors (`Zone.Size` instead of `Zone.Count`); corrected only the fixture API calls and reran the entire original gate list.
- Structural Collapse candidate now preserves a pending edict's enclosing sequence, resumes only after its choices (including chained players), and shares exactly one player target across the bounded artifact/land/damage shape. Named public tests cover both player targets, choices and forced/no-eligible cases, order, wrong chooser, exclusions, and stolen ownership. All original gates are running.
- Two owned local candidate process trees were terminated by exact PID to correct known fixture assumptions before completing their check runs. No worker/controller process was terminated, no test was removed, and no interrupted run is treated as passing. The interrupted check logs are retained.
- Ulalek remains unresolved; `ulalek-runtime-review.md` records the missing per-copy retargeting choice flow.

### 2026-09-15 21:44 UTC — remote operator verification pilot

The initial exile-filter gate passed all positive/negative type-membership cases and adjacent plain exile cases, but correctly failed the resolution recheck after the target lost disturb. The corrected candidate explicitly declares one target for the new filter so the shared resolution validator runs; both legacy and native recheck cases are included. The failed evidence is preserved in `exile-filter/initial-gates.json`.

The changed candidate is now using the already-enabled ordinary remote verifier on slot 3, after read-only inspection found no active verification containers. `exile-filter/remote-manifest.json` pins the operator identity, zero provider calls, ticket hash, source revision, and proposal patch. This uses the same original gates and immutable receipt import, with no controller/job mutation. The other three local candidate checks continue unchanged.

### 2026-09-15 21:49 UTC — three candidate corrections accepted

- Exile filter passed the ordinary remote verifier with its exact original gate list, including full game/cards suites. Receipt: `docs/factory-ng/runs/2026-09-15T214619Z-focused-e4c90bf4c62f4cfa979137f3b5143c74-0.json`. Normal production integration is running.
- Filtered pump was moved from a still-compiling local check to remote slot 1; interrupted local evidence is retained. The remote verifier passed scope, vocabulary handoff, formatting, named behavioral selector, full game/cards suites, and diff integrity. Receipt: `docs/factory-ng/runs/2026-09-15T214825Z-focused-4a7c1d8b30884306bf95b834ca30b355-0.json`. Normal production integration is queued.
- Temporary ability grants passed all original local candidate gates. Accepted receipt: `docs/factory-ng/runs/2026-09-15T214909Z-engine-operator-grant-ability-recovery-sep15-v1.json`. Normal production integration is queued.
- Structural Collapse moved from an unfinished local compilation to remote slot 2 with the exact pinned patch and original gate list; interrupted logs are retained. No actual failed check was hidden by these host changes.
- The normal integrator owns and serializes canonical mutations. None of these three candidates is counted as completed until production integration is green.

### 2026-09-15 21:56 UTC — 25 completed; pump conflict repaired

Three full production integrations completed and pushed:
- Exile filter: `0237aeb00d8639d847c18d70087f245066c45e38`; receipt `docs/factory-ng/runs/2026-09-15T214651Z-engine-operator-exile-filter-recovery-sep15-v1-1789508811463297513-integration.json`.
- Temporary ability grant: `a878ecb9f4da5e6eaaceec3ef16f771baf2ee31a`; receipt `docs/factory-ng/runs/2026-09-15T214910Z-engine-operator-grant-ability-recovery-sep15-v1-1789508950482150557-integration.json`.
- Structural Collapse: `0e46dd46b537e9d57ec76c06ba064c3457017265`; receipt `docs/factory-ng/runs/2026-09-15T215123Z-engine-operator-structural-collapse-recovery-sep15-v1-1789509083064068548-integration.json`.

Filtered pump v1 encountered an integration conflict with the newly integrated grant conversion and disturb filter. Failed receipt remains immutable: `docs/factory-ng/runs/2026-09-15T215327Z-engine-operator-filtered-pump-recovery-sep15-v1-1789509207246052511-integration.json`. `filtered-pump-rebase/` is a new pinned v2 correction based on the latest green Structural Collapse commit; both sides of the two adjacent insertion conflicts are preserved. All original gates are rerunning remotely. Original accepted ticket/receipt files were not rewritten.

`triggering-copy/` is a new isolated correction for the reviewed Archmage of Echoes formatting failure. The original proposal lacked negative coverage and reused incomplete token-copy state. The correction uses the existing event stamping, copies only the exact event spell while it is still controlled on the stack, preserves printed characteristics, and gives copied triggered/activated abilities independent identities. Public-cast tests include Faerie/Wizard and multiple permanent types, opponent/nonpermanent/unrelated-subtype negatives, another spell on the stack, a vanished original, and functional token-copy ETB abilities. Remote verification is running.

### 2026-09-15 22:02 UTC — Archmage integration green; Cloudstone verification

Archmage of Echoes correction passed every original remote candidate gate, then full production integration and pushed `13d5a17b62d6f46fe60a2d633bcdbf73414d3156`. Integration receipt: `docs/factory-ng/runs/2026-09-15T215633Z-engine-operator-triggering-copy-recovery-sep15-v1-1789509393258756186-integration.json`.

Filtered-pump v2 passed all original remote gates again; accepted receipt `docs/factory-ng/runs/2026-09-15T215759Z-focused-1ec5786673c543e0a85af5137df4fda1-0.json`. Normal production integration is running.

`shared-type-bounce/` is the next operator correction for Cloudstone Curio. It adds the nonartifact-permanent event predicate, binds matching to the entering object, excludes that object and other players' permanents, and uses the existing optional PendingChoice bounce path even with a sole candidate. Public cast/ETB/choice tests cover both controllers, decline, no candidates, wrong chooser, excluded objects, artifact/opponent entries, and stolen ownership. Remote verification is running.

## 22:27 UTC follow-up

Cloudstone Curio completed full production integration and push 6173533df8d81070974ed6eef2be4a2a859348fa. Righteous Indignation required a separate Engine prerequisite: public DeclareBlockers emitted no blocks event, and receiver color restrictions were not converted or matched. Engine push 6db2cd1942535ae50ef71c1919c51d8973c6576f supplies both. The Map fix preserves the black-or-red blocked-creature qualification, fixes the tuple assertion, and refuses unproven adjacent qualifiers; full-green push fdf3b243f8bcfa66617bfa640cde4f5ac0d35646 completes that original Map ticket.

A saved Rabble-Rouser dependency proposal incorrectly assumed BasePower includes continuous effects and tested BasePower writes rather than public resolution. Operator attacking-pump uses effective source power once at resolution and applies it only to current attackers. Public activation/attack tests cover both players, source attacking, negative/zero/positive amounts, modifiers after activation, later entrants, and cleanup. Full-green push c67645fa2b99d0f0f546495e6146d5029e7dc4b7 completes the Engine prerequisite, not the original Map ticket.

Remote launcher formatting gap: both host scripts linked go but omitted gofmt, and legacy formatting gates masked command-not-found. Both launchers now link gofmt; 8 remote and 12 full-gate tests pass. Supplemental local audits verify changed Go files of six affected candidates are formatted. Corrected production block-receiver-color receipt has an empty successful formatting output. Historical receipts retained. See remote-gofmt/.

Dovin's Veto already has an integrated noncreature counter runtime and maps correctly. Its operator test verifies the real card retains uncounterability and the noncreature target; it exposed a neighboring creature-spell restriction erased by the object parser. The Map patch refuses that unsupported case. Candidate gates green, production integration running.

Single-graveyard exile Engine prerequisite in remote verification (single-graveyard/). Adds registration plus public graveyard-card targets, same-graveyard declaration validation, optional bounded or exact paid-X bounds, and resolution zone rechecks; existing private executor retained. Original Rats' Feast and Scarab Feast Map tickets remain open.

## 22:43 UTC follow-up

Single-graveyard Engine prerequisite integrated green at 761dada5eb26259920871514a3f4d4e56a4a052f. Rats' Feast Map completed green at 3d6011c8fb0382757a3c88b658ea67ebd7c720b5; Scarab Feast Map completed green at 09f9ae5b53d9d675af10cef196d2c4b1a8689e16. Both preserve chosen graveyard-card targets and the same-graveyard requirement; Rats binds exact paid X and Scarab preserves zero-to-three targets and cycling. Each retains every original gate and separate integration evidence.

Current cohort snapshot at22:41:48: 35completed,6blocked,3parked,1awaiting_verification,5queued,69failed,2working;46reviewed originals admitted. Still incomplete. Latest completed health check had watchdog healthy, canonical clean, profiles green, backend active. The watchdog's transient dead-PID reports cleared as controller consumed completed worker outputs.

Rabble-Rouser Map retries uncovered a further genuine missing runtime: bloodthirst keyword_cost is grandfathered but not registered or implemented. Separate bloodthirst/ Engine candidate in remote verification adds entry specs and battlefield-entry hook for numeric/X counters based on actual opponent damage, skipping duplicate spell-resolution application. Tests cover both controllers, cast/noncast entries, life loss, own damage, prevention, previous-turn reset, and counters visible at ETB. Original Map still open.

Attached-control revisions1and2 failed candidate tests and are retained. v1 test cast outside main phase; v2 revealed enchanted recipient filtering suppressing self ETB. v3 classified it as recipient but further review found the existing else branch still copies Affects to SourceType. v4 being prepared with a narrow exception for attached-control recipients. No attached-control revision accepted yet.

Patch delimiter harness fix in patch-delimiters/: supports exact === newline REPLACE variant seen in two current failed dependencies, rejects incomplete additional hunks and nested control markers;4 applicator+1 duplicate-regression+31staged tests pass. Existing modifications to scripts/map-pipeline-apply.py preserved.

## 22:48 UTC candidates

Attached-control v4 passed all candidate gates and is in production integration. Public Aura casting verifies attachment and the self ETB trigger, plus temporary steal/untap/haste and cleanup. Activated coverage verifies attached recipient, missing attachment, explicit target precedence, and false target_attached marker. v1-v3 failures retained. Final converter fix keeps enchanted Affects as recipient-only through BOTH legacy filter branches.

Bloodthirst v2 passed candidate gates including handwritten-handler precedence and is accepted pending integration. Do not integrate v1: it would duplicate legacy handler counters. v2 preserves existing handler authority; both numeric and X Bloodthirst use actual opponent damage and every ordinary battlefield AddCard/AddCardToBottom route. Existing EtbCounterSpec flags avoid extra card fields/DFC copy omissions. Original Rabble-Rouser Map v4 remains awaiting verification and may need a new pinned source revision after this prerequisite integrates.

trigger-player-filter/ candidate is in remote verification. It proves existing defending_player target qualification through public combat, controller's choice, destroy resolution, owner graveyard, controller changes, plain-filter comparison, prevention and noncombat negatives. No runtime change claimed; original Engine capability parent only, not full Blind Zealot Oracle implementation.

### Full production gate updates (23:03 UTC)

Counter-threshold and Rabble-Rouser corrections both passed full integration and pushed: `62eea60c6468c88f9bf51402e74f80aba723a1c7`, `30bcd8feb647a7cefd52307b7a134e10ca875204`. Bloodthirst v2 and trigger-player-filter previously pushed `168e3851cc5e1e8ff2b1e2552a311dd18626ee31` and `34cc81873d7259200a95c945cf99339976e98a85`. Each review directory retains its immutable focused and integration receipts.
