#!/bin/bash
# Supervised launcher for the card-knowledge service (:4103).
#
# The service previously had no restart supervision at all — it was started
# by hand in a tmux pane, and once killed (crash, OOM, closed terminal) it
# stayed down silently since nothing else depends on it loudly enough to
# notice. This mirrors the same "while true; wait; sleep" pattern already
# used for the factory-ng/factory-watch lanes.
cd /opt/development/magic-ops || exit 1
while true; do
  python3 scripts/card-knowledge-service.py >> /tmp/orch/kb.log 2>&1 &
  kb_pid=$!
  wait "$kb_pid"
  echo "[$(date -u +%FT%TZ)] card-knowledge-service exited, restarting in 5s" >> /tmp/orch/kb.log
  sleep 5
done
