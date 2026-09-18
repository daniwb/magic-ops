#!/usr/bin/env python3
"""Cached daily UTC auto-card totals from immutable canonical Git snapshots."""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile

OPS = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], timeout=90)


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def publish(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(value, handle, indent=2)
            handle.write('\n')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def auto_count(repo, revision, cache):
    """Reuse counts by immutable shard blob, including unchanged historical days."""
    blobs = []
    for entry in git(repo, 'ls-tree', '-r', '-z', revision, '--', 'backend/data/carddb').split(b'\0'):
        if not entry:
            continue
        header, path = entry.split(b'\t', 1)
        mode, kind, oid = header.split()
        name = Path(os.fsdecode(path)).name
        if kind == b'blob' and name.endswith('.json') and not name.startswith('_'):
            blobs.append(oid.decode())
    if not blobs:
        raise ValueError('No card shards at ' + revision)
    for oid in set(blobs) - cache.keys():
        cards = json.loads(git(repo, 'cat-file', 'blob', oid))
        if not isinstance(cards, dict):
            raise ValueError('Invalid card shard at ' + revision)
        cache[oid] = sum(isinstance(card, dict) and card.get('status') == 'auto' for card in cards.values())
    return sum(cache[oid] for oid in blobs)


def daily_rows(commits, now, days, count):
    """Use first-parent order and exclusive midnight cutoffs, never interpolate gaps."""
    today = now.astimezone(UTC).date()
    previous = None
    rows = []
    for offset in range(-days - 1, 1):
        day = today + dt.timedelta(days=offset)
        cutoff = int((now if offset == 0 else dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), UTC)).timestamp())
        selected = next(((sha, ts) for sha, ts in commits if ts < cutoff), None)
        total = count(selected[0]) if selected else None
        if offset != -days - 1:
            rows.append({'date_utc': day.isoformat(), 'partial_day': offset == 0,
                         'revision': selected[0] if selected else None, 'total_auto': total,
                         'net_activated': total - previous if total is not None and previous is not None else None})
        previous = total
    return rows


def operational_signals(controller_log, watchdog_log):
    signals = {}
    def day_signals(day):
        return signals.setdefault(day, {'producer_errors': 0, 'duplicate_tickets': 0,
            'fresh_exhausted': 0, 'watchdog_samples': 0, 'idle_samples': 0, 'stale_samples': 0})
    if controller_log.exists():
        for line in controller_log.read_text(errors='replace').splitlines():
            if not line.startswith('[') or 'producer=' not in line:
                continue
            day = line[1:11]
            row = day_signals(day)
            row['producer_errors'] += 'status=producer_error ' in line
            row['duplicate_tickets'] += 'status=duplicate_ticket ' in line
            row['fresh_exhausted'] += ('status=exhausted_supported_plan ' in line and
                ('producer=build-plan-fresh-local ' in line or 'producer=build-plan-continuous ' in line))
    if watchdog_log.exists():
        for line in watchdog_log.read_text(errors='replace').splitlines():
            try:
                value = json.loads(line)
                day = value['checked_at'][:10]
            except (ValueError, KeyError):
                continue
            row = day_signals(day)
            row['watchdog_samples'] += 1
            row['idle_samples'] += value.get('active') is False
            row['stale_samples'] += any('controller state is stale' in str(p) for p in value.get('problems', []))
    return signals


def activation_waves(repo, head, start, cache):
    waves = cache.setdefault('_waves_v2', {})
    lines = git(repo, 'log', head, '--first-parent', '--format=%H %ct',
                '--since=' + start + 'T00:00:00Z', '--', 'backend/data/carddb').decode().splitlines()
    result = {}
    for line in lines:
        sha, raw_ts = line.split(); ts = int(raw_ts)
        if sha not in waves:
            patch = git(repo, 'show', '--format=', '--first-parent', '--unified=0', sha,
                        '--', 'backend/data/carddb')
            delta = 0
            in_shard = False
            for changed in patch.splitlines():
                if changed.startswith(b'diff --git '):
                    name = changed.rsplit(b'/', 1)[-1]
                    in_shard = name.endswith(b'.json') and not name.startswith(b'_')
                if in_shard and changed[:1] in (b'+', b'-') and changed[1:].strip().rstrip(b',') == b'"status": "auto"':
                    delta += 1 if changed[:1] == b'+' else -1
            waves[sha] = delta
        if waves[sha]:
            day = dt.datetime.fromtimestamp(ts, UTC).date().isoformat()
            result.setdefault(day, []).append({'revision': sha, 'net_activated': waves[sha]})
    return result


def explain_day(row, signals, waves, note=None):
    value = row['net_activated']
    if value is None:
        return {'category': 'unknown', 'text': 'Insufficient committed history for a daily comparison.', 'evidence': []}
    category = 'in_progress' if row['partial_day'] else 'below_target' if value < 100 else 'high' if value >= 150 else 'on_target'
    evidence = []
    positive = sorted((w for w in waves if w['net_activated'] > 0), key=lambda w: -w['net_activated'])
    if positive:
        evidence.append(f"{len(positive)} imports increased enabled cards; largest +{positive[0]['net_activated']} ({positive[0]['revision'][:12]}).")
    if signals.get('producer_errors'):
        evidence.append(f"{signals['producer_errors']} producer error responses were logged.")
    if signals.get('duplicate_tickets'):
        evidence.append(f"{signals['duplicate_tickets']} duplicate-ticket responses were logged.")
    if signals.get('fresh_exhausted'):
        evidence.append(f"The fresh-work producer reported an exhausted frontier in {signals['fresh_exhausted']} checks.")
    if signals.get('idle_samples'):
        evidence.append(f"No active work in {signals['idle_samples']}/{signals['watchdog_samples']} watchdog samples (samples, not hours).")
    if signals.get('stale_samples'):
        evidence.append(f"A stale controller was reported in {signals['stale_samples']} watchdog samples.")
    if category == 'in_progress':
        text = 'Today is still in progress; the daily target is not assessed yet.'
    elif category == 'high' and positive:
        largest = positive[0]['net_activated']
        top3 = sum(w['net_activated'] for w in positive[:3])
        text = (f'A large import contributed +{largest} cards in one step.' if largest >= 100 else
                f'Activations accumulated across {len(positive)} imports; the three largest contributed +{top3} cards.')
    elif category == 'high' and not note:
        text = 'Well above target, but the available records do not establish a specific cause.'
    elif note:
        text = note['text']
    elif category == 'below_target':
        text = ('Repeated duplicate-ticket responses indicate a supply bottleneck; its daily impact is not quantified.' if signals.get('duplicate_tickets', 0) >= 100 else
                'Producer errors and exhausted fresh-work checks were observed; their share of the shortfall is not established.'
                if signals.get('producer_errors') or signals.get('fresh_exhausted') else
                'Below target. The available records do not establish a specific cause for the shortfall.')
    else:
        text = 'The daily target was reached.'
    if note and category in ('high', 'in_progress'):
        evidence.append(note['text'])
    return {'category': category, 'text': text, 'evidence': evidence,
            'operator_note_source': note.get('source') if note else None,
            'largest_imports': positive[:3]}


def build(repo, now, days, cache):
    # A changing working tree cannot affect committed blobs under this pinned SHA.
    head = git(repo, 'rev-parse', 'refs/heads/main').decode().strip()
    commits = [(sha, int(ts)) for sha, ts in
               (line.split() for line in git(repo, 'log', head, '--first-parent', '--format=%H %ct').decode().splitlines())]
    totals = {}
    def count(sha):
        if sha not in totals:
            totals[sha] = auto_count(repo, sha, cache)
        return totals[sha]
    rows = daily_rows(commits, now, days, count)
    signals = operational_signals(OPS / 'state/factory-ng-controller.log', Path('/tmp/orch/factory-ng-watchdog.log'))
    waves = activation_waves(repo, head, rows[0]['date_utc'], cache)
    notes = read_json(OPS / 'docs/factory-ng/measurements/activation-day-notes.json', {})
    for row in rows:
        day = row['date_utc']
        row['reason'] = explain_day(row, signals.get(day, {}), waves.get(day, []), notes.get(day))
    completed = [r['net_activated'] for r in rows if not r['partial_day'] and r['net_activated'] is not None]
    return {'schema': 'factory.daily-activations/v1', 'generated_at': now.isoformat(),
            'source_head': head, 'timezone': 'UTC', 'days': days,
            'metric': 'Net change in committed status-auto cards; not live deployments.',
            'target_per_day': 100, 'high_threshold': 150, 'rows': rows, 'summary': {'completed_days': len(completed),
                                     'total_net': sum(completed),
                                     'average_per_day': sum(completed) / len(completed) if completed else None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('/opt/development/test/openmagic'))
    parser.add_argument('--out', type=Path, default=OPS / 'state/factory-ng-daily-activations.json')
    parser.add_argument('--cache', type=Path, default=OPS / 'state/factory-ng-daily-activations-cache.json')
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        cache = read_json(args.cache, {})
        value = build(args.repo, dt.datetime.now(UTC), 14, cache)
        publish(args.cache, cache)
        publish(args.out, value)


if __name__ == '__main__':
    main()
