#!/usr/bin/env python3
"""Verify saved proposals on one composition; no model, push or canonical writes.

Per-ticket patches retain their original base. Acceptance records the actual
composed tree; integration must revalidate every included ticket on its final tree.
A rejected composition returns all proposals to the existing individual harness.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from factory_ng_receipts import write_receipt
from factory_ng_safety import source_problem
from factory_ng_verification import load_proposal, checksum, require_compilation, VerificationPaused, normalize_go, repair_artifacts

OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE


def runner():
    spec = importlib.util.spec_from_file_location('batch_gate_runner', OPS / 'scripts/factory-ng-run-engine-ticket.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, *args, stdin=None):
    return subprocess.run(['git', *args], cwd=repo, input=stdin, text=True,
                          capture_output=True, check=True, timeout=120).stdout


def scope_command(command):
    return ((command.startswith('git status --porcelain ') or command.startswith('git diff --name-only '))
            and ' only ' in command)


def verify(entries, gate_runner=None):
    batch_id = uuid.uuid4().hex
    results = {}
    # The fallback keeps original proposal paths, model attempts and repair budgets.
    def pending(reason, isolate=False):
        return {'ticket_results': {entry['ticket_id']: {
            'status': 'verification_pending', 'proposal': entry['proposal'],
            'reason': reason, 'verification_isolate': isolate} for entry in entries}}
    try:
        require_compilation()
        problem = source_problem(SOURCE)
        if problem:
            return pending(problem)
        m = gate_runner or runner()
        prepared = []
        with tempfile.TemporaryDirectory(prefix='factory-ng-focused-') as tmp:
            root = Path(tmp)
            composed = root / 'composed'
            git(root, 'clone', '--quiet', '--shared', str(SOURCE), str(composed))
            isolated = root / 'individual-scope'
            git(root, 'clone', '--quiet', '--shared', str(SOURCE), str(isolated))
            source_revision = None
            # Check scope and export each patch against its own pinned base before
            # composition. Never broaden a ticket's scope to the batch's union.
            for index, entry in enumerate(entries):
                path = OPS / entry['ticket_path']
                ticket = json.loads(path.read_text())
                if ticket['id'] != entry['ticket_id']:
                    raise ValueError('manifest TicketSpec identity mismatch')
                proposal = load_proposal(OPS / entry['proposal'], path, entry['identity'])
                revision = proposal['source_revision']
                if source_revision is None:
                    source_revision = revision
                    git(composed, 'checkout', '--quiet', '--detach', revision)
                elif revision != source_revision:
                    raise ValueError('batch proposals have different source revisions')
                git(isolated, 'reset', '--hard', revision)
                problems = m.preparation_problems(ticket, isolated)
                if problems:
                    raise ValueError('pinned preparation contract failed: ' + str(problems))
                git(isolated, 'apply', '--index', '--binary', '-', stdin=proposal['patch'])
                names = list(filter(None, git(isolated, 'diff', '--cached', '--name-only', '-z', 'HEAD').split('\0')))
                if not names or not set(names).issubset(ticket['scope']['allowed_paths']):
                    raise ValueError('proposal exceeds individual TicketSpec scope')
                formatting = normalize_go(isolated, ticket, names)
                if formatting:
                    if formatting['outcome'] != 'passed':
                        raise ValueError('proposal Go formatting failed: ' + formatting['detail'])
                    git(isolated, 'add', '--', *names)
                git(isolated, 'diff', '--cached', '--check')
                gates = [{'id': 'scope', 'outcome': 'passed', 'detail': 'changed=' + ','.join(names)},
                         {'id': 'diff-check', 'outcome': 'passed'}]
                if formatting:
                    gates.append(formatting)
                git(isolated, '-c', 'user.name=Factory NG', '-c', 'user.email=factory-ng@local',
                    'commit', '--quiet', '-m', 'factory-ng: focused batch proposal')
                patch = git(isolated, 'format-patch', '-1', '--stdout', 'HEAD')
                commit = git(isolated, 'rev-parse', 'HEAD').strip()
                git(composed, '-c', 'user.name=Factory NG', '-c', 'user.email=factory-ng@local',
                    'am', '--3way', stdin=patch)
                prepared.append((entry, path, ticket, proposal, gates, patch, commit, names))
            tree = git(composed, 'rev-parse', 'HEAD^{tree}').strip()
            # All semantic checks see exactly this composition. Go's content cache
            # reuses the compiled packages/test executable across test selectors.
            shared_results = {}
            for entry, path, ticket, proposal, gates, patch, commit, names in prepared:
                require_compilation()
                if ticket.get('work_type') == 'engine' and 'backend/game/ability_effects.go' in names:
                    gates.append(m.engine_registration_gate(ticket, composed))
                    if gates[-1]['outcome'] != 'passed':
                        raise ValueError('composed engine registration check failed')
                for index, command in enumerate(ticket.get('gates', [])):
                    if scope_command(command) or command == 'git diff --check':
                        gates.append({'id': 'ticket-gate-%d' % index, 'command': command,
                                      'outcome': 'passed', 'detail': 'Checked against the individual patch before composition.'})
                        continue
                    require_compilation()
                    # Reuse identical simple test invocations only. Measurements
                    # and arbitrary shell commands retain per-ticket execution.
                    reusable = bool(re.fullmatch(r'(?:cd [\w./-]+ && )?(?:go test|python3? -m unittest) [\w./= \-]+', command))
                    key = (ticket.get('work_type'), command)
                    reused = reusable and key in shared_results
                    result = shared_results[key] if reused else m.ticket_gate(command, composed, ticket)
                    if reusable:
                        shared_results[key] = result
                    checked = {'id': 'ticket-gate-%d' % index, 'command': command,
                               'outcome': 'passed' if result['exit_code'] == 0 else 'failed',
                               'elapsed_ms': result['elapsed_ms'], 'detail': m.failure_detail(result)}
                    if reused:
                        checked.update(reused_from_batch=batch_id, elapsed_ms=0)
                    gates.append(checked)
                    if result['exit_code']:
                        raise ValueError('%s: %s' % (ticket['id'], checked['detail']))
                # A gate may create ignored artifacts, but cannot change tested code.
                if git(composed, 'status', '--porcelain').strip() or git(composed, 'rev-parse', 'HEAD^{tree}').strip() != tree:
                    raise ValueError('focused gate changed the composed source tree')
            require_compilation()
            # Publish only after EVERY member passes, never after a partial batch.
            for entry, path, ticket, proposal, gates, patch, commit, names in prepared:
                candidates = OPS / 'docs/factory-ng/candidates'; candidates.mkdir(parents=True, exist_ok=True)
                runs = OPS / 'docs/factory-ng/runs'; runs.mkdir(parents=True, exist_ok=True)
                suffix = batch_id + '-' + str(len(results))
                patch_path = candidates / ('focused-' + suffix + '.patch')
                patch_path.write_text(patch)
                receipt_path = runs / (time.strftime('%Y-%m-%dT%H%M%SZ', time.gmtime()) + '-focused-' + suffix + '.json')
                identity, context = proposal['identity'], proposal['context']
                artifacts = [{'path': entry['proposal'], 'sha256': checksum((OPS / entry['proposal']).read_bytes()), 'kind': 'saved_proposal'}]
                artifacts.extend(repair_artifacts(OPS, context))
                if context.get('raw_path'):
                    raw = OPS / context['raw_path']
                    artifacts.append({'path': context['raw_path'], 'sha256': checksum(raw.read_bytes())})
                value = {'schema': 'factory.observation-receipt/v1',
                         'ticket': {'id': ticket['id'], 'path': str(path.relative_to(OPS)), 'sha256': proposal['ticket_sha256']},
                         'skill': ticket.get('skill', {}),
                         'model': {'profile': identity['profile'], 'resolved_model': identity['model'],
                                   'worker': identity['worker'], 'telemetry': dict(context.get('telemetry', {}),
                                       model_calls=context.get('model_calls', context.get('telemetry', {}).get('model_calls', 0)))},
                         'execution': {'mode': 'isolated_composed_verification', 'source_revision': source_revision,
                                       'source_tree_changed': False, 'candidate_commit': commit,
                                       'candidate_patch': str(patch_path.relative_to(OPS)),
                                       'candidate_patch_sha256': checksum(patch_path.read_bytes()),
                                       'verification_batch': batch_id, 'verified_tree': tree,
                                       'verified_ticket_ids': [item['ticket_id'] for item in entries]},
                         'raw_artifacts': artifacts, 'gates': gates,
                         'attempt_history': context.get('attempt_history', []),
                         'outcome': 'accepted_for_dependent_observation', 'integration': 'eligible_full_gate',
                         'next_action': 'Revalidate every included contract on the final integration composition.'}
                write_receipt(receipt_path, value)
                results[ticket['id']] = {'status': value['outcome'], 'receipt': str(receipt_path.relative_to(OPS))}
            return {'ticket_results': results}
    except VerificationPaused as exc:
        return pending(str(exc))
    except Exception as exc:
        # Includes conflicting patches, missing tests, corrupt proposals, and
        # infrastructure errors. Individual resume retains its bounded repair.
        result = pending('Batch could not pass; verify individually: ' + str(exc)[-1600:], True)
        result['ticket_results'].update(results)  # preserve any already published receipts
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(json.loads(args.manifest.read_text()))))


if __name__ == '__main__':
    main()
