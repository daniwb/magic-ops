"""Early vocabulary handoff checks; production semantic gates remain required."""
import json
from pathlib import Path
import subprocess
from factory_ng_go_helper import helper_binary
import time

OPS = Path(__file__).resolve().parents[1]


def vocabulary(repo, base=None):
    repo = Path(repo)
    if base is not None:
        sources = {'base': subprocess.check_output(
            ['git', 'show', base + ':backend/game/ability_effects.go'], cwd=repo, text=True)}
    else:
        sources = {str(p): p.read_text() for p in (repo / 'backend/cards').glob('registry*.go')
                   if not p.name.endswith('_test.go')}
        sources['dispatch'] = (repo / 'backend/game/ability_effects.go').read_text()
    result = subprocess.run([helper_binary(OPS / 'scripts/factory-ng-vocabulary/main.go')],
                            input=json.dumps(sources), text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise ValueError('Go vocabulary extraction failed: ' + result.stderr[-1600:])
    return json.loads(result.stdout)


def emitted_effects(value):
    if isinstance(value, dict):
        effect = value.get('effect')
        if isinstance(effect, str) and effect:
            yield effect
        for child in value.values():
            yield from emitted_effects(child)
    elif isinstance(value, list):
        for child in value:
            yield from emitted_effects(child)


def engine_registration_gate(ticket, repo):
    started = time.monotonic()
    try:
        current = vocabulary(repo)
        previous = vocabulary(repo, ticket['source']['revision'])
        added = set(current['dispatch']) - set(previous['dispatch'])
        missing = sorted(added - set(current['registered']))
        detail = ('New public effects require regEffect registration in an allowed registry_*.go file: '
                  + ', '.join(missing)) if missing else 'All newly added public effects are registered.'
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        missing, detail = True, str(exc)
    return {'id': 'engine-vocabulary-handoff', 'outcome': 'failed' if missing else 'passed',
            'detail': detail, 'elapsed_ms': round((time.monotonic() - started) * 1000)}
