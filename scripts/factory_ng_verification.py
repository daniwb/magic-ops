"""Durable untested proposals. These are never accepted observation receipts."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import uuid
from factory_ng_quiet import compilation_status, POLICY


class VerificationPaused(Exception):
    pass


def require_compilation():
    settings = json.loads(POLICY.read_text())
    if not compilation_status(settings)['allowed']:
        raise VerificationPaused('Compilation and testing are switched off on the dashboard.')


def checksum(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def normalize_go(clone, ticket, changed):
    """Format only scope-checked regular Go files; never compile or run tests."""
    root = Path(clone).resolve()
    if not set(changed).issubset(set(ticket['scope']['allowed_paths'])):
        raise ValueError('formatting candidate exceeds TicketSpec scope')
    paths = []
    for name in changed:
        path = root / name
        if not name.endswith('.go') or not path.exists():
            continue
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('unsafe Go formatting path: ' + name)
        paths.append(name)
    if not paths:
        return None
    formatter = shutil.which('gofmt') or '/usr/local/go/bin/gofmt'
    result = subprocess.run([formatter, '-w', *paths], cwd=root, capture_output=True,
                            text=True, timeout=60)
    return {'id': 'go-format', 'outcome': 'passed' if result.returncode == 0 else 'failed',
            'detail': (result.stdout + result.stderr).strip() or 'Formatted: ' + ','.join(paths)}


def save_proposal(directory, clone, ticket_path, identity, context):
    """Keep a binary-safe diff and pinned contract; release the disposable clone."""
    clone, ticket_path = Path(clone), Path(ticket_path)
    ticket = json.loads(ticket_path.read_text())
    subprocess.run(['git', 'add', '-A'], cwd=clone, check=True, capture_output=True)
    names = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z', 'HEAD'], cwd=clone).decode().split('\0')
    if not set(filter(None, names)).issubset(set(ticket['scope']['allowed_paths'])):
        raise ValueError('untested proposal exceeds TicketSpec scope')
    formatting = normalize_go(clone, ticket, list(filter(None, names)))
    if formatting:
        context = dict(context, formatting=formatting)
        subprocess.run(['git', 'add', '-A'], cwd=clone, check=True, capture_output=True)
    patch = subprocess.check_output(['git', 'diff', '--cached', '--binary', '--full-index', 'HEAD'], cwd=clone)
    if not patch:
        raise ValueError('cannot save an empty proposal')
    value = {'schema': 'factory.untested-proposal/v1', 'ticket_id': ticket['id'],
             'ticket_sha256': checksum(ticket_path.read_bytes()),
             'source_revision': ticket['source']['revision'], 'identity': identity,
             'patch': patch.decode(), 'patch_sha256': checksum(patch), 'context': context}
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('proposal-' + uuid.uuid4().hex + '.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary, path)
    return path


def load_proposal(path, ticket_path, identity):
    value = json.loads(Path(path).read_text())
    ticket = json.loads(Path(ticket_path).read_text())
    if (value.get('schema') != 'factory.untested-proposal/v1'
            or value.get('ticket_id') != ticket['id']
            or value.get('ticket_sha256') != checksum(Path(ticket_path).read_bytes())
            or value.get('source_revision') != ticket['source']['revision']
            or value.get('identity') != identity
            or value.get('patch_sha256') != checksum(value['patch'].encode())):
        raise ValueError('saved proposal identity, contract or patch integrity mismatch')
    return value


def restore_proposal(value, clone):
    subprocess.run(['git', 'apply', '--index', '--binary', '-'], cwd=clone,
                   input=value['patch'], text=True, check=True, capture_output=True)
    return value['context']


def singleton_repair_evidence(ops, result_path, ticket_path, proposal_path, identity):
    """Bind a singleton compile/test failure, never a passed gate.

    Ambiguous batch failures, transport errors, changed identities and corrupt
    artifacts fall back to ordinary verification. This guides a remaining
    correction or records terminal failure when its budget is spent. Every
    corrected candidate must still run its entire gate list.
    """
    try:
        ops = Path(ops).resolve()
        result_path = Path(result_path).resolve()
        if not result_path.is_relative_to(ops / 'state/factory-ng-job-output'):
            return None
        manifest_path = result_path.with_suffix('.manifest.json')
        raw, manifest_raw = result_path.read_bytes(), manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        proposal = load_proposal(proposal_path, ticket_path, identity)
        key = proposal['ticket_id']
        expected = {'ticket_id': key, 'ticket_path': str(Path(ticket_path).resolve().relative_to(ops)),
                    'proposal': str(Path(proposal_path).resolve().relative_to(ops)), 'identity': identity}
        if manifest != [expected]:
            return None
        members = json.loads(raw).get('ticket_results', {})
        if set(members) != {key}:
            return None
        result = members[key]
        reason = result.get('reason', '')
        if (result.get('status') != 'verification_pending' or not result.get('verification_isolate')
                or not result.get('verification_remote_failed') or result.get('proposal') != expected['proposal']
                or not reason.startswith('Batch could not pass; verify individually: ' + key + ': ')
                or any(marker in reason.lower() for marker in
                       ('panic: test timed out', 'context deadline exceeded', 'signal: killed'))):
            return None
        kind = 'compile' if re.search(r'(?m)^FAIL\s+magic-backend/(?:game|cards)\s+\[build failed\]', reason) else None
        if kind is None:
            ticket = json.loads(Path(ticket_path).read_text())
            failed_tests = re.findall(r'(?m)^--- FAIL: (Test[A-Za-z0-9_]+)(?:/[^ ]+)? \(', reason)
            if any(re.search(r'\b' + re.escape(name) + r'\b', command)
                   for name in failed_tests for command in ticket.get('gates', []) if 'go test' in command):
                kind = 'test'
        if kind is None:
            return None
        return {'schema': 'factory.singleton-repair-evidence/v1', 'manifest': manifest, 'failure_kind': kind,
                'result': json.loads(raw), 'result_sha256': checksum(raw),
                'manifest_sha256': checksum(manifest_raw), 'ticket_sha256': proposal['ticket_sha256'],
                'proposal_sha256': checksum(Path(proposal_path).read_bytes()),
                'patch_sha256': proposal['patch_sha256'], 'source_revision': proposal['source_revision'],
                'failure': {'id': 'prior-remote-' + kind + '-failure', 'outcome': 'failed', 'detail': reason}}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def repair_artifacts(ops, context):
    """Validate only harness-recorded public repair evidence before transport."""
    root = Path(ops).resolve()
    artifacts = context.get('repair_artifacts', [])
    if not isinstance(artifacts, list):
        raise ValueError('invalid repair artifact list')
    for artifact in artifacts:
        path = (root / artifact['path']).resolve()
        if (not path.is_relative_to(root / 'docs/factory-ng/runs')
                or checksum(path.read_bytes()) != artifact.get('sha256')):
            raise ValueError('repair artifact path or hash mismatch')
    return artifacts


def corrected_proposal_can_reverify(ops, job, new_path):
    """Only a new, hash-linked correction may clear an old remote failure."""
    try:
        root = Path(ops).resolve()
        old_path, new_path = root / job['proposal'], root / new_path
        if not all(p.resolve().is_relative_to(root) for p in (old_path, new_path)):
            return False
        identity = {'worker': job['worker'], 'profile': job['dispatch_profile'], 'model': job['model']}
        old = load_proposal(old_path, root / job['ticket_path'], identity)
        new = load_proposal(new_path, root / job['ticket_path'], identity)
        context = new['context']
        return (new_path != old_path and old['patch_sha256'] != new['patch_sha256']
                and not old['context'].get('telemetry', {}).get('bounded_repair_attempted')
                and context.get('telemetry', {}).get('bounded_repair_attempted') is True
                and context.get('telemetry', {}).get('gate_repair_attempted') is True
                and context.get('repair_parent') == {'proposal': job['proposal'],
                                                       'sha256': checksum(old_path.read_bytes())}
                and any(g.get('id') == 'gate-repair-apply' and g.get('outcome') == 'passed'
                        for g in context.get('gates', [])))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def recover_bundle_export_fallbacks(ops, jobs, now):
    """One transport retry after replacing repeated full-history bundle export."""
    ops = Path(ops).resolve()
    recovered = []
    for key, job in jobs.items():
        if (job.get('state') != 'awaiting_verification' or job.get('superseded_by')
                or not job.get('verification_remote_failed')
                or job.get('remote_bundle_export_recovery', {}).get('proposal') == job.get('proposal')):
            continue
        try:
            path = (ops / job['result_path']).resolve()
            if not path.is_relative_to(ops / 'state/factory-ng-job-output'):
                continue
            raw = path.read_bytes()
            members = json.loads(raw).get('ticket_results', {})
            result = members.get(key, {})
            reason = result.get('reason', '')
            identity = {'worker': job['worker'], 'profile': job['dispatch_profile'], 'model': job['model']}
            expected = {'ticket_id': key, 'ticket_path': job['ticket_path'],
                        'proposal': job['proposal'], 'identity': identity}
            manifest_raw = path.with_suffix('.manifest.json').read_bytes()
            manifest = json.loads(manifest_raw)
            if (result.get('status') != 'verification_pending' or not result.get('verification_remote_failed')
                    or result.get('proposal') != job['proposal']
                    or not reason.startswith('Remote verification unavailable; retained for local checks: ')
                    or "'bundle', 'create'" not in reason or 'timed out after 300 seconds' not in reason
                    or len(manifest) != len(members) or {e['ticket_id'] for e in manifest} != set(members)
                    or [e for e in manifest if e['ticket_id'] == key] != [expected]):
                continue
            proposal = ops / job['proposal']
            load_proposal(proposal, ops / job['ticket_path'], identity)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        job.pop('verification_remote_failed')
        job['remote_bundle_export_recovery'] = {'proposal': job['proposal'],
            'proposal_sha256': checksum(proposal.read_bytes()), 'result_path': job['result_path'],
            'result_sha256': checksum(raw), 'manifest_sha256': checksum(manifest_raw), 'recovered_at': now}
        job['waiting_reason'] = 'Pinned bundle export repaired; one remote transport retry is eligible.'
        job['updated_at'] = now
        recovered.append(key)
    return recovered


def recover_remote_batch_fallbacks(ops, jobs, now):
    """Undo only the old multi-member failure attribution, without a model retry."""
    recovered = []
    for key, job in jobs.items():
        if (job.get('state') != 'awaiting_verification' or job.get('superseded_by')
                or not job.get('verification_remote_failed') or not job.get('verification_isolate')
                or job.get('remote_batch_isolation_recovery', {}).get('proposal') == job.get('proposal')):
            continue
        try:
            path = (ops / job['result_path']).resolve()
            if not path.is_relative_to((ops / 'state/factory-ng-job-output').resolve()):
                continue
            raw = path.read_bytes()
            members = json.loads(raw).get('ticket_results', {})
            result = members.get(key, {})
            if (len(members) <= 1 or result.get('status') != 'verification_pending'
                    or not result.get('verification_isolate')
                    or not result.get('reason', '').startswith('Batch could not pass; verify individually:')
                    or result.get('proposal') != job.get('proposal')):
                continue
            # The saved patch, contract and original author/model must still
            # match. No receipt, attempt, failed profile or repair budget moves.
            load_proposal(ops / job['proposal'], ops / job['ticket_path'],
                          {'worker': job['worker'], 'profile': job['dispatch_profile'], 'model': job['model']})
        except (OSError, ValueError, KeyError, TypeError):
            continue
        job.pop('verification_remote_failed')
        job['remote_batch_isolation_recovery'] = {'proposal': job['proposal'],
            'result_path': job['result_path'], 'result_sha256': checksum(raw), 'recovered_at': now}
        job['waiting_reason'] = 'Multi-member failure requires individual verification; remote slot remains eligible.'
        job['updated_at'] = now
        recovered.append(key)
    return recovered
