# Factory NG legacy backlog reconciliation

Read-only classification; it does not alter dispatcher state.

- Database: `/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db`
- Snapshot: `sha256:bb3e3d4f986b48ca6e8f8962cb2a50830a09b9db79ed8590d0dc69a7681f0aee`
- Tickets reconciled: 5310

## Exact classification totals

| Classification | Tickets |
|---|---:|
| blocked_by_capability | 106 |
| duplicate | 164 |
| legacy_unverified | 1003 |
| mixed_or_ambiguous | 24 |
| stale | 1 |
| terminal | 4012 |

## Candidates requiring fresh TicketSpec compilation

| Legacy ID | Classification | Title | Reason |
|---:|---|---|---|
| 3654 | mixed_or_ambiguous | REPARSE-ENGINE: verb_unmapped:?/if — class round (unlock 395) | legacy class-round assignment needs TicketSpec split |
| 3655 | mixed_or_ambiguous | REPARSE-ENGINE: verb_unmapped:?/target — class round (unlock 408) | legacy class-round assignment needs TicketSpec split |
| 3656 | mixed_or_ambiguous | REPARSE-ENGINE: verb_unmapped:damage — class round (unlock 356) | legacy class-round assignment needs TicketSpec split |
| 3657 | mixed_or_ambiguous | REPARSE-ENGINE: verb_unmapped:pump — class round (unlock 351) | legacy class-round assignment needs TicketSpec split |
| 3658 | mixed_or_ambiguous | REPARSE-ENGINE: verb_unmapped:grant_eot — class round (unlock 326) | legacy class-round assignment needs TicketSpec split |
| 3860 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (103 cards, 104 misses): cost_unmapped:reveal, condition_unsupported:cast_manner, loyalty_body:look_top, verb_unmapped:lose_life, condition_unsup | legacy ticket combines several independently testable shape families |
| 3861 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (125 cards, 125 misses): loyalty_body:create_token, verb_unmapped:exchange, verb_unmapped:goad, verb_unmapped:mill, cost_unmapped:remove_counters | legacy ticket combines several independently testable shape families |
| 3862 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (163 cards, 164 misses): cost_unmapped:tap_others, verb_unmapped:venture, event_unsupported:becomes_targeted, verb_unmapped:p_discard, verb_unmap | legacy ticket combines several independently testable shape families |
| 3863 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (79 cards, 80 misses): verb_unmapped:switch_pt, kind_unsupported:deck_rule, cost_unmapped:return_to_hand, verb_unmapped:draw_eq, loyalty_body:c | legacy ticket combines several independently testable shape families |
| 3864 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (86 cards, 90 misses): loyalty_body:reveal, loyalty_body:exile, verb_unmapped:p_discard_hand, loyalty_body:damage, event_unsupported:roll_die | legacy ticket combines several independently testable shape families |
| 3967 | stale | REPARSE-SWEEP: 1 small shapes (14 cards, 15 misses): loyalty_body:choose | unchanged todo for more than seven days; recompile from ground truth |
| 3968 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (108 cards, 109 misses): cost_unmapped:remove_counters, cost_unmapped:reveal, condition_unsupported:cast_manner, loyalty_body:look_top, verb_unma | legacy ticket combines several independently testable shape families |
| 3969 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (128 cards, 128 misses): verb_unmapped:remove_counter, loyalty_body:create_token, verb_unmapped:exchange, verb_unmapped:goad, verb_unmapped:mill | legacy ticket combines several independently testable shape families |
| 3970 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (167 cards, 169 misses): cost_unmapped:tap_others, verb_unmapped:venture, event_unsupported:becomes_targeted, verb_unmapped:regenerate, verb_unma | legacy ticket combines several independently testable shape families |
| 3971 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (81 cards, 83 misses): event_unsupported:roll_die, verb_unmapped:switch_pt, kind_unsupported:deck_rule, cost_unmapped:return_to_hand, verb_unma | legacy ticket combines several independently testable shape families |
| 3972 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (89 cards, 91 misses): condition_unsupported:control_subtype, loyalty_body:reveal, loyalty_body:exile, verb_unmapped:p_discard_hand, loyalty_bo | legacy ticket combines several independently testable shape families |
| 4667 | mixed_or_ambiguous | REPARSE-SWEEP: 2 small shapes (29 cards, 30 misses): loyalty_body:untap, loyalty_body:choose | legacy ticket combines several independently testable shape families |
| 4668 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (105 cards, 109 misses): cost_unmapped:remove_counters, cost_unmapped:reveal, condition_unsupported:cast_manner, loyalty_body:look_top, loyalty_b | legacy ticket combines several independently testable shape families |
| 4669 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (92 cards, 93 misses): verb_unmapped:lose_life, condition_unsupported:control_subtype, loyalty_body:reveal, loyalty_body:exile, verb_unmapped:p | legacy ticket combines several independently testable shape families |
| 4909 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (109 cards, 110 misses): cost_unmapped:remove_counters, cost_unmapped:reveal, condition_unsupported:cast_manner, verb_unmapped:p_discard_hand, lo | legacy ticket combines several independently testable shape families |
| 4910 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (129 cards, 129 misses): verb_unmapped:remove_counter, loyalty_body:create_token, verb_unmapped:exchange, verb_unmapped:goad, verb_unmapped:mill | legacy ticket combines several independently testable shape families |
| 4911 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (173 cards, 175 misses): cost_unmapped:tap_others, verb_unmapped:venture, event_unsupported:becomes_targeted, verb_unmapped:p_discard, verb_unmap | legacy ticket combines several independently testable shape families |
| 4912 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (82 cards, 84 misses): event_unsupported:roll_die, verb_unmapped:switch_pt, kind_unsupported:deck_rule, verb_unmapped:draw_eq, cost_unmapped:re | legacy ticket combines several independently testable shape families |
| 4913 | mixed_or_ambiguous | REPARSE-SWEEP: 5 small shapes (93 cards, 95 misses): loyalty_body:damage, verb_unmapped:lose_life, condition_unsupported:control_subtype, loyalty_body:reveal, loyalty_body:e | legacy ticket combines several independently testable shape families |
| 5310 | mixed_or_ambiguous | REPARSE-MAP: static_conditional / can't be blocked (45 misses, 45 cards) | legacy ticket combines several independently testable shape families |

No legacy row is directly dispatched by this report. `ready` means only that no block is recorded; a Factory NG producer must refresh evidence, split mixed scopes, and deduplicate before a TicketSpec reaches a worker.
