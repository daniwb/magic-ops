#!/usr/bin/env python3
"""Bound one remote full gate with a host lock, private cache, and deadline."""
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys

job = Path(sys.argv[1]).resolve()
assert job.parent.name == 'jobs' and job.name.startswith('fullgate-')
root = job.parent.parent
settings = json.loads((job / 'manifest.json').read_text())['settings']
name = 'factory-ng-' + job.name
with (root / 'full-gate.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    active = subprocess.check_output(['podman', 'ps', '-q', '--filter', 'label=factory-ng-role=full-gate'], text=True)
    if active.strip(): raise RuntimeError('an orphaned full gate is still running')
    cache = root / 'full-gate-cache'
    if not cache.exists():
        cache.mkdir()
        subprocess.run(['cp', '-a', '--reflink=auto', str(root / 'build-cache') + '/.', str(cache)], check=True, timeout=300)
    (job / 'tmp').mkdir(); (job / 'output').mkdir()
    command = ['podman', 'run', '--rm', '--name', name, '--network=none', '--timeout=10800',
               '--memory=12g', '--pids-limit=512', '--label=factory-ng-role=full-gate',
               '-v', str(job) + ':/job:Z',
               '-v', str(job / 'ops') + ':/opt/development/magic-ops:Z',
               '-v', str(job / 'tmp') + ':/tmp:Z',
               '-v', str(root / 'toolchain') + ':/usr/local/go:ro,z',
               '-v', str(root / 'gomod') + ':/cache/gomod:z',
               '-v', str(cache) + ':/cache/build:z',
               '-e', 'GOTOOLCHAIN=local', '-e', 'GOMODCACHE=/cache/gomod', '-e', 'GOPROXY=off',
               '-e', 'GO_CACHE_ROOT=/cache/build', '-e', 'GOMAXPROCS=' + str(settings['go_parallelism']),
               '-e', 'GOFLAGS=-p=' + str(settings['go_parallelism']),
               '-w', '/opt/development/magic-ops', settings['image'], 'sh', '-c',
               'ln -s /usr/local/go/bin/go /usr/local/bin/go && ln -s /usr/local/go/bin/gofmt /usr/local/bin/gofmt && exec python3 scripts/factory_ng_quiet.py '
               '--exec python3 scripts/factory-ng-full-gate-run.py /job']
    try:
        with (job / 'container.log').open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=log, timeout=10800)
        if result.returncode:
            raise RuntimeError((job / 'container.log').read_text()[-2400:])
    finally:
        subprocess.run(['podman', 'rm', '--force', '--ignore', name], capture_output=True, timeout=60)
        active = subprocess.check_output(['podman', 'ps', '-q', '--filter', 'label=factory-ng-role=full-gate'], text=True)
        size = int(subprocess.check_output(['du', '-sk', cache], text=True).split()[0]) * 1024
        if not active.strip() and (size > 40 * 1024**3 or (shutil.disk_usage(root).free < 30 * 1024**3 and size > 1024**3)):
            shutil.rmtree(cache)
