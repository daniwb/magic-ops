#!/usr/bin/env python3
"""Produce one exact, runtime-backed static condition Map ticket.

Covers the "~ has <keyword> as long as you control a <color> creature"
shape when the keyword carries inline reminder text (wither, persist).  The
sibling reminder-text-free keywords (haste, vigilance, flying) on these same
Scarecrow-cycle cards already parse correctly via the existing control_color
condition (ticket #3088/#4341); only the reminder-text-suffixed variant is a
current static_conditional miss.
"""
import argparse, hashlib, json, subprocess
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / 'docs/factory-ng/tickets'
SKILL = OPS / 'docs/factory-ng/skills/v1/implement-map-class/SKILL.md'
TICKET_ID = 'ticket:map.static-condition-color-control-keyword-reminder/v1'
PARENT = 'ticket:factory.evidence.static-conditional/v1'
# (card name, keyword, color letter, normalized detail sentence)
MEMBERS = (
    ('Blazethorn Scarecrow', 'wither', 'g', '~ has wither as long as you control a green creature'),
    ('Thornwatch Scarecrow', 'wither', 'g', '~ has wither as long as you control a green creature'),
    ('Rattleblaze Scarecrow', 'persist', 'b', '~ has persist as long as you control a black creature'),
    ('Wingrattle Scarecrow', 'persist', 'b', '~ has persist as long as you control a black creature'),
)


def sha(p):
    return 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()


def rev(repo):
    return subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()


def known_ticket(directory):
    for p in directory.glob('*.json'):
        try:
            if json.loads(p.read_text()).get('id') == TICKET_ID:
                return str(p)
        except (OSError, ValueError):
            pass
    return None


def emit(status, **extra):
    print(json.dumps({'schema': 'factory.ticket-production/v1', 'status': status,
                      'ticket_id': TICKET_ID, **extra}, indent=2, sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, default=Path('/opt/development/test/openmagic'))
    ap.add_argument('--ticket-dir', type=Path, default=TICKETS)
    args = ap.parse_args()
    repo = args.repo.resolve()
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True):
        ap.error('ground-truth checkout must be clean')
    parser = repo / 'scripts/paragraph/reparse.py'
    runtime = repo / 'backend/game/condition.go'
    if 'case "control_color":' not in runtime.read_text():
        emit('needs_primitive', reason='runtime lacks control_color condition kind')
        return
    duplicate = known_ticket(args.ticket_dir)
    if duplicate:
        emit('duplicate_ticket', ticket_path=duplicate)
        return
    rows = []
    for name, keyword, color, detail in MEMBERS:
        shard = repo / 'backend/data/carddb' / (name[0].lower() + '.json')
        card = json.loads(shard.read_text())[name]
        text = card.get('text', '')
        if detail.replace('~', 'this creature') not in text.lower():
            emit('ground_truth_changed', card=name)
            return
        rows.append({'name': name, 'text_sha256': 'sha256:' + hashlib.sha256(text.encode()).hexdigest(),
                     'all_miss_shapes': ['static_conditional'], 'details': [detail]})
    measurement = {'schema': 'factory.targeted-demand/v1', 'shape': 'static_conditional',
                   'member_count': len(rows), 'review_cards_scanned': len(rows), 'members': rows,
                   'source': {'repository': str(repo), 'revision': rev(repo), 'parser_sha256': sha(parser)}}
    ticket = {
        'schema': 'factory.ticket-spec/v1', 'id': TICKET_ID,
        'title': 'Map reminder-text-suffixed keyword grants under the existing control_color condition',
        'work_type': 'map', 'lifecycle': 'ready_for_observation', 'parents': [PARENT],
        'source': {'repository': str(repo), 'revision': rev(repo), 'clean': True},
        'skill': {'name': 'implement-map-class', 'path': str(SKILL.relative_to(OPS)), 'sha256': sha(SKILL)},
        'scope': {'allowed_paths': ['scripts/paragraph/reparse.py',
                                     'scripts/paragraph/test_static_condition_color_control_reminder.py'],
                  'forbidden_paths': ['backend/', 'backend/data/', 'scripts/paragraph/slotparse_oneshot.py']},
        'evidence': [
            {'path': 'docs/factory-ng/measurements/static-condition-color-control-keyword-reminder-v1.json',
             'fact': 'Four pinned Scarecrow-cycle cards share two exact reminder-suffixed control_color detail sentences.'},
            {'path': 'backend/game/condition.go', 'sha256': sha(runtime), 'anchor': '191-229',
             'fact': 'control_color already grants a color-gated permanent count check; ticket #4341 explicitly names this Scarecrow-cycle class. No Engine change is implied.'},
            {'path': 'scripts/paragraph/reparse.py', 'sha256': sha(parser), 'anchor': '10649-10929',
             'fact': "The sibling reminder-text-free line on the same four cards (e.g. Blazethorn Scarecrow's haste/red line) already emits {kind: control_color, filter: {filter: creature}, count: 'a', color: <letter>} correctly; only the reminder-text-suffixed keyword line falls through to the static_conditional miss."},
        ],
        'required_behavior': [
            'Map `has wither as long as you control a green creature (reminder text)` and `has persist as long as you control a black creature (reminder text)` to the same control_color condition shape already proven on the reminder-text-free sibling line.',
            'All four pinned cards lose exactly this static_conditional miss.',
            "Do not change output for the cards' existing reminder-text-free sibling ability (haste/vigilance/flying lines) — it must keep parsing exactly as today.",
            'Do not generalize to other keywords, colors, or non-reminder-text phrasing beyond the two pinned detail sentences.',
            'Do not edit Engine, converter, corpus data, condition.go, or use card-name special cases.',
        ],
        'gates': [
            'cd scripts/paragraph && python3 -m unittest test_static_condition_color_control_reminder',
            'git diff --check',
            'git status --porcelain adds or changes only scripts/paragraph/reparse.py and scripts/paragraph/test_static_condition_color_control_reminder.py',
            'python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo . --members-from /opt/development/magic-ops/docs/factory-ng/measurements/static-condition-color-control-keyword-reminder-v1.json',
        ],
        'execution': {
            'mode': 'isolated_clone_observation_only', 'selected_profile': 'qwen-prepared-direct@1.0.2',
            'selection_reason': 'A four-card, two-tuple reminder-text parsing fix over an already-proven runtime condition fits the validated prepared Qwen Map profile.',
            'parser_probes': [
                {'function': 'parse_static_condition', 'text': 'has wither as long as you control a green creature. (It deals damage to creatures in the form of -1/-1 counters.)'},
                {'function': 'parse_static_condition', 'text': "has persist as long as you control a black creature. (When this creature dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)"},
                {'function': 'parse_static_condition', 'text': 'has haste as long as you control a red creature.'},
            ],
            'effective_token_target': 200000, 'warning_reflection_threshold': 500000, 'automatic_stop': False,
            'model_may_not_commit_push_deploy_or_mutate_live_tickets': True,
        },
        'on_failure': 'Record a receipt; a missing keyword-recognition or condition primitive is a separate TicketSpec.',
    }
    emit('ready', measurement=measurement, ticket=ticket)


if __name__ == '__main__':
    main()
