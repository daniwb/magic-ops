#!/usr/bin/env bash
# session-health-check.sh — run at the START of every Claude session.
# Prints factory status + scoped mutation-lock state. Read-only, always safe.
echo "== SCOPED MUTATION LOCKS"
for NAME in openmagic-integration factory-deploy dispatcher-admin; do
  LOCK="/tmp/orch/$NAME.lock"
  if flock -n "$LOCK" true 2>/dev/null; then
    echo "$NAME: free"
  else
    echo "$NAME: held"
  fi
done
echo "== TMUX LANES (expect: disp r1 ro1 shim [rl1] [litellm])"
tmux list-windows -t dispatcher -F '#{window_name}' 2>/dev/null | tr '\n' ' '; echo
echo "== DISPATCHER"
curl -s -m 10 localhost:9999/pilestats || curl -s -m 10 localhost:9999/pilestats || echo "DOWN (2 tries)"
echo; echo "== SERVICE"
systemctl is-active magic-backend
echo "== INTEGRATOR (last 3)"
tail -3 /opt/development/magic-new/.bugfixer-logs/integrator-lite.log 2>/dev/null
echo "== TREE (dirty is OK ONLY while the integrator cron is mid-run — check next line)"
pgrep -cf "integrator-lite.sh" >/dev/null 2>&1 && echo "  integrator currently running: $(pgrep -cf integrator-lite.sh)"
git -C /opt/development/test/openmagic status --porcelain | grep -v '^??' | head -3 || true
echo "== UNMERGED BRANCHES"
cd /opt/development/test/openmagic && git fetch -qp origin 2>/dev/null; U=0
for ref in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin/reparse/ 2>/dev/null); do
  [ "$(git rev-list --count origin/main..$ref 2>/dev/null)" != 0 ] && U=$((U+1)) && echo "  $ref"
done; echo "  total unmerged: $U"
echo "== QUEUE"
python3 -c "
import sqlite3
db=sqlite3.connect('file:/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db?mode=ro',uri=True)
for r in db.execute(\"select state,count(*) from tickets where state in ('todo','claimed','blocked','vocab') group by state\"): print(' ', r)" 2>/dev/null
echo "== DISK"
df -h / | tail -1
