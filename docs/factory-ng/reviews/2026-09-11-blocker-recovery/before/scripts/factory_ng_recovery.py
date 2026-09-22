"""Read-only repair ancestry shared by producers and the controller."""

MAP_REPAIR_LIMIT = 2
INTEGRATION_REPAIR_MARKER = ':integration-repair-v1'


def engine_repair_used(chain):
    # A later evidence refresh must not hide an earlier repair suffix.
    return any(INTEGRATION_REPAIR_MARKER in str(t.get('production', {}).get('key', ''))
               for t in chain)


def map_repair_history(ticket, tickets):
    """Follow Map predecessors, including legacy resumes that dropped counters.

    Dependency completion is new evidence, not a reset of the repair budget.
    Missing ancestry fails closed instead of silently granting fresh attempts.
    """
    generation, obligation, errors = 0, False, []
    visited, visiting = set(), set()

    def visit(item):
        nonlocal generation, obligation
        key = item['id']
        if key in visiting:
            errors.append('cyclic repair ancestry at ' + key)
            return
        if key in visited:
            return
        visiting.add(key)
        production = item.get('production', {})
        count = production.get('integration_repair_generation', 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append('invalid repair generation at ' + key)
            count = MAP_REPAIR_LIMIT
        generation = max(generation, count)
        obligation |= bool(count or production.get('integration_recovery_parent') or
                           production.get('retry_reason') == 'dependency_resume')
        for parent in set(filter(None, (item.get('supersedes'),
                                         production.get('integration_recovery_parent')))):
            previous = tickets.get(parent)
            if previous is None:
                errors.append('missing repair ancestor ' + parent)
            elif previous.get('work_type', 'map') != 'map':
                errors.append('non-Map repair ancestor ' + parent)
            else:
                visit(previous)
        visiting.remove(key)
        visited.add(key)

    visit(ticket)
    return {'generation': generation, 'obligation': obligation,
            'error': '; '.join(sorted(set(errors))), 'ancestors': sorted(visited)}


def annotate_repair_blockers(jobs, tickets):
    """Keep failed receipts/states intact; make exhausted obligations explicit."""
    chains = {}
    for key, ticket in tickets.items():
        chains.setdefault(key.rsplit('/v', 1)[0], []).append(ticket)
    for key, job in jobs.items():
        old = job.pop('repair_blocker', None)
        if old and job.get('waiting_reason') == old.get('reason'):
            job.pop('waiting_reason', None)
        if job.get('superseded_by') or job.get('state') not in ('failed', 'integration_failed'):
            continue
        ticket = tickets.get(key)
        if not ticket:
            continue
        reason = None
        if job.get('work_type') == 'map' and job.get('outcome') in ('gate_failed', 'full_gate_failed', 'candidate_conflict'):
            history = map_repair_history(ticket, tickets)
            if history['obligation']:
                reason = history['error'] or (
                    'Map repair limit reached (%d/%d); complete-card verification is still required.' %
                    (history['generation'], MAP_REPAIR_LIMIT)
                    if history['generation'] >= MAP_REPAIR_LIMIT else None)
        elif (job.get('work_type') == 'engine' and job.get('state') == 'integration_failed'
              and engine_repair_used(chains.get(key.rsplit('/v', 1)[0], []))):
            reason = 'Engine integration repair limit reached (1/1); the failed card dependency remains unresolved.'
        if reason:
            job['repair_blocker'] = {'reason': reason, 'receipt': job.get('integration_receipt') or job.get('receipt')}
            job['waiting_reason'] = reason
