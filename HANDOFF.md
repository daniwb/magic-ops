# Handoff — Record-First-Umstellung (openmagic phase 2/3)

*2026-07-25, aus der openmagic-Session (siehe openmagic `docs/migration-plan.md`).*

## Bereits erledigt (dieses Repo)
- `scripts/dispatcher-worker-real.sh`: Worker-Prompt hat jetzt **STEP 0 —
  RECORD FIRST** (Datensatz in `backend/data/carddb/` statt Handler, wenn alle
  Fähigkeiten Shapes sind; `SHAPE_DEMAND` analog `MISSING_PRIMITIVE`). Der
  Shape-Katalog (`scripts/skills/shape-catalog.md`, aus dem openmagic-Clone)
  wird vor dem Primitive-Katalog in den Prompt eingebettet. Fast-Gate testet
  zusätzlich `./cards/` (Record-Tests); Vollständigkeits-Gate zählt
  `*_record_test.go` als erledigte Karte.

## Offen (bewusst NICHT verdrahtet)
1. **Snapshot-Refresh-Cron**: `scripts/snapshot-carddb.sh` (openmagic) einmal
   täglich im Live-Repo laufen lassen. Empfehlung: NICHT auto-committen —
   der `git diff backend/data/carddb` ist das Review-Artefakt für
   Parser-Änderungen. Cron: laufen lassen, bei Diff mailen/loggen, Mensch
   committet. (Manuell/verified-Records überleben den Re-Run — der Snapshot
   preserved sie.)
2. **Collapse-Ticket-Injektion**: `backend/tools/collapseaudit -json` (openmagic)
   liefert kollabierbare Handler samt Record-Skizze. Als Card-Tickets in den
   Dispatcher einspeisen (Titel-Konvention frei, z.B. `COLLAPSE: <Card>`);
   Merge-Gate: bestehender Test bleibt grün, Handler-Datei gelöscht.
   Aktuell 1 Kandidat (Patron of the Arts). Dateien mit
   MISSING_PRIMITIVE-Annotationen sind ausgeschlossen (Demand-Doku).
3. **Daily-Report-Anbindung**: `backend/tools/report -db data/carddb
   -dispdb services/dispatcher/v4/dispatcher.db` (openmagic) liefert die
   Tier-/Playability-Zahlen (aktuell: 68.8% playable). In den täglichen
   Report/Mail aufnehmen — die Zahl ist die Fortschrittsmetrik der Factory.
4. **Suite-Rot auf main**: ERLEDIGT (openmagic b8606744) — alle 15 Failures
   gefixt (Kumena an neue TapOther-Enforcement angepasst; Life-Gain- und
   Combat-Authority-Rules pro GameState gescoped; CreepyDoll war ein
   Test-Bug). Suite ist grün (5× verifiziert, exit 0). NOCH prüfen: warum
   der 2h-Regression-Cron die Batches gemerged hat, die das Rot einführten
   — und beim Bauen neuer lib_global_*-Regeln gilt ab jetzt: Rule-Stores
   IMMER pro GameState keyen, nie package-global flach (Muster:
   lib_global_life_gain_prevention.go nach dem Fix).

## Kosten-Optimierung Worker (2026-07-25, zweiter Commit)
Gemessene Kosten-Anatomie (3 E2E-Läufe): Park ~110k Token / Build ~2.08M über
17 Turns. Umgesetzt in `dispatcher-worker-real.sh`:
1. **Cache-Layout**: statischer Prefix (Kataloge+Regeln) zuerst, Ticket nur im
   Schwanz, kein sed im Prefix mehr → aufeinanderfolgende Jobs LESEN den
   Prompt-Cache statt ihn je Job neu zu schreiben.
2. **Signatur-Index** statt Voll-Katalog (~27k statt ~52k Token); volle
   Einträge per Grep aus `scripts/skills/primitive-catalog.md` (Regel-1-
   Ausnahme: Docs + `go doc` erlaubt, Go-Quelltext bleibt tabu). Vor
   MISSING_PRIMITIVE ist Grep im Voll-Katalog PFLICHT (Krark's-Thumb-Klasse).
   `CATALOG_FULL=1` = altes Verhalten.
3. **Turn-Diät**: Test-Cheat-Sheet im Prompt (killt go-doc-Runden); kein
   `go build ./...`/Vollsuite durch den Worker (Harness gated ohnehin), max
   ein fokussierter Test + ein Fix-Rerun, im Vordergrund.
4. **Mirror+GOCACHE**: Erst-Clone via lokalem Bare-Mirror (`--reference`,
   origin bleibt GitHub); GOCACHE auf geteiltes persistentes Verzeichnis.

NOCH OFFEN (optional): GPU-Embedding-Ranker (lokales sentence-transformers)
zur Auswahl der pro Ticket INLINE eingebetteten Katalog-Einträge — nur als
Ranking über dem Index, NIE als einziger Zugriffspfad (Recall-Risiko =
systematische False-Parks). Gleiche Behandlung für den vocab-batch-Prompt
(`dispatcher-vocab-batch.sh`) steht ebenfalls noch aus.

### Verifikation Kosten-Optimierung (gemessen, 2 Job-Paare)
- **Cross-Job-Prompt-Cache: FUNKTIONIERT** nach dem --append-system-prompt-Fix.
  Erster Turn pro Job: vorher cw=62.9k/cr=23.7k → nachher cw=0–3.3k/cr=83–86.5k.
  (Rest-Invalidierung: der CLI-eigene System-Kontext enthält die
  Recent-Commits-Liste — ein Push nach main invalidiert den Prefix einmalig.)
- **Token-Accounting ehrlich**: tokens-Feld im Dispatcher war Last-Turn-only
  (Build als "107k" gemeldet, real 2.09M). Jetzt .modelUsage-Summe. Historische
  tokens-Werte in der DB entsprechend als Untergrenzen lesen.
- **Park-Kosten** (gewichtet ~ cw×1.25 + cr×0.1 + out): sauberer Park jetzt
  ~41k effektiv (vorher ~110k) — trotz Pflicht-Grep im Voll-Katalog.
- **WATCH-ITEM**: Ein Park-Versuch (Ticket #33, Attempt 1) verbrannte 16 Turns
  ohne Datei und ohne gültige MISSING_PRIMITIVE-Zeile → Gate wertete
  "keine Dateien" → teurer Zweitversuch. Prompt-Compliance der Park-Ausgabe
  beobachten; ggf. Regel 5 im Prompt schärfen (Zeilen MÜSSEN exakt so
  ausgegeben werden, auch wenn keine Karte gebaut wird).

## Lokale-GPU-Triage — Evaluation abgeschlossen (2026-07-27)
Ergebnis + Empfehlung: `reports/ollama-triage-summary-2026-07-27.md`.
Kurzfassung: kein lokales Modell darf autonom parken (Präzision zu niedrig);
validiert sind (1) Record-Shaped-Routing, (2) deterministischer
Stale-Park-Grep-Sweep (1 Fund: Dispelling Exhale), (3) LOCAL-TRIAGE-
Annotationen via `qwen3.6:27b think` (80% Präzision) mit Sonnet-Precheck.
Werkzeug: `scripts/ollama-triage.sh` (read-only, memory-gekapselt).
Ollama auf 192.168.1.15 auf 0.32.4 aktualisiert (qwen3.6-GPU-Support).

## Lokale GPU-Lanes 2–4 verdrahtet (2026-07-27, nachmittags)
- **Kill-Switch:** Datei `LOCAL_GPU_OFF` (Repo-Root magic-ops) stoppt ALLE
  lokalen GPU-Skripte. Toggle im Dispatcher-GUI ("GPU: AN/AUS 🔇", Endpoint
  `/local-gpu?set=on|off`) — Home-Office-Modus.
- **`scripts/local-triage-queue.sh [N]`** (Streams 2+3): annotiert todo-Karten-
  Tickets via qwen3.6:27b+think. Record-shaped → Titel-Prefix `DSL-RECORD:`
  (Routing-Hook, Worker-STEP-0 fängt Fehltags); MISSING (grep-überlebend) →
  LOCAL-TRIAGE-Hinweis in descr (parkt NIE). Sidecar-Tabelle `local_triage`
  in der Dispatcher-DB macht Läufe idempotent.
- **`scripts/local-record-builder.sh [N]`** (Stream 4): schreibt AbilityDSL-
  Records für record-getaggte Tickets, Gate = recordedit+Linter+Shape-Tests
  im Scratch-Clone (/tmp/work/record-builder); GRÜN → Kandidat in
  `record-candidates/pending/ticket-N.json` (Review nötig, KEIN Auto-Merge).
- Betrieb: manuell oder Cron/Loop; noch NICHT automatisch geschedult.
- ACHTUNG Ops: `pkill -f dispatcher-v4` tötet auch die tmux-Wrapper (Server!)
  — 2026-07-27 passiert, riss ollama-w3 mit. Recovery: 
  `dispatcher-orchestrator-launch.sh` (idempotent) + 
  `tmux new-session -d -s ollama-w3 "bash scripts/archive/dispatcher-worker-ollama.sh >> /tmp/ollama-w3.log 2>&1"`.
  Besser: gezielt `pkill -f "v4/dispatcher-v4$"` NIE ohne Anker verwenden.
