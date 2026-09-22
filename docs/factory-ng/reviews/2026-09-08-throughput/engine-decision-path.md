# Engine simplicity and staged failure evidence

September 8, 2026 follow-up to the throughput review. This is a design
recommendation, not an activated policy or an implementation change.
Canonical source inspected: `6642351731e0c336cd220a861dd14fc212e7d192`.
Historical cases below were checked against their own pinned source where
stated. No model calls, source mutations or deployments were performed.

The user clarified that similar-card batching has already exhausted its easy
frontier, and Forge/XMage reuse has already been tried without meeting the
project's requirements. Neither is recommended as the next direction.

## Finding

There is concrete evidence of card-specific combinations accumulating inside
the engine and making narrowly scoped authoring difficult. There is also
independent evidence that staged attempts fail because their preparation and
repair path is incomplete. These observations do not establish that the whole
engine should be rewritten, that all Engine tickets are unnecessary, or that
board state and scalar counters alone are sufficient for Magic.

The proposed direction is staged authoring of individual ability functions
against a small explicit engine interface. Keep a card as the completion and
cost-accounting unit; use bounded ability edits as the generation unit. A real
shared rule change can remain a separate dependency with its costs attached
to the original card. Similar-card batches are not required.

## Code evidence

1. `backend/game/ability_effects.go:3515` starts ExecuteAbilityEffect. The next
   top-level function starts at 8108: the span is about 4,600 lines including
   comments. It combines early special-case returns, amount rewrites, target
   rewrites and a large dispatch switch. Examples include
   conditional_pump_on_creature_type, untap_dynamic_x_target_lands,
   destroy_target_unless_life_at_least and destroy_all_attached_to_target.
   These are combinations of behavior, scope, conditions or timing, not merely
   new fundamental game actions. This supports a composition/interface audit;
   it does not prove that a particular branch can be deleted safely.

2. Existing generic machinery is substantial. dynamic_amount.go already
   evaluates battlefield/hand/graveyard counts, source/event/target stats,
   arithmetic and turn history. Some specialized handling still lives in
   ExecuteAbilityEffect. For example, sum_of_counts is specially dispatched
   there although its helper recursively evaluates operands through the
   general evaluator. Counts sometimes construct a ContinuousEffect solely
   to call EffectManager.evaluatePerCount. Reuse exists but crosses interfaces
   that an ordinary card author has to discover.

3. Several exile executors at ability_effects.go:2274–2430 repeat graveyard
   removal and exile insertion while varying whether selection comes from
   one graveyard, an event player, one targeted player or several targeted
   players. These differences are real. A possible simplification is to
   separate selection from a shared, rule-aware zone operation. That requires
   checking event emission, ownership, identity changes, replacements and
   simultaneous behavior; replacing all of them with an unexamined loop would
   not be a safe refactor.

4. The Engine producer's CORE_PATHS permits eight existing central files plus
   per-ticket tests/registry files, and forbids backend/cardfns and parser
   changes. A worker cannot simply choose a new isolated production helper
   file. This template helps steer card-specific work into central engine
   code. Changing this boundary would be a deliberate design change.

5. Engine identity hashes the entire capability object, while the generated
   test function name uses only capability.key. Across the inventory, 58 of
   861 capability keys have more than one identity even after removing /vN
   versions. This is not proof of 58 semantic duplicates: one confirmed pair
   uses the same filter_dealt_damage_this_turn key for *dealt damage* and
   *was dealt damage*, which are different behaviors. Both receive the same
   required test name, and the later candidate fails to compile with that
   symbol already present. Identity needs both precise semantics and collision-
   free generated symbols; merging by similar names would be wrong.

## All unsuccessful staged observations in the earlier 24-hour snapshot

Window: September 7 12:42:22 to September 8 12:42:22 UTC. Of 42 Claude staged
observations, 24 were accepted and 18 were unsuccessful. The associated
`staged-failure-review.csv` lists all 18, their categories and receipt paths.

| Observed obstacle | Attempts |
|---|---:|
| Missing source evidence or incompatible path scope | 6 |
| Compile/vet errors such as wrong fields, types or argument lists | 5 |
| Required test symbol already exists | 2 |
| Malformed edit protocol | 2 |
| No usable edit or verdict response | 1 |
| Worker claims a cross-cutting framework gap; not independently established | 1 |
| Behavior test fails; exact semantic cause not established from receipt tail | 1 |

Categories describe observed obstacles, not proof that fixing one makes the
whole candidate correct. Multiple defects may remain. The comparison does
not establish a causal improvement rate for any proposed repair.

### Deterministically reproduced context failure

Receipt: ../../runs/2026-09-07T190220Z-engine-auto-grant-keywords-until-eot-conditional-205e618cf1-v2-claude.json

The raw model response requests:

`NEED: backend/game/ability_effects.go: grant_keywords_until_eot case in ExecuteAbilityEffect (and any executeGrantKeywords* function)`

Replayed the actual requested_context function from
scripts/factory-ng-run-engine-ticket.py against minimal files extracted with
git show from pinned revision `1aecc4b90746a8502d87a45ab42e5e3881524db0`.
The replay returns ability_effects.go lines 1124–1288. Its first text match
is a comment at 1169. The actual `case "grant_keywords_until_eot":` is at
4797 and is absent from the returned continuation. This confirms the worker's
missing-evidence explanation for the continuation, rather than merely taking
its verdict on trust.

The active NG requested_context implementation is separate from the more
capable pipeline-fetch-regions.py helper. It picks the first identifier in a
request, then its first substring occurrence, and returns a short surrounding
excerpt. A bare path returns the first 120 lines. It also conflates permitted
edit paths with permitted context-read paths.

### Scope contradiction

The spell_seq_atom_up_to_n_target_cap v3 ticket explicitly names
gamestate_cast.go as the validation location but excludes it from allowed
paths. Its worker parks for this reason. A better prompt cannot authorize a
correct edit outside that declared scope.

The same ticket specifies 1..N choices for "up to N" targets, omitting zero.
That contract also needs premise correction rather than faithful enforcement
of an incorrect restriction. CR 115.6 covers targeted spells with zero chosen
targets. This observation is a specification finding, not a runtime repair.

### Incomplete repair stage

The inspected NG Engine runner offers a bounded repair after patch application
fails. Once a patch applies, it runs the ticket gates and records gate_failed
if they fail; it has no same-attempt compile/test-feedback repair stage.
Examples therefore terminate on Card.Power not existing, the wrong
GetEffectsAffecting argument count, or a Fatalf format error. Some later
successor-ticket repair paths exist, but they do not make this execution path
equivalent to generate → compile/test → focused repair.

## What a sleek engine must provide

Aim for a small public authoring interface, retaining the actual rules inside
the shared implementation. Needed concepts include source/controller, chosen
targets, triggering-event references, current state, required historical
facts, choices, rule-aware actions and continuous-effect lifetimes.

Board state does not reconstruct every historical fact. A replaced draw must
not count as an actual draw; multiple draws occur individually; an ability
may need an object's last known characteristics; continuous effects have
ordering requirements. These are reasons to centralize the mechanics so a
card function can stay small. See CR 121.2, 608.2h–i, 613 and 614.6 in the
[official rules](https://media.wizards.com/2026/downloads/MagicCompRules%2020260819.txt).

## Recommended decision sequence

1. Keep staged as the normal generation method. First correct and replay the
   documented preparation/scope/symbol/feedback failures with full original
   behavior checks. Do not infer an engine rewrite from these failures.
2. Audit a small set of real remaining Engine demands against executable
   behavior: capability exists but is unseen; composition/bridge missing;
   context/history missing; or genuinely new rule semantics. Do not classify
   by names alone. This supplies the missing avoidable-Engine-ticket fraction.
3. Pick one demonstrated obstruction and expose a small shared interface over
   existing behavior. Use different individual cards to challenge it. Each
   card gets its own implementation and acceptance evidence; no shared batch
   solution is assumed. Include preparation and interface cost in the result.
4. Let the staged packet contain one complete ability contract, exact API
   types, edit location and test fixture. Support a bounded compile/test repair.
   The card retains the accumulated plan and completed abilities so successors
   do not restart whole-card discovery. Keep shared game-rule changes separate.
5. Retain the approach only if unseen cards need less discovery, fewer central
   edits and fewer Engine dependencies at unchanged correctness. If failures
   remain missing-rule failures, build those rules; if they remain context
   failures, improve preparation. Use bounded agentic diagnosis when the missing
   contract cannot be resolved mechanically, then return to staged authoring.

No promise of 100 or 400 cards/day follows from source inspection. A full
quota-week measurement and cost per completed card remain the throughput proof.
No final giant refactor is proposed: each shared-interface extraction should
retain existing behavior and immediately serve the concrete card at hand.
