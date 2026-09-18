#!/usr/bin/env python3
"""Transport pinned proposals to the configured SSH verifier, then import evidence."""
import argparse
import contextlib
import fcntl
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from factory_ng_receipts import write_receipt
from factory_ng_verification import checksum, load_proposal, require_compilation, VerificationPaused, repair_artifacts

OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE
POLICY = OPS / 'config/factory-ng-policy.json'
STATUS = OPS / 'state/factory-ng-remote-status.json'


def path_under(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('artifact path escapes its root')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('artifact symlink escapes its root')
    return resolved


def invoke(args, **kwargs):
    args = list(map(str, args))
    if args[0] == 'rsync':
        args[1:1] = ['--timeout=60', '-e',
                     'ssh -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=15 -o ServerAliveCountMax=3']
    return subprocess.run(args, check=True, capture_output=True,
                          text=True, timeout=300, **kwargs).stdout


def ssh(settings, args, **kwargs):
    return invoke(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                   '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                   settings['host'], shlex.join(list(map(str, args)))], **kwargs)


def export_source_bundle(staging, revision, settings, mirror):
    """Transfer new objects relative to the remote mirror's known snapshot."""
    baseline = None
    try:
        candidate = ssh(settings, ['git', '-C', mirror, 'rev-parse', '--verify',
                                    'refs/heads/snapshot']).strip()
        if re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', candidate):
            invoke(['git', '-C', SOURCE, 'cat-file', '-e', candidate + '^{commit}'])
            baseline = candidate
    except subprocess.CalledProcessError:
        pass  # Initial bootstrap still needs a self-contained full bundle.
    bare = staging / 'export.git'
    invoke(['git', 'clone', '--quiet', '--bare', '--shared', SOURCE, bare])
    invoke(['git', '-C', bare, 'update-ref', 'refs/heads/pinned', revision])
    command = ['git', '-C', bare, '-c', 'pack.threads=2', 'bundle', 'create',
               staging / 'source.bundle', 'refs/heads/pinned']
    if baseline:
        command.append('^' + baseline)
    invoke(command)
    shutil.rmtree(bare)


def export_job(entries, staging, settings):
    """Only code and the selected public contracts/artifacts leave this server."""
    target = staging / 'ops'
    target.mkdir()
    shutil.copytree(OPS / 'scripts', target / 'scripts',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'archive'))
    revision = None
    input_hashes = {}
    for entry in entries:
        ticket_path = path_under(OPS, entry['ticket_path'])
        proposal = load_proposal(path_under(OPS, entry['proposal']), ticket_path, entry['identity'])
        if revision is not None and proposal['source_revision'] != revision:
            raise ValueError('remote batch must share one pinned revision')
        revision = proposal['source_revision']
        relatives = [entry['ticket_path'], entry['proposal']]
        relatives.extend(a['path'] for a in repair_artifacts(OPS, proposal.get('context', {})))
        if proposal.get('context', {}).get('raw_path'):
            relatives.append(proposal['context']['raw_path'])
        ticket = json.loads(ticket_path.read_text())
        # Gate member sets and other pinned evidence are outside the game repo.
        # Copy only documents actually referenced by this immutable contract.
        for relative in re.findall(r'docs/factory-ng/[\w./-]+', json.dumps(ticket)):
            if path_under(OPS, relative).is_file():
                relatives.append(relative)
        for relative in set(relatives):
            dest = path_under(target, relative)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path_under(OPS, relative), dest)
            input_hashes[relative] = checksum(dest.read_bytes())
    if not revision:
        raise ValueError('empty remote verification batch')
    (target / 'manifest.json').write_text(json.dumps(entries))
    (target / 'config').mkdir(exist_ok=True)
    (target / 'state').mkdir(exist_ok=True)
    (staging / 'remote-job.json').write_text(json.dumps(dict(settings, revision=revision)))
    (staging / 'input-checksums.json').write_text(json.dumps(input_hashes))
    write_remote_policy(target, settings)
    return revision


def write_remote_policy(target, settings):
    policy = json.loads(POLICY.read_text())
    policy['resources'] = {'cpu_affinity': settings['cpus'], 'nice': 10}
    policy['integration']['automatic'] = False
    path = target / 'config/factory-ng-policy.json'
    path.write_text(json.dumps(policy))


def import_results(entries, out, settings, input_hashes=None):
    for relative, digest in (input_hashes or {}).items():
        if checksum(path_under(OPS, relative).read_bytes()) != digest:
            raise ValueError('transported input changed during remote verification')
    payload = json.loads((out / 'result.json').read_text())
    expected = {entry['ticket_id']: entry for entry in entries}
    results = payload.get('ticket_results', {})
    if set(results) != set(expected):
        raise ValueError('remote results do not match the submitted batch')
    validated = []
    for ticket_id, result in results.items():
        entry = expected[ticket_id]
        proposal = load_proposal(path_under(OPS, entry['proposal']),
                                 path_under(OPS, entry['ticket_path']), entry['identity'])
        if result.get('status') == 'verification_pending':
            if result.get('proposal') != entry['proposal']:
                raise ValueError('remote fallback changed proposal identity')
            # A failed standalone check must go to the original local repair
            # harness rather than repeat unchanged on a remote slot forever.
            if result.get('verification_isolate') and len(entries) == 1:
                result['verification_remote_failed'] = True
            continue
        if result.get('status') != 'accepted_for_dependent_observation':
            raise ValueError('unexpected remote verdict')
        receipt_path = path_under(out, result['receipt'])
        receipt = json.loads(receipt_path.read_text())
        execution = receipt.get('execution', {})
        ticket = json.loads(path_under(OPS, entry['ticket_path']).read_text())
        if (receipt.get('schema') != 'factory.observation-receipt/v1'
                or receipt.get('outcome') != result['status']
                or receipt.get('ticket', {}).get('id') != ticket_id
                or receipt['ticket'].get('sha256') != proposal['ticket_sha256']
                or execution.get('source_revision') != proposal['source_revision']
                or set(execution.get('verified_ticket_ids', [])) != set(expected)
                or not execution.get('verified_tree')
                or not receipt.get('gates')
                or any(gate.get('outcome') != 'passed' for gate in receipt['gates'])):
            raise ValueError('remote receipt failed pinned identity or gate validation')
        for index, command in enumerate(ticket.get('gates', [])):
            if not any(g.get('id') == 'ticket-gate-%d' % index and g.get('command') == command
                       for g in receipt['gates']):
                raise ValueError('remote receipt omitted a required gate')
        for key in ('worker', 'model', 'profile'):
            field = 'resolved_model' if key == 'model' else key
            if receipt.get('model', {}).get(field) != entry['identity'][key]:
                raise ValueError('remote receipt changed worker identity')
        for artifact in receipt.get('raw_artifacts', []):
            if checksum(path_under(OPS, artifact['path']).read_bytes()) != artifact['sha256']:
                raise ValueError('remote input artifact hash mismatch')
        patch_relative = execution['candidate_patch']
        patch = path_under(out, patch_relative).read_bytes()
        if checksum(patch) != execution.get('candidate_patch_sha256'):
            raise ValueError('remote patch hash mismatch')
        if (Path(result['receipt']).parent != Path('docs/factory-ng/runs')
                or not Path(result['receipt']).name.endswith('.json')
                or Path(patch_relative).parent != Path('docs/factory-ng/candidates')
                or not Path(patch_relative).name.startswith('focused-')):
            raise ValueError('remote output has an unexpected destination')
        execution['verification_host'] = settings['host']
        execution['verification_image'] = settings['image']
        execution['verification_slot'] = settings.get('slot', 0)
        execution['verification_cpus'] = settings.get('cpus', [])
        known = {a['path'] for a in receipt.get('raw_artifacts', [])}
        receipt.setdefault('raw_artifacts', []).extend(
            {'path': relative, 'sha256': digest, 'kind': 'remote_verification_input'}
            for relative, digest in (input_hashes or {}).items() if relative not in known)
        validated.append((result['receipt'], receipt, patch_relative, patch))
    # Validate the complete batch before publishing anything to reconciliation.
    for relative, receipt, patch_relative, patch in validated:
        dest = path_under(OPS, patch_relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as handle:
            handle.write(patch)
        receipt_dest = path_under(OPS, relative)
        receipt_dest.parent.mkdir(parents=True, exist_ok=True)
        write_receipt(receipt_dest, receipt)
    return payload


def verify(entries, settings):
    job_id = 'verify-' + uuid.uuid4().hex
    remote = settings['root'].rstrip('/') + '/jobs/' + job_id
    failed = None
    try:
        require_compilation()
        with tempfile.TemporaryDirectory(prefix='factory-ng-remote-') as tmp:
            staging = Path(tmp)
            revision = export_job(entries, staging, settings)
            mirror = settings['root'].rstrip('/') + '/source.git'
            try:
                ssh(settings, ['git', '-C', mirror, 'cat-file', '-e', revision + '^{commit}'])
            except subprocess.CalledProcessError:
                export_source_bundle(staging, revision, settings, mirror)
            ssh(settings, ['mkdir', '-p', remote])
            invoke(['rsync', '-a', str(staging) + '/', settings['host'] + ':' + remote + '/'])
            require_compilation()
            command = ['python3', remote + '/ops/scripts/factory-ng-remote-host.py', remote]
            with (staging / 'ssh.log').open('w') as log:
                process = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                                            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                                            settings['host'], shlex.join(command)], stdout=log, stderr=log)
                last_policy = None
                started = time.monotonic()
                try:
                    while process.poll() is None:
                        if time.monotonic() - started > 11100:
                            raise TimeoutError('remote verification exceeded three hours')
                        current = POLICY.read_bytes()
                        if current != last_policy:
                            write_remote_policy(staging / 'ops', settings)
                            invoke(['rsync', '-a', staging / 'ops/config/factory-ng-policy.json',
                                    settings['host'] + ':' + remote + '/ops/config/'])
                            last_policy = current
                        time.sleep(3)
                    if process.returncode:
                        raise RuntimeError('remote verifier failed: ' + (staging / 'ssh.log').read_text()[-2000:])
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try: process.wait(timeout=10)
                        except subprocess.TimeoutExpired: process.kill(); process.wait()
            invoke(['rsync', '-a', settings['host'] + ':' + remote + '/out/', str(staging / 'out') + '/'])
            payload = import_results(entries, staging / 'out', settings,
                                     json.loads((staging / 'input-checksums.json').read_text()))
            return payload
    except Exception as exc:
        failed = str(exc)[-2400:]
        return {'ticket_results': {entry['ticket_id']: {
            'status': 'verification_pending', 'proposal': entry['proposal'],
            'verification_remote_failed': True, 'reason': 'Remote verification unavailable; retained for local checks: ' + failed}
            for entry in entries}}
    finally:
        state = {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                 'host': settings['host'], 'error': failed,
                 'retry_after_epoch': int(time.time()) + 300 if failed else 0}
        with STATUS.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if STATUS.exists():
                previous = json.loads(STATUS.read_text())
                state['retry_after_epoch'] = max(state['retry_after_epoch'], previous.get('retry_after_epoch', 0))
            temp = STATUS.with_suffix('.tmp'); temp.write_text(json.dumps(state)); os.replace(temp, STATUS)
        with contextlib.suppress(Exception):
            ssh(settings, ['podman', 'rm', '--force', '--ignore', 'factory-ng-' + job_id])
            ssh(settings, ['rm', '-rf', '--', remote])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--slot', type=int, default=0)
    args = parser.parse_args()
    settings = json.loads(POLICY.read_text())['verification']['remote']
    slots = max(1, min(4, int(settings.get('slots', 1))))
    if not 0 <= args.slot < slots or len(settings['cpus']) < slots:
        raise SystemExit('invalid remote slot allocation')
    settings = dict(settings, slot=args.slot,
                    cpus=settings['cpus'][args.slot * len(settings['cpus']) // slots:
                                          (args.slot + 1) * len(settings['cpus']) // slots])
    settings['go_parallelism'] = min(settings['go_parallelism'], len(settings['cpus']))
    print(json.dumps(verify(json.loads(args.manifest.read_text()), settings)))


if __name__ == '__main__':
    main()
