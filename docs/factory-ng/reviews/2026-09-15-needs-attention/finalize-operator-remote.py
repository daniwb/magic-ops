"""Check imported green evidence against the isolated patch and commit that clone."""
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parent
OPS = ROOT.parents[3]
review = ROOT / sys.argv[1]
ticket = json.loads((review / 'ticket.json').read_text())
result = json.loads((review / 'remote-result.json').read_text())['ticket_results'][ticket['id']]
assert result['status'] == 'accepted_for_dependent_observation', result
receipt = json.loads((OPS / result['receipt']).read_text())
assert receipt['execution'].get('verification_host'), 'Missing remote provenance'
assert all(g['outcome'] == 'passed' for g in receipt['gates'])
assert [g['command'] for g in receipt['gates'] if g['id'].startswith('ticket-gate-')] == ticket['gates']
manifest = json.loads((review / 'remote-manifest.json').read_text())[0]
proposal = json.loads((OPS / manifest['proposal']).read_text())
clone = Path((review / 'clone.txt').read_text().strip())
assert not subprocess.check_output(['git', 'diff', '--name-only'], cwd=clone, text=True), 'Unstaged edits after pinning'
actual = subprocess.check_output(['git', 'diff', '--cached', '--binary', '--full-index', 'HEAD'], cwd=clone, text=True)
assert actual == proposal['patch'], 'Verified patch differs from isolated candidate'
subprocess.run(['git', 'commit', '-m', ticket['title']], cwd=clone, check=True)
(review / 'receipt.txt').write_text(result['receipt'] + '\n')
print(result['receipt'])
