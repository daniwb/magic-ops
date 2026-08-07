# Staged Pipeline-Workflows (Map / Engine / Handler)

Stand 2026-08-07. Idee (Dani): "Less thinking, more doing" — die Ticket-Arbeit
ist stereotyp, also macht die **Harness die deterministischen Schritte** und
das Modell bekommt **einen fokussierten Call** statt einer agentischen
100-Turn-Session. Jede Stufe ist Gate-verifiziert; Eskalation nur bei echtem
Scheitern (Exit 2). Messwerte unten aus der Validierungsserie vom 2026-08-07.

Skripte: `magic-ops/scripts/{map,engine,handler}-pipeline.sh` + `*-pack.py`,
gemeinsamer Applier `map-pipeline-apply.py`, Region-Nachladung
`pipeline-fetch-regions.py`.

---

## 1. MAP-Pipeline (`map-pipeline.sh TICKET [--push]`)

Ziel: ein REPARSE-MAP-Ticket (Miss-Shape) per Parser-/Converter-Patch mappen.

| # | Schritt | Wer |
|---|---------|-----|
| 1 | Shape + Ticket aus Dispatcher-DB extrahieren | Skript (pack.py) |
| 2 | Live-Beispiele: Review-Pile scannen, bis 5 Karten die JETZT mit diesem Shape missen (Oracle + exakte Misses) | Skript |
| 3 | Code-Regionen per Shape-Token greppen (slotparse/reparse/converter) + Knowledge-Service-Hits | Skript + kb :4103 |
| 4 | **Mapping-Regel entscheiden** (oder Park: NEEDS_PRIMITIVE / SEMANTIC_GAP / …) | **Modell** |
| 5 | Patch als SEARCH/REPLACE-Blöcke | **Modell** |
| 6 | Apply (exact-match, game/-Guard) + Gate: build, Vocab/Shape-Tests, Review-Pile-Delta (Shape-Zähler, Fallback total-misses bei Top-40-blinden kleinen Shapes) | Skript |
| 7 | Commit + Branch `reparse/task-N` push → Integrator landet | Skript |

Gate-Metrik: Shape-Instanzen sinken ODER total-misses sinken (isolierter Clone).
Verbote: `backend/game/` (Auto-Park im Applier).

## 2. ENGINE-Pipeline (`engine-pipeline.sh TICKET [--push]`)

Ziel: EIN kleines Primitiv aus einem Park (`missing_prim`) bauen.
Input-Ticket: blocked mit missing_prim (Park aus Map-Lane oder Map-Pipeline).

| # | Schritt | Wer |
|---|---------|-----|
| 1 | Primitiv-Name + Park-REASON (aus Pipeline-Reply-Dateien) + Beispielkarten laden | Skript (pack.py) |
| 2 | Executor-Regionen: Tokens aus Primitiv-Name + Backtick-Bezeichnern der REASON über game/cards-Dateien greppen, gerankt | Skript |
| 3 | Vorbild suchen (kb /find) + Shape-Test-Template (head eines aktuellen shape_*_test.go) beilegen | Skript + kb |
| 4 | **Kleinsten Engine-Change entscheiden** (oder Park: FRAMEWORK/AMBIGUOUS — Framework-Arbeit bleibt bei manuellen Runden) | **Modell** |
| 5 | Edits (SEARCH/REPLACE, game/ ERLAUBT via --allow-game) + NEUE Testdatei (NEWFILE) | **Modell** |
| 6 | Apply + Gate: build, Vocab/Shape/Combat-Tests, **neuer +func Test im Diff Pflicht** (nach `git add`! untracked-Falle), **volle Sharded-Suite** | Skript |
| 7 | Commit + Branch `reparse/engine-task-N` push → Integrator | Skript |

## 3. HANDLER-Pipeline (`handler-pipeline.sh TICKET [--push]`)

Ziel: EIN Karten-Handler (cardfns) + Behavior-Test. Stereotypster Tier.

| # | Schritt | Wer |
|---|---------|-----|
| 1 | Karte aus Ticket-Titel, Oracle-Text aus carddb | Skript (pack.py) |
| 2 | Nächster existierender Handler via kb /similar → **komplette Datei + deren Test als Template** in den Pack | Skript + kb |
| 3 | Helper-Kandidaten via kb /find (Oracle-Text als Query) | Skript + kb |
| 4 | **Handler entwerfen** (oder Park: präziser kebab-case-Primitive-Name) | **Modell** |
| 5 | Zwei NEWFILE-Blöcke: `cardfns/<Name>.go` + `<Name>_test.go` | **Modell** |
| 6 | Apply + Gate: build, neuer Test im Diff, volle Sharded-Suite; **bei rot: Bugfix-Runden auf dem STEHENDEN Tree** (eigene Dateien + exakter Fehler → nur Korrektur-Blöcke, bis BUGFIX_MAX=3, NEWFILE darf überschreiben) | Skript (+Modell für Fixes) |
| 7 | Commit + Branch `reparse/handler-task-N` push → Integrator | Skript |

game/ bleibt gesperrt (Handler nutzen Primitives/Helpers; fehlt einer → Park).

---

## Gemeinsame Mechanik

- **Exit-Codes** (alle drei): 0 = Gate grün (+Push), 4 = Park (Erfolg! Demand
  wird gefiled), 2 = 2 Model-Calls erschöpft → **eskalieren**, 1 = Infra.
- **Modell-Modi**:
  - Sonnet: read-only-agentisch (Read/Grep/Glob, 25 Turns, Emit-Pflicht am
    Ende) — Mutation bleibt IMMER blockbasiert bei der Harness.
  - Lokal (PIPE_BASE_URL=Shim :4102): Single-Shot ohne Tools via direktem
    /v1/messages-curl (SSE-Parsing!), @@@-Marker statt <<< (llama-server-
    Parser 500t auf <<<), + Bugfix-Runden. Claude-CLI ist lokal unbrauchbar
    (meldet interne Tools an → gpt-oss antwortet mit tool_calls + leerem
    content).
- **NEED-Runde**: Modell darf 1× fehlende Regionen anfordern
  (`NEED: <pfad|symbol>`), `pipeline-fetch-regions.py` liefert nach.
- **Serieller GPU-Betrieb** (Dani): NIE parallel zur rl1-Lane auf dem
  llama-server — Test/Pipeline-Läufe an der Ticket-Grenze (cycle done) starten,
  Lane pausieren, danach Launcher wieder starten.

## Eskalationsleiter (Kostenordnung)

1. **Lokal-Pipeline** (Handler: single-shot+bugfix) — $0, ~4–8 min
2. **Lokal-agentisch** (rl1-Worker) — $0, ~20–25 min, heute 4/4 grün (auch Map!)
3. **Sonnet-Pipeline** — ~0,3–1M Tokens, ~5–10 min
4. **Sonnet-agentisch** (Fleet-Worker) — ~2,7M median, Reserve für echte Exploration

Jede Stufe feuert nur bei Gate-verifiziertem Scheitern der darunterliegenden.

## Messwerte Validierungsserie 2026-08-07 (Sonnet, wenn nicht anders vermerkt)

| Lauf | Ergebnis | Tokens (roh) | Dauer |
|------|----------|--------------|-------|
| Map #2485 Triage | Park each_player_discard (verifiziert korrekt) | ~30k | 63 s |
| Map #2482/#2515 Triage | Parks mit Code-verifizierten Gap-Listen | 30–40k / ~0,9M (agentisch) | 35 s–3 min |
| Engine #2485 Build | GRÜN — Executor + Test + volle Suite | ~1,0M | ~10 min |
| Map #2485 nach Primitiv | GRÜN — total-misses −8 | ~0,57M | ~9 min |
| Handler #2192 | GRÜN — Handler + Test, 1. Versuch | ~0,58M | ~9 min |
| Handler #2193 lokal | Exit 2 (Blöcke applizieren, Go-Compile rot) | $0 | ~9 min |
| **Kreislauf Map→Engine→Map gesamt** | Park→Primitiv→Grün | **~1,6M** | ~20 min |
| Vergleich: emergente Engine-Arbeit agentisch (#2457) | grün | 22,5M | Stunden |

## Offene Punkte

- Lane-Integration: Pipelines claimen via Dispatcher `/claim` (Lease =
  Dedup-Gate + Dashboard-Sichtbarkeit); Ticket-Erzeugung + Selbst-Claim für
  Engine-Demands aus Parks (Dani Schritt-3-Idee); Namens-Normalisierung beim
  Demand-Dedup (Map-Parks ≠ cardfns-Helper-Namensraum — Brimaz-Lektion!).
- Bugfix-Runden in Map-/Engine-Pipeline nachziehen (aktuell nur Handler).
- Lokale Pipeline: Go-Compile-Qualität von gpt-oss single-shot ist die
  Grenze; Stand heute bleibt lokal-agentisch der Grün-Pfad der lokalen Lane.
