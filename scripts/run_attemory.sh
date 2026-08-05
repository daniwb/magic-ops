#!/usr/bin/env bash
# Activate the virtual environment and start attemory as a background service
source $(pwd)/.venv/bin/activate
# Start the attemory server (API enabled) on the configured port (using --small preset)
nohup attemory-server --small --host 127.0.0.1 --port 8005 > attemory.log 2>&1 &
# Save the PID so we can stop it later if needed
echo $! > attemory.pid
