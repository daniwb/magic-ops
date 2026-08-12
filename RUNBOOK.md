# RUNBOOK — Magic reparse factory (emergency reference)
Updated 2026-08-04. In an emergency: point a fresh Claude session at THIS file.

## The system in one paragraph
Deterministic parser (scripts/paragraph/reparse.py in /opt/development/test/openmagic)
turns MTGJSON corpus text into card records (backend/data/carddb/*.json).
Workers (LLM agents) improve the parser or write per-card Go handlers, push
branches; an integrator cron lands them through full gates and deploys.
Coverage_planner.py decides what is worth building. Cards the schema can't
express get hand-written handlers (backend/cardfns/).

## Components & where they run
| What | Where | Restart |
|---|---|---|
| Dispatcher v4 (:9999, tickets) | tmux `dispatcher:disp` | /tmp/orch/launch-dispatcher.sh (DB: magic-ops/services/dispatcher/v4/dispatcher.db) |
| Worker r1 (Sonnet, map tier) | tmux `dispatcher:r1` | /tmp/orch/launch-r1.sh |
| Worker ro1 (GLM-5.2 cloud, $0, map) | tmux `dispatcher:ro1` | /tmp/orch/launch-ro1.sh |
| Worker rl1 (local/llmproxy, handler tier) | tmux `dispatcher:rl1` | RL1_MODEL=qwen3-coder:30b /tmp/orch/launch-rl1.sh |
| Anthropic→OpenAI shim (:4102) | tmux `dispatcher:shim` | python3 magic-ops/anthropic-openai-shim.py >> /tmp/orch/shim.log (traffic recorder: /tmp/orch/shim-log/traffic.jsonl) |
| Card-knowledge service (:4103) | tmux `dispatcher:kb` | python3 magic-ops/scripts/card-knowledge-service.py >> /tmp/orch/kb.log (find/similar/caps/reindex; index from openmagic, /reindex after landings; /caps?name=X = deterministic engine-readiness -> map-lane fail-fast park; harness auto-parks map branches touching backend/game/) |
| Pipeline-Workflows (map/engine/handler) | Doku | docs/pipeline-workflows.md — staged Ticket-Verarbeitung, Eskalationsleiter, Messwerte 2026-08-07 |
| Integrator (lands branches) | cron */15 | magic-ops/scripts/integrator-lite.sh (stop: touch magic-ops/INTEGRATOR_LITE_OFF) |
| Regression check | cron 0 */2 | red main safety net |
| Daily report mail | cron 06:30 | magic-new/scripts/kanboard-daily-report.sh |
| Live game backend | systemd magic-backend | binary /opt/development/magic-new/bin/magic-api-server (built from openmagic backend/api) |

NOTE: /tmp/orch/launch-*.sh do NOT survive reboot — restore via
magic-ops/launchers/restore-launchers.sh (canonical copies live in git
since 2026-08-06).

## Repos
- /opt/development/test/openmagic  = THE repo (parser, engine, carddb, skills). Push origin main.
- /opt/development/magic-new       = live checkout (ff-only from origin) + service binary.
- /opt/development/magic-ops       = this infra repo (scripts, dispatcher, shim, launchers). Remote: github daniwb/magic-ops (push after commits!).

## The loop
fleet parks NEEDS_PRIMITIVE w/ spec → session builds primitive (registry_*.go
init file + shape_<topic>_test.go + emitter) → requeue ticket
(localhost:9999/action?do=requeue&id=N) → fleet maps it → integrator lands.

## Gates (never bypass)
build (backend: go build ./...) + fast gate (go test ./cards/ -run
'TestVocabulary|TestV2|TestShape_') + FULL sharded suite
(bash scripts/test-cards-sharded.sh, ~3min). Wave = reparse.py --flip-batch +
--import-corpus (deterministic, no tokens). Deploy = ff magic-new, go build
-o magic-new/bin/magic-api-server ./api (from magic-new/backend!), restart.

## Known failure modes & fixes
- "tree dirty — skip run" in integrator log: uncommitted files in openmagic
  block ALL landings. git status; commit or checkout them.
- Suite FAIL swallowed by `| tail`: NEVER pipe test runs in && chains.
- Worker claim-churn "git sync failed" every 30s: dead cwd. Kill window,
  rm -rf /tmp/work/disp-<w>, relaunch via its launch script.
- pkill: patterns match YOUR OWN command line and the TMUX SERVER's.
  Always split patterns ("disp-r""l1") and prefer kill-by-PID.
- Ollama cloud quota (ro1): auto-parks, probes every 15min, self-resumes.
- llmproxy (llm.k.ezq.ch): keyless OK, but a WRONG Bearer key is rejected;
  no /v1/responses (that's why litellm failed → we use our own shim).
- Local model doesn't commit → auto-commit now in worker; if gate says
  "weder eligibility- noch shape-delta" on a handler ticket, check clone for
  uncommitted work first.
- Watch a local worker's conversation:
  python3 magic-ops/scripts/watch-local-ai.py rl1 -n 40   (or -f)
- Stale review list entries: verify with git rev-list --count
  origin/main..origin/<branch> before re-merging.
- gpt-oss via llmproxy 400 "failed to parse grammar": llama-server chokes on
  exotic JSON-Schema keywords in tool defs; the shim's sanitize_schema()
  strips them — if it reappears, a new tool schema feature slipped through.
- Worker↔model debugging: /tmp/orch/shim-log/traffic.jsonl (one line per
  exchange), last-exchange.json (full payload), error-*.json (failures).
- gen_fleet_tasks rewrites reparse-tasks.jsonl but dispatcher ingests from a
  stored offset: reset via sqlite meta k=backlog_offset v=0, then
  /action?do=ingest&n=300.



## Usage budget & daily pacing (canonical: lib-pace-gate.sh, Variante C 2026-07-27)
The weekly budget unlocks in 7 DAILY STEPS at the 20:00-CH boundary, anchored
to the REAL quota window (seven_day.resets_at - 7d): day1 14%, day2 29%,
day3 43%, day4 57%, day5 71%, day6 86%, day7 100%. Over the current step ->
pause until the next 20:00 boundary. 5h window is a hard ceiling (transient
pause only). Implementation: magic-ops/scripts/lib-pace-gate.sh :: pace_ok()
— sourced by pipeline-lane.sh AND the fleet workers. PACE_DISABLE=1 for $0
lanes (lp1/ro1). Fail-open only after 30min without usage data (endpoint
rate-limits under multi-lane polling; the lib caches with 180s TTL).

## Session startup & operator lock (multi-session guardrail)
Every Claude session MUST at start: run
magic-ops/scripts/session-health-check.sh and inspect /tmp/orch/operator.lock.
Lock free/stale(>4h) -> take it, act as operator. Lock held by another live
session -> OBSERVER MODE: monitors + reporting ONLY, zero mutations (no
commits, pushes, restarts, ticket ops, deploys). Protocol details: memory
file session_startup_protocol.md.

## Session monitors (NOT persistent — they die with the Claude session!)
The interactive session usually runs these watchers via its Monitor tool.
A fresh session should re-arm them (they are conveniences, not infra —
the crons above are the real safety net):
- Fleet results:  tail -n0 -f /tmp/orch/reparse-r1.log /tmp/orch/reparse-ro1.log
    | grep --line-buffered -E "ticket #|gate|parked|gepusht|rot|Fehler"
- Local lane:     same on /tmp/orch/reparse-rl1.log
- After each worker "gepusht" event: probe merge cleanliness
    git merge-tree --write-tree origin/main origin/reparse/<branch>
    (exit 0 = cron will land it; exit 1 = hand-merge job for the session)
- Optional one-shots: 45-min ticket timers, model-appearing-on-a-box
  watchers — recreate ad hoc.
Worker turn/token accounting: /tmp/disp-<w>-turns.log, /tmp/disp-<w>-tokens,
last model output: /tmp/disp-<w>-last-result.txt.

## Dashboards / status
- localhost:9999/dashboard (tickets, pilestats, buildplan, carddb)
- Queue: sqlite3 dispatcher.db "select state,count(*) from tickets group by state"
- DB count: python one-liner over backend/data/carddb/*.json status fields.

## Memory (Claude sessions)
~/.claude/projects/-opt-development-magic-new/memory/ — start with MEMORY.md;
fleet_operating_model.md + local_395_lane.md hold the operating decisions.

## Quality-Ratchet + Gates (phase.rs adoption, 2026-08-10)
- prompts/quality-gates.md — 4 Gates (Premise-Verify, 5-Grep-Existenz,
  Honest-Miss, Discriminating-Test), automatisch in JEDEN Worker-System-
  Prompt eingehängt (dispatcher-worker-real.sh + -reparse.sh, STATIC_FILE-
  Block). Laufende Worker sehen es erst nach inner-kill/Neustart.
- scripts/quality-ratchet.sh — Cron 03:15: primitive_inventory + swallow_audit
  über magic-new; Verschlechterung (inert_live/swallow steigt) -> ALERT-Mail
  an dani@, Baseline bleibt (Alert wiederholt sich); Verbesserung -> Baseline
  update. State: state/quality-ratchet.json. Log: /tmp/orch/quality-ratchet.log
- scripts/fresh-review.sh <range> — Fresh-Context-Reviewer (Sonnet, sieht NUR
  Diff+Standards), SHADOW MODE: loggt nach /tmp/orch/review-shadow.log,
  blockt nichts. Geplante Integration: integrator-lite nach Batch-Merge
  (log-only), später blocking. Hintergrund: docs/phase-rs-factory-analysis.md
  (magic-new).

## Fleet-Stand 2026-08-10 Abend (class-round era)
- Worker: tmux dispatcher:r1 (Sonnet) + dispatcher:rg2 (GLM-5.2 Ollama Cloud),
  BEIDE TIER=engine — gleiche Queue (Modell-Vergleich). Launcher:
  /tmp/orch/launch-r1.sh, /tmp/orch/launch-rg2.sh (Kopien in
  magic-ops/launchers/). NUR EIN Ollama-Worker gleichzeitig (Quota).
- Queue-Source: scripts/class-ticket-builder.py (Cron 03:40, dispatcher-DIREKT
  via sqlite, TARGET_OPEN=5, MIN_UNLOCK=30). Alte per-Card-Tickets:
  state='parked-era1' (261 Stück; Revert: UPDATE tickets SET state='todo'
  WHERE state='parked-era1').
- Corpus-Default: magic-new corpus/AtomicCards.json.gz (MTGJSON 2026-08-09).
  Refresh: curl mtgjson.com/api/v5/AtomicCards.json.gz -> corpus/ ->
  python3 scripts/paragraph/reparse.py --import-corpus (idempotent, nur voll
  v2-eligible Karten werden auto) -> go test ./cards/... -> commit+deploy.
- Kanboard war 2026-08-10 mittags 503 — class-Pipeline haengt NICHT mehr an
  Kanboard (dispatcher-direkt); Bugfixer-Kanboard-Crons pruefen wenn wieder up.

## Korrektur 2026-08-10 spät: Pipeline-first (Dani)
Fleet-Default ist die STAGED PIPELINE (7 Steps, nur 1-2 agentic; 1.6M vs
22.5M pro Kreis validiert 2026-08-07) — NICHT der free-form agentic Worker
(der 51.8M-Vorfall lief free-form). Fenster: dispatcher:p1 (Sonnet
map-pipeline) + dispatcher:lp1 (lokal $0). Free-form dispatcher-worker-*
NUR noch als Eskalation wenn Pipeline nonzero exitet. Engine-Class-Rounds:
state='fable' Queue, Operator-Sessions (Budget + go/no-go von Dani).

## Fleet-Stand 2026-08-10 spät (r1+rg1 Engine-Pairing, rg2 gestoppt)
Aktuelle Lane-Konfiguration (Stand ~20:20 CEST) — Components-Tabelle oben
(Zeile "Worker r1 ... map tier") ist damit überholt, diese Sektion ist
maßgeblich:
- `dispatcher:p1` — Sonnet, staged map→engine-Pipeline (7 Steps). Launcher
  `magic-ops/launchers/launch-p1.sh`. Läuft, Pace-Gate-gesteuert.
- `dispatcher:p2` — zweite Sonnet-Lane, identisch zu p1 (eigener Klon via
  WORKER_ID, keine Kollision). Launcher `launch-p2.sh`. Gestartet 2026-08-11
  ~20:00 CEST ("4% übrig, lohnt sich bis 20:00").
- `dispatcher:p3` — dritte Sonnet-Lane, identisch zu p1/p2. Launcher
  `launch-p3.sh`. Gestartet 2026-08-12 ~10:46 CEST (Usage-Headroom bestätigt:
  25%/5h, 44%/7d).
- `dispatcher:r1` — Sonnet, TIER=engine, agentic (dispatcher-worker-reparse.sh).
  Launcher `launch-r1.sh`.
- `dispatcher:rg1` — GLM-5.2 Ollama Cloud, TIER=engine (geändert von handler
  am 2026-08-10, Dani: "rg1 auf derselben Pipeline wie Sonnet r1"), $0/Woche-
  Quota. Launcher `launch-rg1.sh`. Teilt sich die Queue mit r1
  (Sonnet-vs-GLM-Signal).
- `dispatcher:rl1` — gpt-oss:120b via Shim :4102, TIER=handler NUR
  (explizit kein engine, kein map — Dani 2026-08-10). Launcher `launch-rl1.sh`.
- `rg2` (das r1+rg2-Pairing aus der "Abend"-Sektion oben) ist GESTOPPT,
  abgelöst durch r1+rg1. Falls rg2 wieder gebraucht wird: `launch-rg2.sh`
  (TIER=engine, eigener Klon `/tmp/work/disp-rg2`) — NICHT gleichzeitig mit
  rg1 starten (Ollama-Quota geteilt; "nur ein Ollama-Worker gleichzeitig"
  gilt weiter).
- `og1` — **ARCHIVIERT 2026-08-12** (Dani: Ollama-Cloud-Abo gekündigt, "we
  don't have anymore access to it, as I don't pay it anymore"). War GLM-5.2
  Ollama Cloud auf der STAGED MAP-Pipeline (kein agentic). Lief 2026-08-10
  bis 2026-08-12 ~14:32, dann API 403 "this model requires a subscription"
  auf jeden Call (Details: [[ollama_cloud_403_subscription]]) — ~28 Tickets
  fälschlich als "escalated/deprioritized" markiert bevor bemerkt, dann
  gestoppt. `launch-og1.sh` ist jetzt ein Guard (`exit 1` + Log-Zeile), der
  ORIGINALE Lane-Code steht dort auskommentiert falls das Abo je reaktiviert
  wird. NICHT in Reboot-Recovery unten, NICHT wieder manuell starten ohne
  vorher zu prüfen, dass das Abo wieder aktiv ist.
- FTS5-Preseed (`dispatcher-worker-reparse.sh`, Stage-A-Injektion vor dem
  ersten Modell-Call) läuft jetzt für handler+map+engine, nicht mehr nur
  handler — direkt relevant für r1/rg1 (TIER=engine). kb-Index (:4103)
  wird seit heute bei jedem `integrator-lite.sh`-Deploy automatisch
  neu gebaut (`push_deploy()` ruft `/reindex`).

**WICHTIG — Reboot-Lücke:** keiner der Worker oben (p1/p2/p3/r1/rg1/rl1)
startet automatisch neu (og1 ist archiviert, siehe oben — bewusst NICHT in
der Liste). Die einzigen `@reboot`-Crons sind
`dispatcher-reparse-launch.sh` (baut Dispatcher + EIN `r1` OHNE Tier +
`rf1` Fable/engine — eine ANDERE Konfiguration, kollidiert im Fenster-Namen
mit dem `r1` oben!) und `local-lanes-launch.sh` (anderes System,
Triage/Record-Builder). `p1` kam ursprünglich aus einem EINMALIGEN
datierten Cron (7.8., nicht wiederkehrend) — läuft NICHT nach Reboot neu an.
Nach jedem Reboot manuell:
```
bash magic-ops/launchers/restore-launchers.sh   # git -> /tmp/orch
tmux new-window -t dispatcher -n p1  'bash /opt/development/magic-ops/launchers/launch-p1.sh; exec bash'
tmux new-window -t dispatcher -n p2  'bash /opt/development/magic-ops/launchers/launch-p2.sh; exec bash'
tmux new-window -t dispatcher -n p3  'bash /opt/development/magic-ops/launchers/launch-p3.sh; exec bash'
tmux new-window -t dispatcher -n r1  'bash /opt/development/magic-ops/launchers/launch-r1.sh; exec bash'
tmux new-window -t dispatcher -n rg1 'bash /opt/development/magic-ops/launchers/launch-rg1.sh; exec bash'
tmux new-window -t dispatcher -n rl1 'bash /opt/development/magic-ops/launchers/launch-rl1.sh; exec bash'
```
(og1 bewusst NICHT hier — archiviert, siehe Fleet-Stand-Sektion oben.)
(kb :4103 und shim :4102 haben eigene manuelle Startzeilen in der
Components-Tabelle oben — ebenfalls nicht reboot-persistent.)
