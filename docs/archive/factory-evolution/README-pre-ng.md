# magic-ops — Operational Pipeline (Dispatcher / Orchestrator)

> Archived 2026-09-01 from `README.md`. Historical pre-NG description only;
> see [`../../../README.md`](../../../README.md) for the current project.

Betriebs-Tooling der Karten-Bau-Pipeline, getrennt vom Spiel-Repo (openmagic).
Die **Skills** bleiben bewusst in openmagic (`scripts/skills/`), weil die Worker
sie über `git clone` erhalten — sie gehören ins Spiel-Repo, nicht hierher.

## Inhalt
- `scripts/`   Orchestrator + Card-Worker + VOCAB-Batch + Pace-Gate (+ archive/)
- `services/`  Dispatcher (Go-Quelle; Binary + *.db sind gitignored, Runtime)

## Live-Verknüpfung
Die Live-Pfade sind Symlinks hierher, damit absolute Pfade (Cron, Orchestrator)
unverändert funktionieren:
- `/opt/development/magic-claude/scripts`  -> `magic-ops/scripts`
- `/opt/development/magic-claude/services` -> `magic-ops/services`
