# Worker quota visibility — September 17

At04:51 UTC the queue had11 runnable tickets, shared Codex usage was80%,
primary Codex allowed95%, and Codex-2/-3/-4 allowed70%. The controller correctly
held all three secondary workers. Claude was paused at its daily weekly-pacing
tranche. Canonical source was clean with integration lock free at startup.

The limits API only returned primary Claude/Codex entries. The dashboard looked
up every worker by exact ID and treated a missing secondary entry as available.
The fix returns a separate limit for every configured metered worker while
preserving primary account cards. Each uses its own ceiling/mode and Claude
pause marker. Codex pause results include reset/resume time. Worker cards show
shared usage alongside their own ceiling when quota-paused.

proposed-workers.json contains the concrete optional settings change: the three
secondary Codex ceilings would increase70→95, matching the primary. It is NOT
applied; user approval to change the spending limit is pending. The operational
fix does not change scheduling, limits, gates, or game deployment.

Validation and live reload evidence will be appended after checks complete.

## Validation and live result

Five focused Go checks passed (including new per-worker endpoint regression,
independent setting changes and stale usage), and embedded JavaScript syntax
passed. Dashboard binary built and reloaded under dispatcher-admin lock.
Live API now reports primary available at81%/95%, and Codex-2/-3/-4 paused
at81%/70%, with reset2026-09-23T04:59:29Z. Executing the deployed renderRun
against live API data produces three usage-paused cards with own ceiling and
shared usage. See after-limits.json, rendered-worker-cards.html, validation.json.
Canonical source clean, integration lock free, controller running and11runnable
at04:58 closing health check. Quota settings are byte-content equivalent to the
initial worker configuration. Their optional increase remains pending user choice.

## User-approved shared Codex limit

The user requested the same limits as the primary and disabled Codex-3.
Applied primary fixed95% to Codex-2/-3/-4 via scoped worker API updates,
preserving every enabled flag and execution setting. Primary, Codex-2 and
Codex-4 were independently observed with live ticket processes afterward.
Codex-3 remains disabled. See applied-limits.json and after-sync.json.

The main Codex limit control now updates mode and ceiling for all workers using
codex-weekly, including disabled workers without enabling them. It is labeled
“all Codex workers”; worker cards correctly display disabled when no lease is
active. Explicit secondary API overrides remain possible, but every primary
limit edit resynchronizes the group. Unrelated primary enabled/model/profile
changes do not propagate. Claude policies are unchanged. Obsolete70% descriptive
text was replaced with a reference to the primary limit.

Six focused Go checks pass, including fixed/paced/none propagation, disabled
state preservation, primary enable-toggle isolation and unrelated Claude limits.
JS syntax and actual deployed card/control rendering pass. Dashboard rebuilt
and reloaded under dispatcher-admin. Prior proposed-workers.json is historical:
do not apply its old enabled flags. The user's authorization is now fulfilled;
there is no pending quota approval.
