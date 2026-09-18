"""Classify explicit transport errors without interpreting model prose."""
import json

CAPACITY_EXIT = 77
CAPACITY_OUTCOME = 'infrastructure_failed_provider_capacity'


def codex_capacity_failure(raw):
    errors = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') in ('item.completed', 'turn.completed'):
            return False
        if event.get('type') == 'error':
            errors.append(event.get('message'))
        if event.get('type') == 'turn.failed':
            errors.append((event.get('error') or {}).get('message'))
    return any(isinstance(e, str) and e.startswith('Selected model is at capacity.') for e in errors)
