#!/usr/bin/env bash
# Activate the virtual environment and ensure attemory is running, then store each Go file in attemory.

# Activate venv
source $(pwd)/.venv/bin/activate

# Simple health check – if it fails, start the service.
if ! python - <<'PY'
import sys, pathlib, requests
HOST = '127.0.0.1'
PORT = 8005
try:
    r = requests.get(f'http://{HOST}:{PORT}/health', timeout=2)
    sys.exit(0 if r.ok else 1)
except Exception:
    sys.exit(1)
PY
then
    echo "Starting attemory service..."
    ./scripts/run_attemory.sh
    sleep 2
fi

# Determine the absolute path to the sibling backend directory
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(realpath "${SCRIPT_DIR}/../..")
BACKEND_DIR="${REPO_ROOT}/magic-new/backend"

# Export variables for the Python subprocess
export REPO_ROOT
export BACKEND_DIR

if [ ! -d "${BACKEND_DIR}" ]; then
    echo "Backend directory not found: ${BACKEND_DIR}" >&2
    exit 1
fi

# Python block to store each Go file
python - <<'PY'
import pathlib, sys, os
# Add repo root to PYTHONPATH for wrapper import
repo_root = os.getenv('REPO_ROOT')
if repo_root:
    sys.path.append(repo_root)
from magic_ops.attemory_wrapper import store_file

backend_dir = pathlib.Path(os.getenv('BACKEND_DIR'))
go_files = list(backend_dir.rglob('*.go'))
print(f"Found {len(go_files)} Go files. Storing in attemory...")
for f in go_files:
    try:
        store_file(str(f))
        print(f"Stored: {f}")
    except Exception as e:
        print(f"Error storing {f}: {e}", file=sys.stderr)
PY
