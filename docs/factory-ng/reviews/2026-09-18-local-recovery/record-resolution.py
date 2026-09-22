"""Export an operator-reviewed commit and bind it to its accepted observation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('receipt', type=Path)
parser.add_argument('clone', type=Path)
parser.add_argument('reason')
parser.add_argument('--suffix', default='')
parser.add_argument('--commit', default='HEAD')
args = parser.parse_args()
root = Path(__file__).resolve().parent
ops = root.parents[3]
receipt = json.loads(args.receipt.read_text())
ticket = receipt['ticket']
assert receipt['outcome'].startswith('accepted')
def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()
original = ops / receipt['execution']['candidate_patch']
assert digest(original.read_bytes()) == receipt['execution']['candidate_patch_sha256']
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=args.clone)
patch = subprocess.check_output(['git', 'format-patch', '-1', '--stdout', args.commit], cwd=args.clone)
name = ticket['id'].removeprefix('ticket:').replace('/', '-') + args.suffix + '.patch'
output = root / name
assert not output.exists(), output
output.write_bytes(patch)
manifest_path = root / 'merge-resolutions.json'
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
    'schema': 'factory.reviewed-merge-resolutions/v1', 'resolutions': {}}
manifest['resolutions'][ticket['id']] = {
    'original_patch_sha256': digest(original.read_bytes()),
    'ticket_sha256': ticket['sha256'],
    'patch': str(output.relative_to(ops)),
    'patch_sha256': digest(patch),
    'source_revision': subprocess.check_output(['git', 'merge-base', args.commit, 'origin/main'], cwd=args.clone, text=True).strip(),
    'reason': args.reason,
}
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
print(output)
