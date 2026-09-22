# Remaining-work triage — September 8, 2026

Read-only production review, recorded 2026-09-08T19:02:02.483497+00:00. Job snapshot updated
`2026-09-08T18:57:31Z`; canonical card records read from
`da85419117f69262d386b2b268b30bdcbc922b28`. The factory continued running during this review.
[Structured inventory](remaining-work-triage.json) retains all 52 ticket IDs,
receipt/patch hashes, exact failed gates, test names, dependency links and six
card histories. No source, tickets, jobs, policy or running processes changed.

## Finding

The watchdog's 52 unresolved integration failures are all Engine jobs. It
already excludes 25 superseded integration failures. None of these 52 has an
immutable direct successor in the captured ticket inventory, and none has a
superseded direct Map parent. They cannot be dismissed as stale warnings.

| Failure class | Count | Required disposition |
| --- | ---: | --- |
| Required test selector does not match candidate tests | 35 | Review semantic coverage; issue fresh successors with explicit test obligations and rerun gates. |
| Candidate patch conflict | 15 | Inspect current implementation, then rebase/reconstruct only still-needed behavior in isolated candidates. |
| Duplicate Go test symbol | 1 | Lantern of the Lost: use an unambiguous test identity, preserve behavior and rerun composition gates. |
| Go compilation failure | 1 | Soulcoil Viper: repair duplicate short variable declarations in the composed candidate. |

For every one of the 35 selector failures, the retained patch adds tests under
different names from the TicketSpec's exact required name. For example, Pulse
of Murasa requires `TestFactoryNGBounceTargetFilterGraveyardZone`, while its
patch adds `TestBounceFromGraveyardEffect_CreatureCard`. Integration correctly
rejects the no-test run. This is not proof that simply renaming the test would
satisfy the semantic contract. Review all clauses and add missing assertions;
do not rewrite old receipts or weaken the required tests.

The other two composed-gate failures are precise: Lantern of the Lost redeclares
`TestFactoryNGExileTargetCardFromGraveyard` across `factory_ng_d5c2a6e92f_test.go`
and `factory_ng_d1e31b337e_test.go`; Soulcoil Viper reports “no new variables on
left side of :=” in `ability_effects.go`. The structured inventory includes
the full candidate-specific gate evidence, rather than a wave's aggregate result.

## Why automatic recovery is not clearing them

1. **Ordinary Engine repairs have no admission reserve here.** The snapshot has
   215 queued jobs, versus the controller's current admission cap of 9. The
   ordinary producer loop is skipped while that inventory exceeds its cap.
   The exceptional Engine reserve handles dependencies of Map integration
   recovery only. None of the 52 direct Map parents is superseded; these
   failures remain live obligations. The producer's existing per-chain check
   permits one integration repair for 51; Falkenrath Exterminator has already
   used that repair. This is eligibility under the repair-limit check, not a
   claim that all 51 would pass preparation. See controller
   `run_once`/`producer_loop_needed` and capability producer `main`.
2. **Tidal Surge loses recovery generation across dependency resumes.** Map
   v3 records `integration_repair_generation=2`; v4 and v5 retain only
   `integration_recovery_parent`. `resumed_map` replaces the production object.
   After v5 fails a worker gate, `integration_repair_candidate` skips it because
   `integration_repair_generation` is absent. Preserve and evaluate ancestry
   consistently, including the already-used repair limit. Do not reset the
   counter to grant an unlimited new retry. This card needs an explicit bounded
   successor decision after its fresh parser failure is understood.
3. **Three completed audited dependencies are waiting for Map admission.**
   Sigil, Siegfried and Cicada have completed Engine successors but no Map
   successors in the snapshot. The two-slot dependency reserve is occupied by
   Pendelhaven (awaiting integration) and Patch Up (integrating). That is a
   bounded queue wait, not proof of a broken Engine-to-Map identity link.

## Audited cards

All six are still `review` in the pinned canonical card records. None is counted
as a completed card by this review.

| Card | Current chain | Next bounded task |
| --- | --- | --- |
| Tidal Surge | Map v5 failed after both Engine dependencies completed. Full parser still reports `spell_seq_targeted: tap up to three target creatures without flying.` | Repair the parser composition and recovery ancestry. Verify 0–3 legal nonflying targets, reject excess/illegal targets, and test normal casting/resolution. |
| Siegfried, Famed Swordsman | Map v1 blocked; dynamic-counter Engine v2 completed. | Admit complete-card Map verification through the existing reserve; test menace, ETB mill then graveyard count, including zero. |
| Sigil of Sleep | Map v1 blocked; player-damage Engine v2 completed. | Verify Aura attachment and full trigger/choice/resolution against the new event contract; retain prevention, damaged-player and ownership checks. |
| Skittering Cicada | Map v1 blocked; keyword/dynamic-P/T Engine v2 completed. | Verify all abilities, including flash and casting other colorless spells as though they had flash, plus the cast trigger, X and EOT expiry. |
| Rakdos Roustabout | Engine v3 failed on `Fatalf` format `%d` applied to string `pw.ID`; Map v1 remains blocked. | Fresh verification successor using the existing attacked-defender resolver. Correct the test compile defect and cover real block declaration, combat removal and last-known recipient. |
| Sea God's Scorn | Engine v2 parked after unrelated source evidence; Map v1 remains blocked. | Reuse union targeting/bounce and the integrated 0–3 casting bounds in a fresh evidence-backed verification/composition successor. Its existing Engine identity is still parked, so the shared target-count fix alone will not release its Map job. |

## Proposed repair order

1. **Repair recovery bookkeeping and admission**, retaining ancestry-based retry
   limits and a small explicit reserve for existing failed Engine integrations.
   Verify with snapshot-derived scheduling cases: saturated queue, Tidal v5,
   exhausted Falkenrath repair and no duplicate successor. This addresses
   admission; it does not reopen failed candidates as accepted.
2. **Start with Tidal Surge as the concrete parser repair**, and let the three
   completed audited dependencies enter their existing Map verification reserve.
   Correct Rakdos's test contract and Sea God's Scorn's evidence/connection
   contract as separate bounded work. Preserve a full-card acceptance checklist
   for each card, especially Cicada's independent flash permission.
3. **Recover the 35 selector-mismatch candidates in small batches.** Inspect the
   candidate tests against the required behavior, refresh scope/source evidence,
   create unique explicit tests, then pass focused and full production gates.
   Do not commission 35 new implementations before reviewing retained patches.
4. **Repair the duplicate-test and compilation cases, then the 15 conflicts**
   using the same normal gates. A conflict can conceal already-landed behavior;
   inspect current source before adding more code.
5. **Run the five-card measured trial after these prerequisites.** Select five
   distinct cards explicitly. Keep prior operator repairs separate from model
   trial costs; record complete-card acceptance, all attempts and stage timing.
   Dashboard/SQLite expansion and throughput claims remain deferred.

## Verification and limits

The inventory checks partition all 52 unsuperseded failures, resolves each
candidate's own failed gates, confirms differing added test names in all 35
selector cases, verifies the absence of direct successors, and reads all six
card states from one immutable Git revision. Existing immutable Engine
integration receipts confirm the four audited corrections were pushed.
No tests or paid model trials were run during this triage. Current behavior
and semantic sufficiency of old patches require fresh isolated verification.
The startup health check passed its service/profile checks; the watchdog is
unhealthy because of persistent failures. Integration owned the canonical
checkout during inspection. Live deployment remains disabled.
