#!/usr/bin/env bash
# After reboot: restore the tmux lane launchers into /tmp/orch and print
# the start commands (see RUNBOOK.md component table for the windows).
mkdir -p /tmp/orch
cp "$(dirname "$0")"/launch-*.sh /tmp/orch/
chmod +x /tmp/orch/launch-*.sh
echo "launchers restored to /tmp/orch — start via tmux windows per RUNBOOK"
