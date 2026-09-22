"""Explicit, bounded replay selection; immutable attempts remain untouched."""
import json

ACTIVE = {'queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating'}


def read_batch(ops):
    try:
        value = json.loads((ops / 'config/factory-ng-context-retry-batch.json').read_text())
    except (OSError, ValueError):
        return {}
    return value if value.get('enabled') and value.get('id') and 1 <= len(value.get('tickets', [])) <= 4 else {}


def selected(batch, ticket_id):
    return ticket_id.rsplit('/v', 1)[0] in {key.rsplit('/v', 1)[0] for key in batch.get('tickets', [])}


def active_count(batch, specs, jobs):
    superseded = {t.get('supersedes') for t in specs.values()}
    return sum(selected(batch, key) and key not in superseded and not job.get('superseded_by')
               and job.get('state') in ACTIVE for key, job in jobs.items())
