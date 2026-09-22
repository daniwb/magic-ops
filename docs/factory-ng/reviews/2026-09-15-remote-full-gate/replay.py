"""Replay a completed integration's checks; never merge, commit, push or deploy."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

OPS = Path('/opt/development/magic-ops')
SOURCE = Path('/trial/source')
OUT = Path('/trial/output')
sys.path.insert(0, str(OPS / 'scripts'))
spec = importlib.util.spec_from_file_location('integration', OPS / 'scripts/factory-ng-integrate.py')
integration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integration)
manifest = json.loads(Path('/trial/manifest.json').read_text())
started = time.monotonic()
report = {'schema': 'factory.full-gate-replay/v1', 'revision': manifest['revision'],
          'gates': [], 'outcome': 'running', 'cpus': sorted(os.sched_getaffinity(0)),
          'go_parallelism': os.environ['GOMAXPROCS']}


def save():
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')


def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args], text=True).strip()


try:
    assert git('rev-parse', 'HEAD') == manifest['revision']
    assert not git('status', '--porcelain')
    for relative, expected in manifest['inputs'].items():
        assert hashlib.sha256((OPS / relative).read_bytes()).hexdigest() == expected, relative
    assert hashlib.sha256((SOURCE / 'corpus/AtomicCards.json.gz').read_bytes()).hexdigest() == manifest['corpus_sha256']
    for relative in manifest['parents']:
        observation = json.loads((OPS / relative).read_text())
        print('Semantic gates:', observation['ticket']['id'], flush=True)
        passed = integration.semantic_gates(observation, SOURCE, report['gates'])
        save()
        if not passed:
            raise RuntimeError('original semantic contract failed')
    for step in manifest['commands']:
        identifier = step['id']
        print('Starting:', identifier, flush=True)
        cwd = SOURCE / 'backend' if identifier in ('go-build', 'game-tests', 'focused-go') else SOURCE
        result = integration.call(step['argv'], cwd, timeout=7200 if identifier == 'full-sharded-suite' else 1800)
        (OUT / (identifier + '.log')).write_text(result['stdout'] + '\n' + result['stderr'])
        report['gates'].append(integration.gate(identifier, step['argv'], result))
        save()
        print('Finished:', identifier, result['exit_code'], result['elapsed_ms'], 'ms', flush=True)
        if result['exit_code']:
            raise RuntimeError(identifier + ' failed')
    # Reproduce the production index operation only inside this disposable clone.
    git('add', '-A', 'backend/data/carddb')
    report['generated_tree'] = git('write-tree')
    report['expected_tree'] = manifest['expected_tree']
    report['tree_matches_local'] = report['generated_tree'] == report['expected_tree']
    (OUT / 'tree-diff.txt').write_text(git('diff', '--stat', manifest['expected_result_commit']))
    if not report['tree_matches_local']:
        raise RuntimeError('generated tree differs from the locally gated tree')
    report['outcome'] = 'passed'
except Exception as exc:
    report['outcome'] = 'failed'
    report['error'] = str(exc)
finally:
    for name in ('memory.peak', 'cpu.stat', 'memory.events'):
        path = Path('/sys/fs/cgroup') / name
        if path.exists():
            report[name] = path.read_text().strip()
    save()
    print(json.dumps({key: value for key, value in report.items() if key != 'gates'}), flush=True)
sys.exit(0 if report['outcome'] == 'passed' else 1)
