"""Recognize an evidence-only failure before granting one fresh context packet."""
import hashlib
import json
import re

from factory_ng_investigation import evidence_gap, STAGED

CONTEXT_VERSION = 'python-handoff-v2'


def historical_evidence_gap(reply):
    """Normalize old evidence receipts without widening the live helper API.

    Older replies could list more than eight inspected locations. Recovery
    replays their original bounded NEEDs; it does not invoke an investigator.
    Keep the full response immutable and validate a bounded projection here.
    """
    gap = evidence_gap({'stdout': reply, 'exit_code': 0}, STAGED)
    if gap:
        return gap
    match = re.fullmatch(r'\s*EVIDENCE_GAP:\s*(\{[^\n]*\})\s*', reply)
    if not match:
        return None
    try:
        value = json.loads(match[1])
    except ValueError:
        return None
    searched = value.get('searched') if isinstance(value, dict) else None
    if not isinstance(searched, list) or not 9 <= len(searched) <= 32 or not all(isinstance(s, str) and s.strip() for s in searched):
        return None
    value['searched'] = searched[:8]
    return evidence_gap({'stdout': 'EVIDENCE_GAP: ' + json.dumps(value), 'exit_code': 0}, STAGED)


def valid_context_successor(ops, successor, job, original, tickets):
    from factory_ng_recovery import map_repair_history, MAP_REPAIR_LIMIT
    if (successor.get('supersedes') != original.get('id')
            or successor.get('production', {}).get('context_repair_version') != CONTEXT_VERSION):
        return False
    history = map_repair_history(original, tickets)
    if history['error'] or history['generation'] >= MAP_REPAIR_LIMIT:
        return False
    try:
        observation = json.loads((ops / job['receipt']).read_text())
        ticket_bytes = (ops / job['ticket_path']).read_bytes()
    except (OSError, ValueError, KeyError):
        return False
    if observation.get('ticket', {}).get('sha256') != 'sha256:' + hashlib.sha256(ticket_bytes).hexdigest():
        return False
    requests = context_repair_requests(ops, observation, original, history, tickets)
    return bool(requests and successor.get('execution', {}).get('context_requests') == requests
                and successor['production'].get('integration_repair_generation') == history['generation'] + 1
                and successor.get('scope') == original.get('scope')
                and successor.get('gates') == original.get('gates')
                and all(rule in successor.get('required_behavior', []) for rule in original.get('required_behavior', []))
                and all(successor.get('execution', {}).get(key) == original.get('execution', {}).get(key)
                        for key in ('profile_policy', 'compatible_profiles', 'selected_profile')))


def park_legacy_context_failure(ops, job, original, tickets):
    """A confirmed evidence gap cannot use a generic same-packet retry."""
    if (job.get('state') not in ('queued', 'failed')
            or job.get('outcome') != 'infrastructure_failed_model_protocol'
            or not job.get('receipt') or job.get('context_failure_receipt') == job['receipt']):
        return False
    try:
        observation = json.loads((ops / job['receipt']).read_text())
        ticket_bytes = (ops / job['ticket_path']).read_bytes()
    except (OSError, ValueError, KeyError):
        return False
    if observation.get('ticket', {}).get('sha256') != 'sha256:' + hashlib.sha256(ticket_bytes).hexdigest():
        return False
    from factory_ng_recovery import map_repair_history
    history = map_repair_history(original, tickets)
    if history['error'] or not context_repair_requests(ops, observation, original, history, tickets):
        return False
    job['state'] = 'parked'
    job['context_failure_receipt'] = job['receipt']
    job['waiting_reason'] = 'Recorded missing-source failure; waiting for a bounded fresh context packet.'
    job.pop('retry_after_epoch', None)
    return True


def context_repair_requests(ops, observation, original, history, tickets):
    if observation.get('model', {}).get('profile') != STAGED:
        return []
    if observation.get('outcome') not in ('parked', 'infrastructure_failed_model_protocol'):
        return []
    if observation.get('execution', {}).get('candidate_patch'):
        return []
    if any(tickets[k].get('production', {}).get('context_repair_version') == CONTEXT_VERSION
           for k in history['ancestors']):
        return []
    replies = []
    for item in observation.get('raw_artifacts', []):
        if item.get('kind') not in (None, 'bounded_repair', 'need_continuation'):
            continue
        relative = item.get('path', '')
        path = (ops / relative).resolve()
        if not path.is_relative_to((ops / 'docs/factory-ng/runs').resolve()) or not path.is_file():
            return []
        raw = path.read_bytes()
        if len(raw) > 2_000_000 or 'sha256:' + hashlib.sha256(raw).hexdigest() != item.get('sha256'):
            return []
        try:
            decoded = json.loads(raw)
        except ValueError:
            decoded = raw.decode(errors='replace')
        reply = decoded.get('result', '') if isinstance(decoded, dict) else decoded
        if not isinstance(reply, str) or re.search(r'<<<(?:FILE|NEWFILE)|VERDICT:\s*(?:NEEDS_PRIMITIVE|SEMANTIC_GAP)', reply):
            return []
        replies.append(reply)
    if not replies:
        return []
    requests = re.findall(r'^NEED:\s*(.+?)\s*$', replies[0], re.M)[:3]
    if not requests:
        return []
    # Old Map runners rejected NEED as malformed before attempting source
    # resolution. Later runners may explicitly report an unresolved gap.
    rejected_need = (not observation.get('model', {}).get('telemetry', {}).get('need_continuation_attempted')
                     and any(g.get('id') == 'initial-patch-apply' and 'no edit blocks' in g.get('detail', '')
                             for g in observation.get('gates', [])))
    explicit_gap = observation.get('evidence_failure') or any(
        historical_evidence_gap(reply)
        for reply in replies[1:] if reply.startswith('EVIDENCE_GAP:'))
    return [request[:2000] for request in requests] if rejected_need or explicit_gap else []
