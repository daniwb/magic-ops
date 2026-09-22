"""Pin a reviewed isolated correction; never mutates live jobs or original tickets."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OPS = ROOT.parents[3]
name, original_path, ticket_id, title, reason = sys.argv[1:6]
extra_paths = sys.argv[6:]
review = ROOT / name
review.mkdir(exist_ok=True)
if (review / 'ticket.json').exists():
    raise SystemExit('Ticket already pinned; use a new immutable revision/review directory.')
clone = Path('/tmp/factory-ng-attention-' + name)
original = OPS / original_path
ticket = json.loads(original.read_text())
parent = ticket['id']
ticket.update(id=ticket_id, title=title, parents=[parent],
              source={'repository': '/opt/development/test/openmagic',
                      'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=clone, text=True).strip(),
                      'clean': True},
              operator_recovery={'authorization': 'User requested fixing all needs-attention tickets.',
                                 'original_ticket': original_path,
                                 'original_ticket_sha256': 'sha256:' + hashlib.sha256(original.read_bytes()).hexdigest(),
                                 'additional_provider_runs': 0, 'counter_resets': False,
                                 'scope_addition_reason': reason})
ticket['scope']['allowed_paths'] += extra_paths
(review / 'ticket.json').write_text(json.dumps(ticket, indent=2) + '\n')
(review / 'clone.txt').write_text(str(clone) + '\n')
sys.path.insert(0, str(OPS / 'scripts'))
from factory_ng_verification import save_proposal
identity = {'worker': 'operator', 'model': 'operator-correction-no-worker-provider-run', 'profile': 'codex-constrained@1.1.0'}
proposal = save_proposal(OPS / 'docs/factory-ng/candidates', clone, review / 'ticket.json', identity,
                         {'telemetry': {'model_calls': 0}, 'operator_recovery': ticket['operator_recovery']})
(review / 'remote-manifest.json').write_text(json.dumps([{'ticket_id': ticket_id,
    'ticket_path': str((review / 'ticket.json').relative_to(OPS)),
    'proposal': str(proposal.relative_to(OPS)), 'identity': identity}], indent=2) + '\n')
print(proposal)
