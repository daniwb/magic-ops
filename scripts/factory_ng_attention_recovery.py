"""Finite operator-reviewed recovery; never reset attempts or edit receipts."""
import hashlib
import json

MANIFEST = 'docs/factory-ng/reviews/2026-09-15-needs-attention/worker-recovery.json'
ACTIVE = {'queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating'}


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def review_digest(review):
    return 'sha256:' + hashlib.sha256(json.dumps(review, sort_keys=True).encode()).hexdigest()


def pending(job):
    review = job.get('attention_recovery', {})
    return bool(review and int(job.get('attempts', 0)) == review['previous_attempts'])


def attempt_limit(job, ordinary):
    review = job.get('attention_recovery', {})
    return review['previous_attempts'] + 1 if review else ordinary


def failed_profiles(job):
    failed = set(job.get('failed_profiles') or [])
    if pending(job):
        failed.difference_update(job['attention_recovery']['profiles'])
    elif (job.get('state') == 'awaiting_verification' and job.get('proposal')
          and job.get('attention_recovery')
          and int(job.get('attempts', 0)) == job['attention_recovery']['previous_attempts'] + 1
          and job.get('dispatch_profile') in job['attention_recovery']['profiles']):
        # Saving a draft ends the lease, not its reviewed attempt. Its original
        # worker must still be able to verify/repair that exact proposal. Keep
        # history intact and never extend this exception to a fresh queued run.
        failed.discard(job['dispatch_profile'])
    return failed


def profiles(job, ordinary):
    if pending(job):
        return [p for p in ordinary if p in job['attention_recovery']['profiles']]
    return ordinary


def active_count(manifest, jobs):
    reviewed_ids = {item['ticket_id'] for item in manifest['tickets']}
    return sum(j.get('state') in ACTIVE and not j.get('superseded_by')
               and (j.get('attention_recovery', {}).get('batch') == manifest['batch']
                    or j.get('production', {}).get('attention_recovery_parent') in reviewed_ids)
               for j in jobs.values())


def dependency_admission(ops, jobs, payload):
    root = payload.get('ticket', {}).get('production', {}).get('attention_recovery_parent')
    if not root:
        return True
    manifest = json.loads((ops / MANIFEST).read_text())
    if root not in {item['ticket_id'] for item in manifest['tickets']}:
        return False
    # An immutable ticket already admitted consumes its existing slot.
    existing = jobs.get(payload.get('ticket_id'), {})
    if existing.get('state') in ACTIVE:
        return True
    return active_count(manifest, jobs) < min(6, manifest['max_active'])


def admit(ops, jobs, now, queue_limit=12, runnable_count=None):
    path = ops / MANIFEST
    if not path.exists():
        return 0
    manifest = json.loads(path.read_text())
    if manifest.get('schema') != 'factory.reviewed-attention-recovery/v1':
        raise ValueError('Invalid attention recovery manifest')
    batch = manifest['batch']
    active = active_count(manifest, jobs)
    queued = (runnable_count if runnable_count is not None else
              sum(j.get('state') == 'queued' and not j.get('superseded_by') for j in jobs.values()))
    # Leave one slot for a blocked review's producer. Otherwise dispatch-time
    # admission would refill every vacancy before the producer can admit its
    # prioritized dependency later in the same controller cycle.
    dependency_reserve = 1 if dependency_roots(jobs) else 0
    room = max(0, min(6, manifest['max_active']) - active - dependency_reserve)
    room = min(room, max(0, queue_limit - queued))
    admitted = 0
    for item in manifest['tickets']:
        if admitted >= room:
            break
        job = jobs.get(item['ticket_id'], {})
        prior = job.get('attention_recovery')
        followup = item.get('prior_recovery_sha256')
        if followup:
            # A changed-model transport recovery needs its own finite review,
            # bound to the prior review and new failure. It cannot replay the
            # original allowance or reopen a semantic failure.
            if (not prior or review_digest(prior) != followup
                    or not item.get('required_model') or item['required_model'] == job.get('model')
                    or item.get('reviewed_outcome') != job.get('outcome')
                    or job.get('outcome') not in ('infrastructure_failed_provider_capacity', 'infrastructure_failed')):
                continue
        elif prior:
            continue
        # A finite reviewed protocol fix may also cover deferred inventory.
        # Default manifests still admit failed jobs only. Bind the reviewed
        # state and exact protocol outcome; never reopen active or semantic work.
        reviewed_state = item.get('reviewed_state', 'failed')
        if reviewed_state not in ('failed', 'queued'):
            continue
        if reviewed_state == 'queued' and (job.get('outcome') != 'infrastructure_failed_model_protocol'
                or not set(item.get('profiles', [])).issubset(set(job.get('failed_profiles', [])))):
            continue
        if (job.get('state') != reviewed_state or job.get('superseded_by')
                or not str(job.get('outcome', '')).startswith('infrastructure_failed')
                or job.get('receipt') != item.get('receipt')
                or job.get('attempts', 0) != item['attempts']
                or job.get('started_at') != item.get('started_at')):
            continue
        evidence = ops / item['evidence_path']
        ticket = ops / job['ticket_path']
        if (not item.get('reason') or not item.get('profiles')
                or not evidence.is_file() or digest(evidence) != item['evidence_sha256']
                or not ticket.is_file() or digest(ticket) != item['ticket_sha256']):
            continue
        profiles = [p for p in item['profiles'] if p in job.get('compatible_profiles', [])]
        if not profiles:
            continue
        if prior:
            job.setdefault('attention_recovery_history', []).append(prior)
        job['attention_recovery'] = {
            'batch': batch, 'previous_attempts': item['attempts'],
            'previous_receipt': item.get('receipt'), 'profiles': profiles,
            'evidence_path': item['evidence_path'], 'evidence_sha256': item['evidence_sha256'],
            'reason': item['reason'], 'admitted_at': now,
        }
        if item.get('required_model'):
            job['attention_recovery']['required_model'] = item['required_model']
        job.update(state='queued', updated_at=now,
                   waiting_reason='One reviewed recovery attempt; original scope and gates remain required.')
        job.pop('retry_after_epoch', None)
        admitted += 1
    return admitted


def dependency_roots(jobs):
    """Only unresolved reviewed Map lineages receive dependency priority."""
    roots = {}
    for ticket_id, job in jobs.items():
        if job.get('state') != 'blocked' or job.get('superseded_by'):
            continue
        root = (ticket_id if job.get('attention_recovery') else
                (job.get('production') or {}).get('attention_recovery_parent'))
        if root:
            roots[ticket_id] = root
    return roots


def prioritized_dependency_receipts(paths, ops, jobs):
    roots = dependency_roots(jobs)
    current = {ops / jobs[parent]['receipt'] for parent in roots if jobs[parent].get('receipt')}
    return sorted(paths, key=lambda path: (path not in current, str(path)))


def promote_dependency(payload, parent_id, roots):
    root = roots.get(parent_id)
    if root:
        payload['ticket'].setdefault('production', {})['attention_recovery_parent'] = root
    return payload
