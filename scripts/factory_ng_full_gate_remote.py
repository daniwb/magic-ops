"""Transport full-gate computation; canonical integration owns landing authority."""
import contextlib
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid

OPS = Path(__file__).resolve().parents[1]
STATUS = OPS / 'state/factory-ng-full-gate-remote.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def invoke(args, timeout=300):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True,
                          text=True, timeout=timeout).stdout


def git(clone, *args):
    return invoke(['git', '-C', clone, *args]).strip()


def ssh(settings, args, timeout=300):
    return invoke(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                   '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                   settings['host'], shlex.join(list(map(str, args)))], timeout)


def rsync(source, target):
    return invoke(['rsync', '-a', '--timeout=60', '-e',
                   'ssh -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=15 -o ServerAliveCountMax=3',
                   source, target])


def validate_gates(result, manifest):
    """Accept the exact ordered gate prefix, including bounded cache retries."""
    gates = result['gates']
    cursor = 0
    for expected in manifest.get('semantic_gates', []):
        if cursor >= len(gates):
            raise ValueError('missing required semantic gate')
        checked = gates[cursor]; cursor += 1
        if any(checked.get(key) != expected.get(key) for key in ('id', 'command', 'ticket_id')):
            raise ValueError('semantic gate identity or command changed')
        if checked['outcome'] == 'failed':
            if result['outcome'] != 'failed' or cursor != len(gates):
                raise ValueError('failed semantic gate cannot be accepted')
            return False
        if checked['outcome'] != 'passed' or checked.get('exit_code', 0) != 0:
            raise ValueError('invalid semantic gate verdict')
    for identifier, argv, _ in manifest['commands']:
        if cursor >= len(gates):
            raise ValueError('missing required full gate')
        g = gates[cursor]; cursor += 1
        if g['id'] != identifier or g['command'] != ' '.join(argv):
            raise ValueError('full gate command or order changed')
        if g['outcome'] == 'infrastructure_retry':
            if g.get('classification') != 'cache_artifact_disappeared' or g['exit_code'] == 0:
                raise ValueError('invalid cache retry evidence')
            if cursor >= len(gates):
                raise ValueError('missing cache retry')
            g = gates[cursor]; cursor += 1
            if (g['id'] != identifier + '-cache-retry' or g['command'] != ' '.join(argv)
                    or g.get('classification') != 'isolated_cache_retry'):
                raise ValueError('invalid retry gate')
        if g['outcome'] == 'failed' and g['exit_code'] != 0:
            if result['outcome'] != 'failed' or cursor != len(gates):
                raise ValueError('red gate cannot be accepted')
            return False
        if g['outcome'] != 'passed' or g['exit_code'] != 0:
            raise ValueError('inconsistent full gate verdict')
    if cursor != len(gates) or result['outcome'] != 'passed':
        raise ValueError('unexpected full gate verdict')
    return True


def import_result(clone, out, manifest, manifest_hash):
    result = json.loads((out / 'result.json').read_text())
    if (result.get('schema') != 'factory.remote-full-gate/v1'
            or result.get('manifest_sha256') != manifest_hash
            or result.get('input_revision') != manifest['revision']
            or result.get('input_tree') != manifest['tree']):
        raise ValueError('remote full gate input identity mismatch')
    if git(clone, 'rev-parse', 'HEAD') != manifest['revision'] or git(clone, 'status', '--porcelain'):
        raise ValueError('integration clone changed during remote gate')
    for relative, expected in manifest.get('input_hashes', {}).items():
        if digest((OPS / relative).read_bytes()) != expected:
            raise ValueError('semantic input changed during remote gate')
    if not validate_gates(result, manifest):
        return result
    patch = (out / 'carddb.patch').read_bytes()
    if digest(patch) != result.get('patch_sha256'):
        raise ValueError('generated patch hash mismatch')
    # Only this disposable integration clone is modified. Roll back on any
    # invalid patch/tree so fallback starts from the exact original composition.
    try:
        if patch:
            invoke(['git', '-C', clone, 'apply', '--index', '--binary', out / 'carddb.patch'])
        raw = invoke(['git', '-C', clone, 'diff', '--cached', '--raw', '--no-abbrev', '-z', 'HEAD'])
        parts = raw.split('\0')
        for i in range(0, len(parts) - 1, 2):
            header, path = parts[i:i + 2]
            fields = header.split()
            if (not path.startswith('backend/data/carddb/') or '..' in Path(path).parts
                    or fields[0][1:] not in ('100644', '000000')
                    or fields[1] not in ('100644', '000000')
                    or fields[-1] not in ('A', 'M', 'D')):
                raise ValueError('generated patch changes paths or modes outside card data')
        if git(clone, 'write-tree') != result.get('result_tree'):
            raise ValueError('generated tree mismatch')
    except Exception:
        git(clone, 'reset', '--hard', manifest['revision'])
        raise
    return result


def execute_remote(clone, tag, settings, commands, semantic_observations=(), semantic_specs=()):
    name = 'fullgate-' + uuid.uuid4().hex
    remote = settings['root'].rstrip('/') + '/jobs/' + name
    with tempfile.TemporaryDirectory(prefix='factory-ng-fullgate-') as directory:
        stage = Path(directory)
        try:
            if git(clone, 'status', '--porcelain'):
                raise ValueError('full gate requires a clean composed clone')
            revision = git(clone, 'rev-parse', 'HEAD')
            invoke(['git', 'clone', '--quiet', '--no-hardlinks', clone, stage / 'source'])
            git(stage / 'source', 'checkout', '--quiet', '--detach', revision)
            shutil.copyfile(clone / 'corpus/AtomicCards.json.gz', stage / 'source/corpus/AtomicCards.json.gz')
            shutil.copytree(OPS / 'scripts', stage / 'ops/scripts',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'archive'))
            input_hashes = {}
            for observation in semantic_observations:
                ticket_path = observation['ticket']['path']
                ticket = json.loads((OPS / ticket_path).read_text())
                relatives = {ticket_path, *re.findall(r'docs/factory-ng/[\w./-]+', json.dumps(ticket))}
                for relative in relatives:
                    path = (OPS / relative).resolve()
                    if not path.is_relative_to(OPS.resolve()) or '..' in Path(relative).parts:
                        raise ValueError('semantic input path escapes artifact root')
                    if not path.is_file():
                        continue
                    target = stage / 'ops' / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
                    input_hashes[relative] = digest(target.read_bytes())
            (stage / 'ops/config').mkdir(); (stage / 'ops/state').mkdir()
            policy = {'compilation': {'enabled': True}, 'resources': {'cpu_affinity': settings['cpus'], 'nice': 10},
                      'integration': {'automatic': False, 'push_when_full_gate_green': False}}
            (stage / 'ops/config/factory-ng-policy.json').write_text(json.dumps(policy))
            normalized = [[key, ['python3', *argv[1:]] if key.startswith('reparse-') else argv, timeout]
                          for key, argv, timeout in commands]
            manifest = {'revision': revision, 'tree': git(clone, 'rev-parse', 'HEAD^{tree}'),
                        'tag': tag, 'commands': normalized,
                        'observations': list(semantic_observations),
                        'semantic_gates': list(semantic_specs), 'input_hashes': input_hashes,
                        'corpus_sha256': digest((stage / 'source/corpus/AtomicCards.json.gz').read_bytes()),
                        'settings': settings}
            data = json.dumps(manifest, sort_keys=True).encode()
            (stage / 'manifest.json').write_bytes(data)
            ssh(settings, ['mkdir', '-p', remote])
            rsync(str(stage) + '/', settings['host'] + ':' + remote + '/')
            ssh(settings, ['python3', remote + '/ops/scripts/factory-ng-full-gate-host.py', remote], timeout=11100)
            rsync(settings['host'] + ':' + remote + '/output/', str(stage / 'output') + '/')
            return import_result(clone, stage / 'output', manifest, digest(data))
        finally:
            with contextlib.suppress(Exception):
                ssh(settings, ['podman', 'rm', '--force', '--ignore', 'factory-ng-' + name], timeout=60)
                ssh(settings, ['rm', '-rf', '--', remote], timeout=60)


def run_with_fallback(clone, gates, tag, settings, *, local_runner, commands, semantic_observations=(), semantic_specs=()):
    remote = settings.get('integration', {}).get('remote', {})
    execution = {'full_gate_host': 'local'}
    if remote.get('enabled'):
        try:
            prior = json.loads(STATUS.read_text()) if STATUS.exists() else {}
        except (OSError, ValueError):
            prior = {}
        if prior.get('retry_after_epoch', 0) <= time.time():
            try:
                result = execute_remote(clone, tag, remote, commands, semantic_observations, semantic_specs)
            except Exception as exc:
                execution['remote_fallback_reason'] = str(exc)[-2400:]
                status = {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                          'host': remote['host'], 'error': execution['remote_fallback_reason'],
                          'retry_after_epoch': int(time.time()) + 300}
            else:
                gates.extend(dict(g, execution_host=remote['host']) for g in result['gates'])
                execution = {'full_gate_host': remote['host'], 'image': remote['image'],
                             'cpus': remote['cpus'], 'go_parallelism': remote['go_parallelism'],
                             'input_tree': result['input_tree'], 'result_tree': result.get('result_tree'),
                             'manifest_sha256': result['manifest_sha256'],
                             'semantic_checks_remote': bool(semantic_observations),
                             'peak_memory_bytes': result.get('peak_memory_bytes')}
                status = {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                          'host': remote['host'], 'error': None, 'retry_after_epoch': 0}
            STATUS.parent.mkdir(parents=True, exist_ok=True)
            temp = STATUS.with_suffix('.tmp'); temp.write_text(json.dumps(status)); os.replace(temp, STATUS)
            if execution['full_gate_host'] != 'local':
                return result['outcome'] == 'passed', execution
        else:
            execution['remote_fallback_reason'] = 'remote full gate is in transport backoff'
    return local_runner(clone, gates, tag), execution
