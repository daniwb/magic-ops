#!/usr/bin/env bash
# Read-only Factory NG startup check. Full Git operation state matters.
set -uo pipefail
OPS="${FACTORY_NG_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$OPS" || exit 1
export FACTORY_NG_SOURCE="${FACTORY_NG_SOURCE:-$OPS/../test/openmagic}"
export PYTHONPATH="$OPS/../../pydeps${PYTHONPATH:+:$PYTHONPATH}"
health=0
integration_owned=0
echo '== SCOPED MUTATION LOCKS'
for name in openmagic-integration factory-deploy dispatcher-admin; do
  if flock -n "/tmp/orch/$name.lock" true 2>/dev/null; then
    echo "$name: free"
  else
    echo "$name: held"
    [ "$name" != openmagic-integration ] || integration_owned=1
  fi
done
echo '== FACTORY NG'
curl -fsS --max-time 15 http://localhost:9999/factory-ng/status \
  | jq '{state,phase,updated_at,queue,message}' || health=1
echo '== WATCHDOG'
jq '{checked_at,healthy,moving,problems,cards}' state/factory-ng-watchdog.json || health=1
echo '== SUPERVISED LANES'
tmux list-windows -t dispatcher -F '#{window_name}' || health=1
echo '== ENABLED PROFILE CONTRACTS'
python3 scripts/factory-ng-profile-validate.py --enabled-workers || health=1
echo '== CANONICAL SOURCE'
if [ "$integration_owned" = 1 ]; then
  echo 'Integration owns the source; check readiness again after it completes.'
else
  PYTHONPATH=scripts python3 -c 'from factory_ng_safety import source_problem; from factory_ng_paths import SOURCE; import sys; problem=source_problem(SOURCE); print(problem or "clean; no unfinished Git operation"); sys.exit(bool(problem))' || health=1
fi
echo '== CARD KNOWLEDGE'
curl -fsS --max-time 10 http://127.0.0.1:4103/health || health=1
echo '== LIVE SERVICE'
if systemctl is-active --quiet magic-backend; then
  echo 'magic-backend systemd service active'
else
  curl -fsS --max-time 10 http://127.0.0.1:8090/api/health || health=1
fi
echo '== DISK'
df -h /
exit "$health"
