#!/usr/bin/env python3
"""Container entry: compute the full gate and return card data, without landing."""
import importlib.util
import json
from pathlib import Path
import sys

from factory_ng_full_gate_remote import digest, git, invoke

job = Path(sys.argv[1])
source = job / 'source'
out = job / 'output'
out.mkdir(exist_ok=True)
data = (job / 'manifest.json').read_bytes()
manifest = json.loads(data)
spec = importlib.util.spec_from_file_location('full_gate_integration', Path(__file__).with_name('factory-ng-integrate.py'))
integration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integration)
result = {'schema': 'factory.remote-full-gate/v1', 'manifest_sha256': digest(data),
          'input_revision': git(source, 'rev-parse', 'HEAD'),
          'input_tree': git(source, 'rev-parse', 'HEAD^{tree}'), 'gates': []}
assert result['input_revision'] == manifest['revision'] and result['input_tree'] == manifest['tree']
assert not git(source, 'status', '--porcelain')
assert digest((source / 'corpus/AtomicCards.json.gz').read_bytes()) == manifest['corpus_sha256']
expected = [[key, ['python3', *argv[1:]] if key.startswith('reparse-') else argv, timeout]
            for key, argv, timeout in integration.full_gate_commands(manifest['tag'])]
assert expected == manifest['commands'], 'transported gate commands differ from production'
# Normalize Python location in evidence to match the manifest across hosts.
integration.full_gate_commands = lambda tag: expected
for relative, expected_hash in manifest.get('input_hashes', {}).items():
    assert digest((integration.OPS / relative).read_bytes()) == expected_hash
semantic_specs = [check for observation in manifest.get('observations', [])
                  for check in integration.semantic_contract(observation)[1]]
assert semantic_specs == manifest.get('semantic_gates', []), 'semantic contract differs from manifest'
passed = True
for observation in manifest.get('observations', []):
    if not integration.semantic_gates(observation, source, result['gates']):
        passed = False
        break
if passed:
    passed = integration.run_full_gates(source, result['gates'], manifest['tag'])
result['outcome'] = 'passed' if passed else 'failed'
if passed:
    # Include newly generated card JSON while detecting other tracked mutations.
    git(source, 'add', '-A', 'backend/data/carddb')
    assert not git(source, 'diff', '--name-only'), 'full gate changed tracked files outside generated card data'
    result['result_tree'] = git(source, 'write-tree')
    patch = invoke(['git', '-C', source, 'diff', '--cached', '--binary', '--full-index', 'HEAD']).encode()
    (out / 'carddb.patch').write_bytes(patch)
    result['patch_sha256'] = digest(patch)
peak = Path('/sys/fs/cgroup/memory.peak')
if peak.exists(): result['peak_memory_bytes'] = int(peak.read_text())
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'outcome': result['outcome'], 'gates': len(result['gates'])}))
