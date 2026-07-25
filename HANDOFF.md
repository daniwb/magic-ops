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
4. **Suite-Rot auf main**: `go test ./cardfns/` hat ~15 vorbestehende Failures
   (Cross-Test-Pollution durch package-globale Maps, z.B.
   `lifeGainPreventionRules` — kartenID-gekeyt, nie pro Game gescoped; mit
   jüngeren vbatch-Batches eingezogen). Der 2h-Regression-Cron sollte das
   sehen — prüfen, warum die Batches trotzdem gemerged wurden. Fix-Idee:
   Rules pro GameState scopen statt package-global.
