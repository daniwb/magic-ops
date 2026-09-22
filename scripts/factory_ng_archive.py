"""Cold job history with compact completion tombstones in the compatibility ledger.

Original TicketSpecs and receipt paths stay valid. Only the controller calls
archive_jobs, under its process-held single-writer lock.
"""
import hashlib
import json
from pathlib import Path

from factory_ng_receipts import write_receipt


def archived(job):
    return bool(job.get('archive_path') and job.get('state') == job.get('archived_state'))


def archivable(job):
    return (job.get('state') == 'completed' or
            job.get('superseded_by') and job.get('state') in
            ('failed', 'integration_failed', 'blocked', 'parked'))


def archive_jobs(ops, jobs, timestamp, limit=200):
    count = 0
    retained = {'ticket_id', 'ticket_path', 'work_type', 'state', 'created_at', 'updated_at',
                'finished_at', 'outcome', 'integration_outcome', 'integration_receipt',
                'receipt', 'processed_receipt', 'production', 'superseded_by', 'attempts',
                'profile', 'dispatch_profile', 'model', 'worker', 'integration_attempts',
                'verification_attempts', 'attention_recovery', 'failed_profiles',
                'compatible_profiles', 'preferred_profile'}
    for key, job in jobs.items():
        if count >= limit:
            break
        if archived(job) or not archivable(job):
            continue
        payload = {'schema': 'factory.archived-job/v1', 'ticket_id': key, 'job': job}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        path = Path(ops) / 'docs/factory-ng/job-archive' / (digest + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            write_receipt(path, payload)
        except FileExistsError:
            # Crash after archive publication but before job-state publication.
            if json.loads(path.read_text()) != payload:
                raise ValueError('archive collision: ' + str(path))
        tombstone = {field: value for field, value in job.items() if field in retained}
        tombstone.update(archive_path=str(path.relative_to(ops)), archived_at=timestamp,
                         archived_state=job['state'])
        jobs[key] = tombstone
        count += 1
    return count
