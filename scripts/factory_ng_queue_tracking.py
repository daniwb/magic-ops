"""Record queue flow without treating dispatch or failed tickets as completion."""
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import time

OPS = Path(__file__).resolve().parents[1]


def stage(job):
    if job.get('superseded_by'):
        return 'superseded'
    state = job.get('state', 'missing')
    return {'awaiting_verification': 'focused_wait', 'awaiting_integration': 'integration_wait',
            'integrating': 'integration_run'}.get(state, 'focused_run' if state == 'working' and
                (job.get('verification_resume') or job.get('verification_batch')) else state)


BACKLOG = {'focused_wait', 'focused_run', 'integration_wait', 'integration_run'}


def measure(jobs, previous=None, epoch=None):
    previous = previous or {}; epoch = time.time() if epoch is None else epoch
    states = {key: stage(job) for key, job in jobs.items()}
    current = {key for key, value in states.items() if value in BACKLOG}
    before = set(previous.get('backlog_ids', []))
    cohort = previous.get('cohort_ids', sorted(current))
    tracked = set(previous.get('tracked_ids', [])) | current
    completed = sorted(key for key in tracked if states.get(key) == 'completed' and
                       previous.get('tracked_states', {}).get(key) != 'completed') if previous else []
    counts = Counter(states[key] for key in current)
    result = {'schema': 'factory.queue-trend/v1', 'epoch': epoch,
              'checked_at': datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
              'baseline_at': previous.get('baseline_at', epoch), 'cohort_ids': cohort,
              'cohort_states': dict(Counter(states.get(key, 'missing') for key in cohort)),
              'counts': dict(counts), 'waiting': counts['focused_wait'] + counts['integration_wait'],
              'running': counts['focused_run'] + counts['integration_run'], 'total_unfinished': len(current),
              'arrivals': sorted(current - before) if previous else [], 'completed': completed,
              'departed_without_completion': {key: states.get(key, 'missing') for key in before-current
                                              if states.get(key) != 'completed'},
              'backlog_ids': sorted(current), 'tracked_ids': sorted(tracked),
              'tracked_states': {key: states.get(key, 'missing') for key in tracked},
              'repair_wait': sum(states[k] == 'focused_wait' and bool(j.get('verification_isolate'))
                                 for k,j in jobs.items()),
              'repair_wait_by_worker': dict(Counter(j.get('worker','unknown') for k,j in jobs.items()
                                                    if states[k]=='focused_wait' and j.get('verification_isolate')))}
    result['net_unfinished_change'] = len(current) - len(before) if previous else 0
    result['completed_since_baseline'] = previous.get('completed_since_baseline', 0) + len(completed)
    result['arrivals_since_baseline'] = previous.get('arrivals_since_baseline', 0) + len(result['arrivals'])
    result['new_tickets_seen'] = len(tracked - set(cohort))
    result['reentries_since_baseline'] = result['arrivals_since_baseline'] - result['new_tickets_seen']
    result['unsuccessful_exits_since_baseline'] = previous.get('unsuccessful_exits_since_baseline', 0) + len(result['departed_without_completion'])
    return result


def window_trend(sample, history):
    eligible = [row for row in history if row.get('baseline_at') == sample['baseline_at']
                and row['epoch'] < sample['epoch']]
    if not eligible:
        return {'status': 'collecting', 'window_seconds': 0}
    older = [row for row in eligible if row['epoch'] <= sample['epoch'] - 3600]
    baseline = older[-1] if older else eligible[0]
    seconds = sample['epoch'] - baseline['epoch']
    change = sample['total_unfinished'] - baseline['total_unfinished']
    return {'status': 'collecting' if seconds < 1800 else 'growing' if change > 0 else 'shrinking' if change < 0 else 'steady',
            'window_seconds': int(seconds), 'unfinished_change': change,
            'waiting_change': sample['waiting'] - baseline['waiting'],
            'completed': sample['completed_since_baseline'] - baseline['completed_since_baseline'],
            'arrivals': sample.get('arrivals_since_baseline', 0) - baseline.get('arrivals_since_baseline', 0),
            'growth_alert': seconds >= 1800 and change >= 5 and sample['total_unfinished'] >= 20}


def record(jobs=None, root=OPS, epoch=None):
    folder = root / 'state'; folder.mkdir(exist_ok=True)
    epoch = time.time() if epoch is None else epoch
    with (folder / 'factory-ng-queue-trend.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        target = folder / 'factory-ng-queue-trend.json'
        previous = json.loads(target.read_text()) if target.exists() else None
        if previous and epoch - previous['epoch'] < 55:
            return previous
        if jobs is None:
            jobs = json.loads((folder / 'factory-ng-jobs.json').read_text())['jobs']
        history_path = folder / 'factory-ng-queue-trend.jsonl'
        history = []
        if history_path.exists():
            with history_path.open('rb') as stream:
                stream.seek(0, 2); offset = max(0, stream.tell() - 262144); stream.seek(offset)
                if offset: stream.readline()
                for line in stream:
                    try: history.append(json.loads(line))
                    except ValueError: continue
        if previous and 'arrivals_since_baseline' not in previous:
            same = [row for row in history if row.get('baseline_at') == previous['baseline_at']]
            previous['arrivals_since_baseline'] = sum(len(row.get('arrivals', [])) for row in same)
            previous['unsuccessful_exits_since_baseline'] = sum(len(row.get('departed_without_completion', {})) for row in same)
        sample = measure(jobs, previous, epoch)
        sample['window'] = window_trend(sample, history)
        with history_path.open('a') as output:
            output.write(json.dumps({k:v for k,v in sample.items() if k not in
                                    ('tracked_ids','tracked_states','cohort_ids','backlog_ids')})+'\n')
        temp = target.with_suffix('.tmp'); temp.write_text(json.dumps(sample, indent=2)+'\n');os.replace(temp,target)
        return sample


if __name__ == '__main__':
    print(json.dumps({k:v for k,v in record().items() if k not in
                     ('tracked_ids','tracked_states','cohort_ids','backlog_ids')}, indent=2))
