#!/bin/bash
# Kanboard Sync Cron — load new tasks every 5 minutes
# Add to crontab: */5 * * * * /opt/development/magic-claude/scripts/kanboard-sync-cron.sh

set -e

DISPATCHER="http://localhost:9999"
KB_URL="https://kanboard.k.ezq.ch/jsonrpc.php"
KB_USER="admin"
KB_TOKEN="fda650985874506da62a737b9a7befc39a5873735a253de80fa2d5ee5c20"
PROJECT_ID="2"
COL_TODO="16"

log() { echo "[$(date '+%H:%M:%S')] $*" >> /tmp/kanboard-sync.log; }

# Get new tasks from Kanboard
TASKS=$(curl -s -X POST "$KB_URL" \
  -H "Content-Type: application/json" \
  --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"search\",\"params\":{\"project_id\":$PROJECT_ID,\"query\":\"column:$COL_TODO sort:id limit:20\"}}" \
  2>/dev/null | jq '.result[]? | {id, title}' 2>/dev/null || echo "")

if [ -z "$TASKS" ]; then
  log "No new tasks in Kanboard"
  exit 0
fi

# Add each task to dispatcher
COUNT=0
echo "$TASKS" | while read -r task; do
  ID=$(echo "$task" | jq -r '.id')
  TITLE=$(echo "$task" | jq -r '.title')

  if [ -z "$ID" ] || [ "$ID" = "null" ]; then
    continue
  fi

  # Add to dispatcher
  RESPONSE=$(curl -s -X POST "$DISPATCHER/add-ticket" \
    -H "Content-Type: application/json" \
    -d "{\"id\":\"kb-$ID\",\"title\":\"$TITLE\"}" 2>/dev/null)

  if echo "$RESPONSE" | grep -q "\"status\":\"inserted\""; then
    log "✓ Added Kanboard task $ID: $TITLE"
    COUNT=$((COUNT + 1))
  fi
done

log "Sync complete: $COUNT new tasks loaded"
