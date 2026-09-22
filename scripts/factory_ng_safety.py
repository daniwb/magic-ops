"""Shared preflight and final-candidate checks for Factory NG harnesses."""
import json
import os
import re
import shlex
import subprocess
import hashlib
import time
from pathlib import Path
from factory_ng_receipts import write_receipt


def source_wait_receipt(ticket_path, ticket, worker, profile, model, runs, ops, reason):
    """A busy canonical checkout is a zero-model wait, not a failed attempt."""
    runs.mkdir(parents=True, exist_ok=True)
    slug = ticket['id'].removeprefix('ticket:').replace('/', '-').replace('.', '-')
    path = runs / (time.strftime('%Y-%m-%dT%H%M%SZ', time.gmtime()) + '-' + slug + '-source-wait-' + str(time.time_ns()) + '.json')
    value = {'schema': 'factory.observation-receipt/v1',
             'ticket': {'id': ticket['id'], 'path': str(ticket_path.relative_to(ops)),
                        'sha256': 'sha256:' + hashlib.sha256(ticket_path.read_bytes()).hexdigest()},
             'skill': ticket.get('skill', {}),
             'model': {'profile': profile, 'resolved_model': model, 'worker': worker,
                       'telemetry': {key: 0 for key in ('input_tokens', 'output_tokens', 'cache_read_tokens',
                                                       'cache_write_tokens', 'model_calls', 'elapsed_ms')}},
             'execution': {'model_called': False, 'source_revision': ticket['source']['revision'],
                           'source_tree_changed': False},
             'gates': [{'id': 'source-preflight', 'outcome': 'deferred', 'detail': reason}],
             'outcome': 'source_unavailable', 'reason': reason, 'integration': 'observation_only',
             'next_action': 'Wait for a clean available source; this did not consume a model attempt.'}
    write_receipt(path, value)
    return {'status': 'source_unavailable', 'ticket_id': ticket['id'], 'worker': worker,
            'receipt': str(path.relative_to(ops)), 'model_called': False, 'reason': reason}


def source_problem(repo):
    """Empty porcelain alone does not rule out an unfinished Git operation."""
    try:
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=repo,
                                capture_output=True, text=True, timeout=30,
                                env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
        if status.returncode:
            return 'git status failed: ' + status.stderr.strip()
        if status.stdout.strip():
            return 'canonical integration checkout is dirty'
        for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD',
                     'rebase-merge', 'rebase-apply', 'sequencer', 'index.lock'):
            result = subprocess.run(['git', 'rev-parse', '--git-path', name], cwd=repo,
                                    capture_output=True, text=True, timeout=10)
            if result.returncode:
                return 'cannot resolve Git operation state: ' + result.stderr.strip()
            path = Path(result.stdout.strip())
            if not path.is_absolute():
                path = Path(repo) / path
            if path.exists():
                return 'canonical checkout has unfinished Git operation: ' + name
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 'canonical checkout unavailable: ' + str(exc)
    return ''


def final_gates_pass(gates):
    """Keep failed attempt history, but judge the final candidate's checks."""
    current = [g for g in gates if g.get('id') != 'initial-patch-apply']
    return bool(current) and all(g.get('outcome') == 'passed' for g in current)


def named_test_pattern(command):
    if not re.search(r'\bgo\s+test\b', command):
        return None
    words = shlex.split(command)
    for i, word in enumerate(words):
        if word == '-run' and i + 1 < len(words):
            return words[i + 1]
        if word.startswith('-run='):
            return word.split('=', 1)[1]
    return None


def test_json_command(command):
    if named_test_pattern(command) is not None:
        return re.sub(r'\bgo\s+test\b', 'go test -json', command, count=1)
    return command


def require_executed_test(command, result):
    pattern = named_test_pattern(command)
    if pattern is None or result['exit_code'] != 0:
        return result
    passed = []
    for line in result['stdout'].splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get('Action') == 'pass' and event.get('Test'):
            passed.append(event['Test'])
    # go test itself applies Go's regex/subtest matching rules. A package pass
    # or a skipped test is not proof that any selected test actually passed.
    if not passed:
        result['exit_code'] = 1
        result['stderr'] += '\nrequired test filter %r executed no passing tests' % pattern
        result['stderr'] += ('\nProvide the required named behavioral test with the original assertions; '
                             'do not remove or weaken the selector, or substitute a package-only pass.')
    else:
        result['stdout'] += '\nNamed test gate: %d test(s) passed for %r\n' % (len(passed), pattern)
    return result


def decoded_output(value):
    return value.decode(errors='replace') if isinstance(value, bytes) else (value or '')
