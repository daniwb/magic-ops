#!/usr/bin/env bash
# Run one shared-state mutation under its narrow kernel-held lock.
set -euo pipefail

kind="${1:-}"
[ "$#" -ge 2 ] || {
  echo "usage: $0 <integration|deploy|dispatcher-admin> <command> [args...]" >&2
  exit 2
}
shift

case "$kind" in
  integration)      lock=/tmp/orch/openmagic-integration.lock ;;
  deploy)           lock=/tmp/orch/factory-deploy.lock ;;
  dispatcher-admin) lock=/tmp/orch/dispatcher-admin.lock ;;
  *) echo "unknown scoped lock: $kind" >&2; exit 2 ;;
esac

mkdir -p /tmp/orch
exec flock -n -E 75 "$lock" "$@"
