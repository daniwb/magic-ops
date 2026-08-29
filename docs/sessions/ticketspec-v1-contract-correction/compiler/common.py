#!/usr/bin/env python3
import hashlib, json, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPS = pathlib.Path('/opt/development/magic-ops')
MAGIC = pathlib.Path('/opt/development/magic-new')
OPENMAGIC = pathlib.Path('/opt/development/test/openmagic')
PARSER = OPENMAGIC / 'scripts/paragraph'
SNAP = pathlib.Path('/opt/development/magic-ops-artifacts/oracle-face-snapshot/run1/8cdd0282d959a4039ceaa5e462c9214b3e95f15de9b9880373bda04f5fbef629.jsonl.xz')

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def digest(value):
    data = value if isinstance(value, bytes) else canonical(value)
    return 'sha256:' + hashlib.sha256(data).hexdigest()

def file_digest(path):
    return digest(pathlib.Path(path).read_bytes())

def load(path):
    return json.loads(pathlib.Path(path).read_text())

def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b'\n')

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

def repository_state(repo, relevant_paths):
    relevant = []
    for rel in relevant_paths:
        path = pathlib.Path(repo) / rel
        relevant.append({'path': rel, 'sha256': file_digest(path)})
    return {
        'repository': str(repo),
        'commit': git(repo, 'rev-parse', 'HEAD'),
        'dirty_paths': sorted(x for x in git(repo, 'status', '--porcelain').splitlines() if x),
        'relevant_files': relevant,
        'dirty_policy': 'all dirty paths recorded; only content-bound relevant_files are inspected surface',
    }

def tree_digest(root, excluded=()):
    h = hashlib.sha256()
    for path in sorted(pathlib.Path(root).rglob('*')):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and rel not in excluded and not any(path.match(x) for x in ('*/__pycache__/*', '*.pyc')):
            h.update(rel.encode() + b'\0' + path.read_bytes())
    return 'sha256:' + h.hexdigest()
