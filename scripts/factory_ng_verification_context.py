"""Exact fresh-card parser invocation for test-only verification packets."""
import json
import subprocess
import sys

# This is executed in the pinned checkout and shown verbatim to the worker.
# The test must execute it again; copied JSON is never runtime proof.
PARSER_PROGRAM = '''import json, sys
sys.path.insert(0, "scripts/paragraph")
import reparse
card = reparse.load_card(sys.argv[1])
assert card is not None, "corpus card missing"
parsed = reparse.reparse_card(card)
assert parsed["eligible"] and not parsed["misses"], parsed
definition = dict(card)
definition.update({k: v for k, v in parsed.items() if k not in ("eligible", "misses")})
print(json.dumps(definition))
'''


def verification_context(repo, ticket):
    production = ticket.get('production', {})
    if production.get('trial_phase') != 'verification' or not production.get('trial_card'):
        return ''
    name = production['trial_card']
    result = subprocess.run([sys.executable, '-c', PARSER_PROGRAM, name], cwd=repo,
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        return ('## Fresh-card preparation failed (not complete-card evidence)\n' + result.stderr[-3000:])
    definition = json.loads(result.stdout)
    return ('## Verified fresh-card invocation in this pinned checkout\n'
            'From a Go test in backend/cards, invoke python3 -c with the following program '
            'and the card name as the next argument. Set cmd.Dir to ../.. (repository root). '
            'JSON-decode stdout into CardDefinition, then call ToGameCard. Check subprocess '
            'and conversion errors. Execute this in the test; do not embed the displayed JSON '
            'as a substitute for parsing. No existing Python/Go bridge helper is required.\n'
            'Card name: ' + json.dumps(name) + '\nProgram:\n' + PARSER_PROGRAM +
            '\nObserved definition (preparation only; runtime assertions still required):\n' +
            json.dumps(definition, sort_keys=True) + '\n')
