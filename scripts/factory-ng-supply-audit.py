#!/usr/bin/env python3
"""Measure the entire review frontier, including work no producer can compile.

This is a planning artifact, never a TicketSpec or permission to retry a card.
Source, tickets and jobs are read-only. Only the disposable cache is updated.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

from factory_ng_paths import OPS, SOURCE
from factory_ng_producer_cache import ProducerCache, digest
from factory_ng_parser_runtime import prepare_parser


def load_producer():
    spec = importlib.util.spec_from_file_location(
        'supply_build_plan', OPS / 'scripts/factory-ng-produce-build-plan.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify(result, effects, history, producer, text_hash, max_misses):
    misses = result.get('misses', [])
    if result.get('eligible'):
        return 'remeasure_import'
    if not misses:
        return 'unexplained_ineligible'
    shapes = producer.eligible_shapes(misses, effects, max_misses=max_misses) if len(misses) > 1 else producer.eligible_shapes(misses, effects)
    if not shapes:
        return 'needs_preparation'
    key = 'build-plan:%s:%s' % ('multi' if len(misses) > 1 else shapes[0], text_hash)
    if producer.candidate_retry(history, key, 'fresh') is None:
        return 'existing_lineage'
    return 'fresh_supported_candidate'


def census(cards, parse, effects, history, producer, max_misses=6):
    counts, families, groups, errors = Counter(), {}, {}, []
    for name, card in cards:
        text_hash = producer.digest_bytes((card.get('text') or '').encode())
        try:
            result = parse(name, card)
            misses = result.get('misses', [])
            disposition = classify(result, effects, history, producer, text_hash, max_misses)
            signature = sorted({str(kind) for kind, _ in misses})
        except Exception as exc:
            counts['measurement_error'] += 1
            errors.append({'card': name, 'error': type(exc).__name__ + ': ' + str(exc)[:400]})
            continue
        counts[disposition] += 1
        for family in signature:
            entry = families.setdefault(family, {'cards': 0, 'sole_blocker_cards': 0,
                                                'dispositions': Counter(), 'examples': []})
            entry['cards'] += 1
            entry['sole_blocker_cards'] += len(signature) == 1
            entry['dispositions'][disposition] += 1
            if len(entry['examples']) < 3:
                entry['examples'].append(name)
        # Family groups are discovery leads, not claims of equivalent semantics.
        key = digest([disposition, signature])
        group = groups.setdefault(key, {'id': 'supply:' + key, 'disposition': disposition,
                                       'families': signature, 'cards': 0, 'examples': []})
        group['cards'] += 1
        if len(group['examples']) < 3:
            group['examples'].append({'name': name, 'text_sha256': text_hash,
                                      'misses': misses})
    return {'review_cards': sum(counts.values()), 'dispositions': dict(counts),
            'families': sorted((dict(family=key, **value) for key, value in families.items()),
                               key=lambda row: (-row['sole_blocker_cards'], -row['cards'], row['family'])),
            'discovery_groups': sorted(groups.values(), key=lambda row: (-row['cards'], row['id'])),
            'measurement_errors': errors,
            'note': 'Groups overlap by family. Counts are measured demand, not runnable tickets or guaranteed card unlocks. Existing lineage requires explicit disposition; age and source revision never reset attempts.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=SOURCE)
    ap.add_argument('--cache', type=Path, default=OPS / 'state/factory-ng-supply-audit-cache.sqlite3')
    ap.add_argument('--max-misses', type=int, default=6)
    args = ap.parse_args()
    if args.max_misses < 2:
        ap.error('--max-misses must be at least 2')
    source = args.source.resolve()
    producer = load_producer()
    if not producer.clean_source(source):
        raise SystemExit('source unavailable: canonical checkout is not clean')
    revision = producer.source_revision(source)
    cache = ProducerCache(args.cache)
    try:
        sys.path.insert(0, str(source / 'scripts/paragraph'))
        import reparse
        cards, parser_stamp, _ = prepare_parser(source, reparse, cache)
        effects = producer.registry_effects(source)
        history = producer.production_history(producer.TICKETS, producer.JOBS, cache)

        def parse(name, card):
            key = str(source) + ':' + name
            stamp = parser_stamp + ':' + digest(card)
            found, result = cache.get('supply-audit-parse-v1', key, stamp)
            if not found:
                result = reparse.reparse_card(card)
                result = {'eligible': bool(result.get('eligible')), 'misses': result.get('misses', [])}
                cache.put('supply-audit-parse-v1', key, stamp, result)
            return result

        report = census(cards, parse, effects, history, producer, args.max_misses)
        if producer.source_revision(source) != revision or not producer.clean_source(source):
            cache.db.rollback()
            cache.db.execute("DELETE FROM cache WHERE namespace='parser-vocabulary-v1'")
            cache.db.execute("DELETE FROM cache WHERE namespace='supply-audit-parse-v1'")
            raise SystemExit('source changed during audit; report discarded, rerun on clean source')
        report.update(schema='factory.supply-audit/v1', source_revision=revision,
                      parser_stamp=parser_stamp,
                      measured_at=datetime.now(timezone.utc).isoformat(),
                      max_supported_misses=args.max_misses)
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        cache.close()


if __name__ == '__main__':
    main()
