#!/usr/bin/env bash
while true; do
  PORT=:9999 DB_PATH='/opt/development/magic-ops/services/dispatcher/v4/dispatcher.db' \
    BACKLOG='/opt/development/kanboard-backlog/reparse-tasks.jsonl' \
    /opt/development/magic-ops/services/dispatcher/v4/dispatcher-v4 >> /tmp/dispatcher-v4.log 2>&1
  echo "[$(date -Is)] dispatcher exited, restart 5s" >> /tmp/dispatcher.log
  sleep 5
done
