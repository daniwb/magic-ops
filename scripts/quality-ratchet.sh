#!/bin/bash
# quality-ratchet.sh — nightly honesty ratchet (phase.rs adoption 2026-08-10).
# Runs the two read-only auditors over the live checkout and compares against
# the stored baseline. Four-bucket discipline: metric got WORSE -> ALERT mail
# + keep old baseline (so the alert repeats until fixed); metric improved or
# equal -> baseline updates silently. Read-only w.r.t. the repo; safe to run
# while workers are active.
set -u
REPO=/opt/development/magic-new
STATE=/opt/development/magic-ops/state/quality-ratchet.json
LOG=/tmp/orch/quality-ratchet.log
MAIL_TO="${REPORT_TO:-dani@sunier.li}"
MAIL_FROM="${REPORT_FROM:-dani@sunier.li}"

cd "$REPO" || exit 2
python3 scripts/primitive_inventory.py >/dev/null 2>>"$LOG" || { echo "$(date -Is) inventory FAILED" >>"$LOG"; exit 2; }
python3 scripts/paragraph/swallow_audit.py >/dev/null 2>>"$LOG" || { echo "$(date -Is) swallow FAILED" >>"$LOG"; exit 2; }

read -r INERT_LIVE SWALLOW <<EOF2
$(python3 - <<'PY'
import json
inv = json.load(open('corpus/primitive-inventory.json'))
names, flags = inv['names'], inv['flags']
inert_live = sum(1 for n in flags['inert_candidate'] if names[n]['usage_auto'] > 0)
sw = json.load(open('corpus/swallow-audit.json'))
print(inert_live, len(sw['findings']))
PY
)
EOF2

OLD_INERT=999999; OLD_SWALLOW=999999
if [ -f "$STATE" ]; then
  OLD_INERT=$(python3 -c "import json;print(json.load(open('$STATE'))['inert_live'])" 2>/dev/null || echo 999999)
  OLD_SWALLOW=$(python3 -c "import json;print(json.load(open('$STATE'))['swallow'])" 2>/dev/null || echo 999999)
fi

echo "$(date -Is) inert_live=$INERT_LIVE (was $OLD_INERT) swallow=$SWALLOW (was $OLD_SWALLOW)" >>"$LOG"

if [ "$INERT_LIVE" -gt "$OLD_INERT" ] || [ "$SWALLOW" -gt "$OLD_SWALLOW" ]; then
  SUBJECT="[magefield] QUALITY RATCHET ALERT: inert_live $OLD_INERT->$INERT_LIVE, swallow $OLD_SWALLOW->$SWALLOW"
  BODY="Quality ratchet regression on $(hostname) $(date -Is)

inert primitives with LIVE auto usage: $OLD_INERT -> $INERT_LIVE
swallow-audit findings (auto pile):    $OLD_SWALLOW -> $SWALLOW

A worse number means newly shipped records carry semantics the engine does
not execute (parse-but-inert) or drops (swallowed clause). Inspect:
  $REPO/corpus/primitive-inventory-report.md
  $REPO/corpus/swallow-audit-report.md
Baseline NOT updated — this alert repeats nightly until fixed or the
baseline is bumped deliberately (edit $STATE).

-- quality-ratchet.sh (docs/phase-rs-factory-analysis.md)"
  SUBJECT_ENC="=?UTF-8?B?$(printf '%s' "$SUBJECT" | base64 -w0)?="
  BODY_B64=$(printf '%s\n' "$BODY" | base64 -w0)
  printf 'Subject: %s\nFrom: magefield-fleet <%s>\nTo: %s\nMIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\nContent-Transfer-Encoding: base64\n\n%s\n' \
    "$SUBJECT_ENC" "$MAIL_FROM" "$MAIL_TO" "$BODY_B64" \
    | /usr/sbin/sendmail -f "$MAIL_FROM" -t
  echo "$(date -Is) ALERT sent" >>"$LOG"
  exit 1
fi

printf '{"inert_live": %s, "swallow": %s, "updated": "%s"}\n' "$INERT_LIVE" "$SWALLOW" "$(date -Is)" > "$STATE"
exit 0
