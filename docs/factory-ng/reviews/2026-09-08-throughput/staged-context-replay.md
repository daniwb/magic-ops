# Historical source-request replay

Pinned revision: `1aecc4b90746a8502d87a45ab42e5e3881524db0`.
No model calls; the source was read with `git show` into a temporary directory.

The old resolver selected an early comment at line 1169 and returned lines 1124–1288. The repaired resolver includes the actual dispatch at line 4797. Excerpts remain bounded and disclose truncation.

```text
NEED: backend/game/ability_effects.go: grant_keywords_until_eot case in ExecuteAbilityEffect (and any executeGrantKeywords* function)
```

```go
### backend/game/ability_effects.go:4797-4922 (source match)
 4797 	case "grant_keywords_until_eot":
 4798 		// "X gains KEYWORD (and KEYWORD) until end of turn" — plural-keyword
 4799 		// variant (schema-v2 3c round 4: 123 records were parser-emitted with
 4800 		// zero consuming code). Recipients, in priority order: explicit
 4801 		// targets → affects.enchanted (the permanent this Aura is attached
 4802 		// to, stashed by the converter as affects_filter) → affects group
 4803 		// (creature/permanent you control) → the source itself (the common
 4804 		// "{cost}: ~ gains flying until end of turn" self-shape).
 4805 		kws := keywordListFromValue(effectValue)
 4806 		if len(kws) == 0 || gs.EffectManager == nil {
 4807 			return nil
 4808 		}
 4809 		grant := func(cardID string) {
 4810 			for _, kw := range kws {
 4811 				gs.EffectManager.Register(&ContinuousEffect{
 4812 					Source:          source,
 4813 					SourceID:        source.ID,
 4814 					AffectsSpecific: cardID,
 4815 					GrantKeyword:    kw,
 4816 					UntilEOT:        true,
 4817 				})
 4818 			}
 4819 		}
 4820 		if len(targets) > 0 {
 4821 			for _, t := range targets {
 4822 				if t.IsCard && t.CardID != "" {
 4823 					grant(t.CardID)
 4824 				}
 4825 			}
 4826 			return nil
 4827 		}
 4828 		affects := getStringValue(effectValue, "affects_filter", "")
 4829 		// grant_keywords_until_eot_controlled_creatures primitive (ticket
 4830 		// engine.auto-grant-keywords-until-eot-controlled-creatures-
 4831 		// be9ff5177e): a TRIGGERED ability's mass "creatures you control
 4832 		// gain KEYWORD until end of turn" clause (Essence of Antiquity: "...
 4833 		// creatures you control gain hexproof until end of turn") reaches
 4834 		// this executor as a plain EffectValue["target_filter"] ==
 4835 		// "all_creatures_you_control" sequence-atom key — converter.go's
 4836 		// EffectAtomSpec loop never stashes the affects_filter/
 4837 		// affects_controller pair AbilityToActivated stashes for
 4838 		// single-effect ACTIVATED abilities, so the mass shape had no way
 4839 		// to reach the existing "creature"/"you" branch below. Alias it
 4840 		// onto that SAME branch (affects_controller already defaults to
 4841 		// "you") instead of a parallel per-card loop, reusing the identical
 4842 		// filter-scoped ContinuousEffect path — self-shape (no
 4843 		// affects/target_filter) and single-target shape (explicit
 4844 		// targets, handled above) are untouched.
 4845 		if affects == "" && getStringValue(effectValue, "target_filter", "") == "all_creatures_you_control" {
 4846 			affects = "creature"
 4847 		}
 4848 		switch affects {
 4849 		case "enchanted", "equipped", "equipped_creature_and_equipment":
 4850 			if source.AttachedTo != "" {
 4851 				grant(source.AttachedTo)
 4852 				if affects == "equipped_creature_and_equipment" {
 4853 					grant(source.ID)
 4854 				}
 4855 			}
 4856 		case "creature", "permanent":
 4857 			// affects_subtype/affects_controller/affects_other (task-2366):
 4858 			// forwarded by converter.go's isRecipientAffects glue from the
 4859 			// ability's top-level Affects field, same as pump_all's
 4860 			// group-keyword-grant shape below, but previously never read
 4861 			// here — every subtype-qualified group grant ("Knights you
 4862 			// control gain double strike until end of turn") silently
 4863 			// widened to "every creature you control" instead. Filter-scoped
 4864 			// ContinuousEffect (not a per-card grant() loop) so the existing
 4865 			// AffectsSubtype/AffectsController/ExcludeSelf matching in
 4866 			// effectAffectsCard — the same code pump_all's keyword grants
 4867 			// already rely on — does the recipient check instead of a
 4868 			// hand-rolled reimplementation.
 4869 			affSubtype := getStringValue(effectValue, "affects_subtype", "")
 4870 			affController := getStringValue(effectValue, "affects_controller", "you")
 4871 			excludeSelf, _ := effectValue["affects_other"].(bool)
 4872 			// affects_token (task-2366): "creature TOKENS you control gain
 4873 			// KEYWORD until end of turn" (Ainok Strike Leader, King Darien
 4874 			// XLVIII, Ravenous Robots) — same forwarding as affects_subtype
 4875 			// above, read straight off the atom's own value map.
 4876 			affToken, _ := effectValue["affects_token"].(bool)
 4877 			// affects_counter_type (task-2418): "creatures you control with
 4878 			// [a/no] counter(s) on {it,them}" (Bulwark Ox, Tyrant Guard,
 4879 			// Chocobo Knights, Synchronized Charge). effectAffectsCard
 4880 			// already gates generically on ContinuousEffect.AffectsCounterType
 4881 			// ("any" sentinel = presence of any counter kind, mirrors the
 4882 			// STATIC grant_ability path's identical field, task 2370) — this
 4883 			// case just never forwarded it.
 4884 			affCounterType := getStringValue(effectValue, "affects_counter_type", "")
 4885 			// grant_valued_keyword_until_eot (ticket engine.auto-grant-
 4886 			// valued-keyword-until-eot-1312f3366b, Plague Nurse class):
 4887 			// "Each other creature you control with toxic gains toxic 1
 4888 			// until end of turn" — a VALUED keyword grant to a filtered
 4889 			// group, unlike the plain boolean/presence keyword grants the
 4890 			// loop below handles. Dispatches to the dedicated executor
 4891 			// above instead, since the granted value has to land on
 4892 			// Card.ToxicN directly rather than through a lazily-evaluated
 4893 			// filter effect (see that executor's doc). Absent
 4894 			// keyword_value (every existing boolean keyword grant: flying,
 4895 			// haste, reach, deathtouch, indestructible, ...) this is a
 4896 			// no-op and control falls straight through to the untouched
 4897 			// loop below.
 4898 			if kwValue := getIntValue(effectValue, "keyword_value", 0); kwValue != 0 {
 4899 				requiresKw := Keyword(strings.Title(strings.ToLower(getStringValue(effectValue, "requires_keyword", ""))))
 4900 				for _, kw := range kws {
 4901 					gs.executeGrantValuedKeywordFilteredUntilEOT(controller, source, kw, kwValue, requiresKw)
 4902 				}
 4903 				return nil
 4904 			}
 4905 			for _, kw := range kws {
 4906 				gs.EffectManager.Register(&ContinuousEffect{
 4907 					Source:             source,
 4908 					SourceID:           source.ID,
 4909 					GrantKeyword:       kw,
 4910 					AffectsFilter:      affects,
 4911 					AffectsSubtype:     affSubtype,
 4912 					AffectsController:  affController,
 4913 					ExcludeSelf:        excludeSelf,
 4914 					AffectsToken:       affToken,
 4915 					AffectsCounterType: affCounterType,
 4916 					UntilEOT:           true,
 4917 				})
 4918 			}
 4919 		default:
 4920 			grant(source.ID)
 4921 		}
 4922 		return nil

### backend/game/ability_effects.go:2571-2644 (source match; truncated, remaining lines 2645-6748)
 2571 func (gs *GameState) ExecuteAbilityEffect(stackObj *StackObject) error {
 2572 	if stackObj == nil || !stackObj.IsAbility {
 2573 		return nil
 2574 	}
 2575 
 2576 	// event_amount count spec (ticket #3730): the resolving object's own
 2577 	// stamped event magnitude (StackObject.EventAmount, set by
 2578 	// stampEventCard) is exposed to EvalDynamicAmountFull via a
 2579 	// GameState-scoped field for the duration of this call — the spec
 2580 	// resolves to the triggering event's numeric magnitude ("put that
 2581 	// many"). Saved/restored so nested effect execution (a sequence atom
 2582 	// resolving another ability) can't read a stale magnitude.
 2583 	savedEventAmount := gs.eventAmountStamped
 2584 	if stackObj.HasEventAmount {
 2585 		gs.eventAmountStamped = stackObj.EventAmount
 2586 	} else {
 2587 		gs.eventAmountStamped = 0
 2588 	}
 2589 	defer func() { gs.eventAmountStamped = savedEventAmount }()
 2590 
 2591 	effect := stackObj.Text
 2592 	controller := stackObj.Controller
 2593 	source := stackObj.Card
 2594 	effectValue := stackObj.EffectValue
 2595 	targets := stackObj.Targets
 2596 
 2597 	// tap_untap_shared_creature_type_referent primitive (Faces of the
 2598 	// Past class): the referent is the triggering event's subject
 2599 	// (stackObj.EventCard), never an explicit target, so this dispatches
 2600 	// straight to the battlefield-wide sweep and returns before the
 2601 	// normal effect switch below, the same early-fold shape
 2602 	// resolveModalChoiceEffect/resolveRecipientFromEventCard use above.
 2603 	if effect == "tap_untap_shared_creature_type_referent" {
 2604 		gs.executeTapUntapSharedCreatureTypeReferent(effectValue, stackObj.EventCard)
 2605 		return nil
 2606 	}
 2607 
 2608 	// targeted_effect_dynamic_x_count primitive (ticket
 2609 	// engine.auto-targeted-effect-dynamic-x-count-d629ddac55, Candelabra of
 2610 	// Tawnos class: "{X}, {T}: Untap X target lands."). X-target abilities
 2611 	// announce/pay their {X} activation cost BEFORE targets are chosen
 2612 	// (Rule 601.2b), so by the time this stack object resolves,
 2613 	// stackObj.Targets already holds exactly the X targets the activating
 2614 	// player chose — this executor's job is narrow: apply the effect to
 2615 	// every target it was handed, no fewer (a fixed single target) and no
 2616 	// more (a battlefield-wide sweep), unlike
 2617 	// executeTapUntapSharedCreatureTypeReferent above which deliberately
 2618 	// sweeps the whole battlefield for its own (non-targeted) primitive.
 2619 	if effect == "untap_dynamic_x_target_lands" {
 2620 		return gs.executeUntapDynamicXTargetLands(targets)
 2621 	}
 2622 
 2623 	// conditional_destroy primitive (ticket
 2624 	// engine.auto-conditional-destroy-fad25c5f76): "destroy target
 2625 	// permanent unless <condition>." Dispatches before the dynamic-amount
 2626 	// resolvers below since it needs no X/count resolution of its own.
 2627 	if effect == "destroy_target_unless_life_at_least" {
 2628 		return gs.executeDestroyTargetUnlessLifeAtLeast(targets, effectValue)
 2629 	}
 2630 
 2631 	// destroy_unless_damage_to_controller primitive (ticket
 2632 	// engine.auto-destroy-unless-damage-to-controller-1b18eeccd8, Dwarven
 2633 	// Driller class): "Destroy target permanent unless its controller has ~
 2634 	// deal N damage to them." Dwarven Driller's "2 damage" is a fixed
 2635 	// amount, so this dispatches before the dynamic-amount resolvers below,
 2636 	// same as the sibling check just above.
 2637 	if effect == "destroy_unless_damage_to_controller" {
 2638 		return gs.executeDestroyUnlessDamageToController(targets, effectValue, source)
 2639 	}
 2640 
 2641 	// destroy_target_blocking_source primitive (ticket
 2642 	// engine.auto-destroy-target-blocking-source-8c68a1acdf, Knight of Dusk
 2643 	// class): "Destroy target creature blocking this creature." Needs the
 2644 	// ability's own source (Rule 509.1h blocking state — Card.Blocking +
```
