# Operator-Projekte (active-session work) — Stand 2026-08-09

Dani 2026-08-09: "we need things that are projects for active sessions."
Diese Liste = Miss-Massen, die als EIN fokussiertes Projekt (Operator-Session
oder Batch-Agent-Runde) gelöst gehören — NICHT als 45-Miss-Fleet-Tickets.
Zahlen = LIVE demand scan (reparse.py über review-pile, 4322 Karten / 7118
Misses, /tmp/orch/demand-latest.txt). KPI-Tracking: state/miss-history.jsonl
(miss-tracker.sh cron :13) → Dashboard "corpus misses (▼N/24h)".

| # | Projekt | Misses | Kern |
|---|---------|--------|------|
| 1 | **Parser-Spine: Subjekt-/Antezedens-Auflösung** | **2147** (verb_unmapped:? = 30% ALLER Misses) | reparse.py kann "it/that/each/you"-Klauseln + if-Konditionale nicht auflösen. → EIGENES TODO: openmagic docs/parser-spine-refactor.md — Dani will das in einer frischen Session machen. |
| 2 | static_unmapped Familie (continuous effects) | 486 (+131 static_mod, +97 static_conditional, +94 static_cost_mod, +59 static_subject) | Statics-Schema verbreitern; die geparkten Mega-Tickets (2498, 2536, 2538, 2539…) sind die Arbeitsliste. |
| 3 | kind UNCLASSIFIED Triage | 395 | classify.py-Runde: "Suspend X—…" u.ä. erst korrekt klassifizieren — viele fallen danach in existierende Shapes. Billig, rein Python. |
| 4 | keyword_unsupported Batch | 313 | Morph/Disguise (face-down-Infra existiert seit CastMorph-Fix), Cumulative Upkeep, Affinity… Batch-Agent-Runde wie engine-batch-0808. |
| 5 | exile-until-leaves + exile-Breite | 167 | Abdel-Adrian-Muster: verknüpfte Zonen ("until ~ leaves"). Ein Primitive + Parser-Emission. |
| 6 | replacement_would Framework | 116 (+52 replacement_as) | "If you would X, instead Y" — ein Replacement-Schema, viele Karten. |
| 7 | Modal/Alt-Cost Gruppe | 81 modal_option + 86 alt_cost + 69 cost_declaration | choose_option-Primitive existiert; Parser-Emission + alt-cost-Deklaration. |
| 8 | Engine-Runde 3 (Menü in memory pipeline_workflows_lane) | ~50-100 | shuffle-self, per-source damage tracker, dynamic_boost_entered_this_turn … |

Faustregel: Projekte 1-3 sind PARSER-Arbeit (Python, deterministisch, $0-Iteration,
kein Fleet-Budget). 4-8 sind Engine+Parser-Mischungen → Batch-Agent-Pattern
(mehrere parallele Subagents, EIN Gate, EIN Push — validiert 2026-08-08).

Fleet-Tickets bleiben für den Tail (<50 Misses/Shape) — Prioritäten werden
stündlich ∝ erwartetem Unlock gesetzt (miss-tracker.sh Re-Rank 10-55,
Circle-Requeues 60 gewinnen weiter).
