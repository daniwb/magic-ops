#!/usr/bin/env python3
"""Continuously rank current corpus demand, then compile one bounded Map task.

Unlike the verb-only compiler, this does not assert that an executor already
exists. The qualified staged worker must prove reachability or return the
existing validated NEEDS_PRIMITIVE contract. Whole-card gates remain mandatory.
"""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
import time

from factory_ng_paths import OPS, SOURCE
from factory_ng_producer_cache import ProducerCache, digest
from factory_ng_parser_runtime import prepare_parser
from factory_ng_frontier_reserve import pending_frontier


def build_plan():
    spec = importlib.util.spec_from_file_location('frontier_build_plan', OPS / 'scripts/factory-ng-produce-build-plan.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def owned_members(tickets, cache):
    """Historical ownership survives completion, family changes and archive."""
    def projection(ticket):
        if not isinstance(ticket, dict) or ticket.get('work_type') != 'map':
            return {}
        return {'id': ticket.get('id'), 'signature': ticket.get('production', {}).get('frontier_signature'),
                'names': [p['card'] for p in ticket.get('execution', {}).get('parser_probes', [])
                          if p.get('function') == 'reparse_card' and p.get('card')],
                'measurements': [e['path'] for e in ticket.get('evidence', [])
                                 if isinstance(e, dict) and str(e.get('path', '')).startswith('docs/factory-ng/measurements/')
                                 and str(e.get('path', '')).endswith('.json')]}
    names = set()
    for _, row in cache.files('frontier-ownership-v1', tickets, projection):
        names.update(row.get('names', []))
        for reference in row.get('measurements', []):
            path = OPS / reference
            if path.is_file():
                members = cache.file('frontier-member-names-v1', path, lambda value:
                    [m['name'] for m in value.get('members', []) if isinstance(m, dict) and m.get('name')]
                    if isinstance(value, dict) and value.get('schema') == 'factory.targeted-demand/v1' else [])
                names.update(members or [])
    cache.checkpoint()
    return names


def ranking(row):
    """Small known seams first; exact-detail reuse breaks ties, never broad counts."""
    return (row['complexity'], len(row['misses']), -row.get('same_detail_cards', 1),
            row['text_length'], row['name'])


def complexity(misses):
    families = {kind for kind, _ in misses}
    if families & {'verb_unmapped:kw_action', 'verb_unmapped:roll_die', 'verb_unmapped:cast_free'}:
        return 4  # Short Oracle wording can hide an entire missing subsystem.
    if all(kind.startswith('verb_unmapped:') and not kind.endswith(':?') for kind in families):
        return 1
    if all(kind.startswith(('static_', 'restriction_')) for kind in families):
        return 2
    if all(kind.startswith(('spine_', 'verb_unmapped:')) for kind in families):
        return 3
    return 4


def discover(source, cards, parser, stamp, cache, budget=12):
    """A resumable complete scan: never call an unfinished/error scan exhausted."""
    fingerprint = digest([stamp, cards, 'corpus-frontier-v2'])
    key = str(source)
    found, scan = cache.get('frontier-scan-v1', key, fingerprint)
    if not found:
        scan = {'cursor': 0, 'rows': [], 'errors': [], 'complete': False}
    if scan['complete']:
        return scan, fingerprint
    started = time.monotonic()
    while scan['cursor'] < len(cards):
        name, card = cards[scan['cursor']]
        try:
            parse_key = key + ':' + name
            parse_stamp = stamp + ':' + digest(card)
            hit, result = cache.get('frontier-parse-v1', parse_key, parse_stamp)
            if not hit:
                result = parser.reparse_card(card)
                result = {'eligible': bool(result.get('eligible')), 'misses': result.get('misses', [])}
                cache.put('frontier-parse-v1', parse_key, parse_stamp, result)
            if not result['eligible']:
                misses = result['misses']
                scan['rows'].append({'name': name, 'misses': misses, 'complexity': complexity(misses),
                                     'text_length': len(card.get('text') or '')})
        except Exception as exc:
            scan['errors'].append({'card': name, 'error': type(exc).__name__ + ': ' + str(exc)[:300]})
        scan['cursor'] += 1
        if time.monotonic() - started >= budget:
            break
    scan['complete'] = scan['cursor'] == len(cards)
    if scan['complete']:
        counts = Counter(digest(row['misses']) for row in scan['rows'])
        for row in scan['rows']:
            row['same_detail_cards'] = counts[digest(row['misses'])]
        scan['rows'].sort(key=ranking)
    cache.put('frontier-scan-v1', key, fingerprint, scan)
    cache.checkpoint()
    return scan, fingerprint


def compile_ticket(source, revision, row, card, helper):
    name, misses = row['name'], row['misses']
    text_hash = helper.digest_bytes((card.get('text') or '').encode())
    # Share ownership with both original build-plan lanes. A newly supported
    # family may not turn this card into a fresh attempt under another producer.
    key = 'build-plan:multi:' + text_hash
    suffix = digest(['corpus-frontier', name, text_hash])[:12]
    ticket_id = 'ticket:map.frontier-' + suffix + '/v1'
    test = 'scripts/paragraph/test_factory_frontier_' + suffix + '.py'
    measurement_path = 'docs/factory-ng/measurements/corpus-frontier-' + suffix + '.json'
    families = sorted({kind for kind, _ in misses})
    paths = {'scripts/paragraph/reparse.py'}
    for family in families:
        if family.startswith('verb_'):
            paths.add('scripts/paragraph/slotparse_oneshot.py')
        elif family.startswith(('kind_', 'keyword_')):
            paths.add('scripts/paragraph/classify.py')
        elif family.startswith('spine_'):
            paths.add('scripts/paragraph/slotparse_triggered.py')
        elif family.startswith(('static_', 'restriction_')):
            paths.add('scripts/paragraph/slotparse_static.py')
        elif family.startswith(('activated_', 'cost_')):
            paths.add('scripts/paragraph/slotparse_activated.py')
    paths = sorted(path for path in paths if (source / path).is_file()) + [test]
    measurement = {'schema': 'factory.targeted-demand/v1', 'shape': families[0],
                   'member_count': 1, 'review_cards_scanned': 1,
                   'source': {'repository': str(source), 'revision': revision,
                              'parser_sha256': helper.digest_file(source / 'scripts/paragraph/reparse.py')},
                   'members': [{'name': name, 'oracle_text': card.get('text') or '',
                                'text_sha256': text_hash, 'all_miss_shapes': families,
                                'details': [detail for _, detail in misses]}]}
    ticket = {'schema': 'factory.ticket-spec/v1', 'id': ticket_id,
              'title': 'Resolve %d current misses on %s' % (len(misses), name),
              'work_type': 'map', 'lifecycle': 'ready_for_observation',
              'parents': ['plan:' + family for family in families],
              'source': dict(measurement['source'], clean=True),
              'production': {'producer': 'corpus-frontier', 'key': key, 'miss_count': len(misses),
                             'frontier_signature': digest(misses),
                             'candidate_complexity': row['complexity'], 'predicted_class_unlock': 1,
                             'same_detail_cards': row.get('same_detail_cards', 1),
                             'ranking': list(ranking(row)[:-1]), 'retry_generation': 0},
              'skill': {'name': 'implement-map-class', 'path': str(helper.SKILL.relative_to(OPS)),
                        'sha256': helper.digest_file(helper.SKILL)},
              'scope': {'allowed_paths': paths, 'forbidden_paths': ['backend/', 'corpus/']},
              'evidence': [{'path': measurement_path,
                            'fact': 'One current review card; exact Oracle and all %d misses are pinned: %s' % (len(misses), json.dumps(misses))}],
              'required_behavior': [
                  'Preserve every Oracle clause of %s; remove all %d pinned misses and make the complete card eligible.' % (name, len(misses)),
                  'First establish the exact converter and Engine execution path. No existing executor is assumed by this contract. Parser acceptance without executable behavior is failure.',
                  'If runtime support is missing, return NEEDS_PRIMITIVE with one precise CAPABILITY_JSON and exact Oracle evidence. The harness creates and gates a separate Engine dependency.',
                  'Add focused positive behavior tests and adjacent negatives that remain unsupported. Cover every pinned miss, recipients, amounts, conditions, ordering and duration.',
                  'Use general parser rules; never special-case the card name, delete clauses, suppress misses, edit generated records or silently approximate semantics.',
                  'Change only the actual relevant seam within the allowed parser files. If the evidence cannot support one bounded behavior, return a structured verdict rather than widening scope.'],
              'gates': ['cd scripts/paragraph && python3 -m unittest ' + Path(test).stem,
                        'git diff --check',
                        'git status --porcelain adds or changes only ' + ' and '.join(paths),
                        'python3 %s --repo . --members-from %s reports zero remaining pinned members' %
                        (OPS / 'scripts/factory-ng-targeted-demand.py', OPS / measurement_path)],
              'execution': {'mode': 'isolated_clone_observation_only',
                            'selected_profile': 'codex-constrained@1.1.0',
                            'compatible_profiles': ['codex-constrained@1.1.0', 'claude-staged@1.0.0'],
                            'profile_policy': 'exact',
                            'selection_reason': 'A bounded current-source card needs parser/runtime investigation; qualified staged profiles only.',
                            'parser_probes': [{'function': 'reparse_card', 'card': name}],
                            'effective_token_target': 200000, 'warning_reflection_threshold': 500000,
                            'automatic_stop': False, 'model_may_not_commit_push_deploy_or_mutate_live_tickets': True},
              'on_failure': 'Retain immutable evidence and bounded attempt history. Validated capability demand creates an Engine child; no fresh retry is granted by rediscovery.'}
    return {'ticket_id': ticket_id, 'ticket': ticket, 'measurement': measurement}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, default=SOURCE)
    ap.add_argument('--max-misses', type=int, default=6)
    ap.add_argument('--inspect', action='store_true', help='report ranked inventory without returning a ready TicketSpec')
    args = ap.parse_args()
    if not 1 <= args.max_misses <= 6:
        ap.error('--max-misses must be in 1..6')
    source, helper = args.repo.resolve(), build_plan()
    pending = pending_frontier(helper.load_json(helper.JOBS, {}).get('jobs', {}))
    limit = max(1, int(helper.load_json(OPS / 'config/factory-ng-policy.json', {}).get('queue', {}).get('max_queued', 12)))
    if not args.inspect and pending >= limit:
        helper.emit('frontier_reserve_full', reason='%d existing frontier contracts await execution; paused-profile work also consumes this reserve' % pending)
        return
    if not helper.clean_source(source):
        helper.emit('source_unavailable', reason='canonical source is not clean')
        return
    revision = helper.source_revision(source)
    cache = ProducerCache(OPS / 'state/factory-ng-frontier.sqlite3')
    try:
        sys.path.insert(0, str(source / 'scripts/paragraph'))
        import reparse
        cards, stamp, _ = prepare_parser(source, reparse, cache)
        scan, fingerprint = discover(source, cards, reparse, stamp, cache)
        if helper.source_revision(source) != revision or not helper.clean_source(source):
            cache.db.execute("DELETE FROM cache WHERE namespace IN ('frontier-scan-v1', 'frontier-parse-v1', 'parser-vocabulary-v1')")
            helper.emit('source_unavailable', reason='canonical source changed during frontier measurement')
            return
        if not scan['complete']:
            helper.emit('scan_pending', reason='full frontier scan continues at %d/%d' % (scan['cursor'], len(cards)))
            return
        owned = owned_members(helper.TICKETS, cache)
        history = helper.production_history(helper.TICKETS, helper.JOBS, cache)
        jobs = helper.load_json(helper.JOBS, {}).get('jobs', {})
        active_signatures = {job.get('production', {}).get('frontier_signature')
                             for job in jobs.values() if not job.get('superseded_by')
                             and job.get('state') in ('queued', 'working', 'awaiting_verification',
                                                       'awaiting_integration', 'integrating', 'blocked')}
        by_name = dict(cards)
        dispositions, candidates, blockers = Counter(), [], []
        for row in scan['rows']:
            name = row['name']
            text_hash = helper.digest_bytes((by_name[name].get('text') or '').encode())
            if name in owned or text_hash in history.text_hashes:
                dispositions['existing_lineage'] += 1
            elif not row['misses']:
                dispositions['ineligible_without_misses'] += 1
                blockers.append({'name': name, 'reason': 'ineligible_without_misses', 'misses': row['misses']})
            elif len(row['misses']) > args.max_misses:
                dispositions['needs_decomposition'] += 1
                blockers.append({'name': name, 'reason': 'needs_decomposition', 'misses': row['misses']})
            elif digest(row['misses']) in active_signatures:
                dispositions['active_shape_owned'] += 1
            else:
                candidates.append(row)
        summary = {'source_revision': revision, 'fingerprint': fingerprint,
                   'candidates': len(candidates), 'dispositions': dict(dispositions),
                   'measurement_errors': scan['errors'], 'blockers': blockers, 'top': candidates[:12]}
        # Inventory is a disposable, observable read model; only the controller
        # may persist a returned TicketSpec and its measurement.
        target = OPS / 'state/factory-ng-frontier.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
        temporary.replace(target)
        if args.inspect:
            helper.emit('inventory', **summary)
        elif candidates:
            payload = compile_ticket(source, revision, candidates[0], by_name[candidates[0]['name']], helper)
            if helper.source_revision(source) != revision or not helper.clean_source(source):
                helper.emit('source_unavailable', reason='canonical source changed during frontier compilation')
            else:
                helper.emit('ready', **payload)
        else:
            helper.emit('frontier_blocked' if scan['errors'] or dispositions else 'exhausted_for_inputs',
                        reason='No fresh bounded card is admissible; see frontier dispositions. Existing attempts are not reset.', **summary)
    finally:
        cache.close()


if __name__ == '__main__':
    main()
