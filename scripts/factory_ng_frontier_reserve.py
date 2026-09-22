"""Bound staged-only frontier admission even while other profiles are available."""

PENDING = {'queued', 'backlog', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating'}


def pending_frontier(jobs):
    return sum(job.get('production', {}).get('producer') == 'corpus-frontier'
               and not job.get('superseded_by') and job.get('state') in PENDING
               for job in jobs.values())


def reconcile_reserve(jobs, cap, priority, timestamp):
    """Keep best unstarted contracts queued; retain excess as reversible backlog.

    Never touch attempted work, receipts, repairs, active processes or budgets.
    Previously compiled overflow remains owned and is promoted automatically.
    """
    candidates = [(key, job) for key, job in jobs.items()
                  if job.get('production', {}).get('producer') == 'corpus-frontier'
                  and job.get('state') in ('queued', 'backlog')
                  and not job.get('superseded_by') and not job.get('attempts')
                  and not job.get('receipt') and not job.get('pid')]
    candidate_ids = {key for key, _ in candidates}
    reserved = sum(job.get('state') == 'queued' and not job.get('superseded_by')
                   and key not in candidate_ids for key, job in jobs.items())
    slots = max(0, cap - reserved)
    for index, (key, job) in enumerate(sorted(candidates, key=priority)):
        state = 'queued' if index < slots else 'backlog'
        if job['state'] != state:
            job.update(state=state, updated_at=timestamp)
        if state == 'backlog':
            job['waiting_reason'] = 'Ranked frontier backlog; promoted automatically when the bounded queue has room'
        elif job.get('waiting_reason', '').startswith('Ranked frontier backlog;'):
            job.pop('waiting_reason', None)
