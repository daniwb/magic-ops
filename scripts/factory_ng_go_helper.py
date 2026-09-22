"""Reuse installed source-analysis helpers without invoking Go during drafting."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
from factory_ng_quiet import compilation_status, POLICY

OPS = Path(__file__).resolve().parents[1]


def helper_binary(source):
    source = Path(source)
    key = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    directory = OPS / 'state' / 'go-helpers'
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / (source.parent.name + '-' + source.stem + '-' + key)
    with (directory / 'build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not binary.exists():
            if not compilation_status(json.loads(POLICY.read_text()))['allowed']:
                raise RuntimeError('Source-analysis helper needs installation; enable compilation/testing once.')
            temporary = binary.with_suffix('.tmp')
            try:
                subprocess.run([str(OPS / 'scripts/go-cache-run.sh'), 'build', '-o', str(temporary), str(source)],
                               check=True, capture_output=True, timeout=180)
                os.replace(temporary, binary)
            finally:
                temporary.unlink(missing_ok=True)
    return str(binary)
