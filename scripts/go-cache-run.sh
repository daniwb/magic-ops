#!/usr/bin/env bash
# Central admission and maintenance barrier for every managed Go invocation.
#
# Normal runs briefly pass the admission gate, then hold a shared active lock
# for their whole lifetime.  Cleaning closes admission first, waits for all
# existing shared holders to drain, and only then mutates the cache.  This
# removes the check-then-clean race that can delete artifacts beneath go test.
set -euo pipefail

OPS="${GO_CACHE_OPS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CACHE="${GO_CACHE_ROOT:-$OPS/../.gocache-magic}"
LOCK_DIR="${GO_CACHE_LOCK_DIR:-/tmp/orch}"
STATUS="${GO_CACHE_STATUS_FILE:-$OPS/state/go-cache-maintenance.json}"
REAL_GO="${GO_CACHE_GO_BINARY:-$(command -v go)}"
ADMISSION="$LOCK_DIR/go-cache-admission.lock"
ACTIVE="$LOCK_DIR/go-cache-active.lock"
MAINTENANCE="$LOCK_DIR/go-cache-maintenance.lock"

mkdir -p "$CACHE" "$LOCK_DIR" "$(dirname "$STATUS")"

utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }
size_gib() {
  du -sk "$CACHE" 2>/dev/null | awk '{printf "%.2f", $1/1024/1024}'
}
write_status() {
  local state="$1" message="$2" requested_at="${3:-}" started_at="${4:-}" finished_at="${5:-}" before="${6:-}" after="${7:-}"
  local tmp="${STATUS}.tmp.$$"
  python3 - "$tmp" "$state" "$message" "$requested_at" "$started_at" "$finished_at" "$before" "$after" "$CACHE" <<'PY'
import json, sys
out, state, message, requested, started, finished, before, after, cache = sys.argv[1:]
value = {
    "schema": "factory.go-cache-maintenance/v1",
    "state": state,
    "message": message,
    "cache_path": cache,
    "updated_at": finished or started or requested,
}
for key, raw in (("requested_at", requested), ("started_at", started), ("finished_at", finished)):
    if raw:
        value[key] = raw
for key, raw in (("size_before_gib", before), ("size_after_gib", after)):
    if raw:
        value[key] = float(raw)
with open(out, "w") as handle:
    json.dump(value, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
  mv "$tmp" "$STATUS"
}

run_managed() {
  # Every entrant serializes for only the time required to take its shared
  # active lock. A cleaner holding admission therefore prevents new entrants.
  exec 8>"$ADMISSION"
  flock -x 8
  exec 9>"$ACTIVE"
  flock -s 9
  flock -u 8
  export GOCACHE="$CACHE"
  # Isolated clones share package artifacts when debug paths are normalized.
  # Bound each Go invocation so simultaneous worker/integration builds leave
  # capacity for the controller and interactive development. Explicit caller
  # settings (including -trimpath=false) remain authoritative.
  export GOMAXPROCS="${GOMAXPROCS:-2}"
  export GOFLAGS="-trimpath -p=2 ${GOFLAGS:-}"
  export PATH="$(dirname "$REAL_GO"):$PATH"
  exec python3 "$OPS/scripts/factory_ng_quiet.py" --exec "$@"
}

clean_cache() {
  exec 7>"$MAINTENANCE"
  if ! flock -n -x 7; then
    echo "Go cache maintenance is already active" >&2
    return 75
  fi

  local requested started finished before after rc
  requested="$(utc)"
  before="$(size_gib)"
  write_status requested "Go cache cleanup requested; closing admission to new Go gates." "$requested" "" "" "$before"

  exec 8>"$ADMISSION"
  flock -x 8
  write_status waiting_for_tests "Cache cleanup is waiting for running Go gates to finish; new gates are paused." "$requested" "" "" "$before"

  exec 9>"$ACTIVE"
  flock -x 9
  started="$(utc)"
  write_status cleaning "Go cache cleanup is running; new Go gates remain paused." "$requested" "$started" "" "$before"

  rc=0
  GOCACHE="$CACHE" "$REAL_GO" clean -cache || rc=$?
  finished="$(utc)"
  after="$(size_gib)"
  if (( rc == 0 )); then
    write_status completed "Go cache cleanup completed; Go gates are available again." "$requested" "$started" "$finished" "$before" "$after"
  else
    write_status failed "Go cache cleanup failed; locks were released so Go gates can continue." "$requested" "$started" "$finished" "$before" "$after"
  fi
  return "$rc"
}

case "${1:-}" in
  clean)
    shift
    clean_cache "$@"
    ;;
  exec)
    shift
    (( $# > 0 )) || { echo "usage: $0 exec COMMAND [ARG ...]" >&2; exit 64; }
    run_managed "$@"
    ;;
  status)
    if [[ -f "$STATUS" ]]; then cat "$STATUS"; else printf '{"state":"idle","cache_path":"%s"}\n' "$CACHE"; fi
    ;;
  "")
    echo "usage: $0 {GO_ARGS...|exec COMMAND...|clean|status}" >&2
    exit 64
    ;;
  *)
    run_managed "$REAL_GO" "$@"
    ;;
esac
