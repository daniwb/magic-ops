#!/bin/bash
# Sync dispatcher queue with Kanboard
# Runs periodically to load new tickets and write status back

DISPATCHER="http://localhost:9999"
KB_URL="http://localhost:8080"
KB_API_TOKEN="${KB_API_TOKEN:-admin}"

log() { echo "[$(date '+%H:%M:%S')] Kanboard-Sync: $*"; }

# Fetch dispatcher status
STATUS=$(curl -s "$DISPATCHER/status")
log "Dispatcher status: $STATUS"

# TODO: Fetch new cards from Kanboard column "new"
# For each: INSERT into dispatcher DB via custom API

# TODO: Write done cards back to Kanboard (move to "done" column)

log "Sync complete"
