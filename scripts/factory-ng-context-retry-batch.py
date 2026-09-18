#!/usr/bin/env python3
"""Emit one of the four authorized context retries, at most two active."""
import importlib.util
import json
from pathlib import Path
import sys

from factory_ng_retry_batch import read_batch, active_count
from factory_ng_safety import source_problem

OPS = Path(__file__).resolve().parents[1]
from factory_ng_paths import SOURCE


def main():
    batch = read_batch(OPS)
    if not batch:
        print(json.dumps({'status': 'disabled'})); return
    problem = source_problem(SOURCE)
    if problem:
        print(json.dumps({'status': 'source_unavailable', 'reason': problem})); return
    spec = importlib.util.spec_from_file_location('batch_repair', OPS / 'scripts/factory-ng-produce-build-plan.py')
    producer = importlib.util.module_from_spec(spec); spec.loader.exec_module(producer)
    sys.path.insert(0, str(SOURCE / 'scripts/paragraph'))
    import reparse
    tickets = {t['id']: t for path in producer.TICKETS.glob('*.json')
               if (t := producer.load_json(path, {})).get('id')}
    jobs = producer.load_json(producer.JOBS, {}).get('jobs', {})
    if active_count(batch, tickets, jobs) >= 2:
        print(json.dumps({'status': 'retry_batch_full'})); return
    eligible = []
    for key in batch['tickets']:
        trial = tickets.get(key, {}).get('production', {}).get('trial_id')
        trial_active = sum(t.get('production', {}).get('trial_id') == trial
                           and not jobs.get(k, {}).get('superseded_by')
                           and jobs.get(k, {}).get('state', 'queued') in ('queued', 'working', 'awaiting_verification', 'awaiting_integration', 'integrating')
                           for k, t in tickets.items()) if trial else 0
        if trial_active < 2:
            eligible.append(key)
    candidate = producer.integration_repair_candidate(SOURCE, producer.TICKETS, producer.JOBS,
                                                       reparse, only_ids=eligible)
    print(json.dumps({'status': 'ready', 'ticket_id': candidate['id'], 'ticket': candidate}
                     if candidate else {'status': 'no_retry_candidate'}))


if __name__ == '__main__':
    main()
