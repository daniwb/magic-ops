"""Shared declaration resolver for knowledge discovery, packets and NEED."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

OPS = Path(__file__).resolve().parents[1]
ROOTS = ('backend/game/', 'backend/cards/', 'backend/cardfns/', 'scripts/paragraph/')


def normalize(text):
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text).lower()
    words = re.findall(r'[a-z0-9]+', text)
    aliases = {'cards':'card', 'draws':'draw', 'drawn':'draw', 'drawing':'draw',
               'counters':'counter', 'events':'event', 'targets':'target'}
    return ' '.join(aliases.get(w, w) for w in words)


def revision(repo):
    p = subprocess.run(['git','rev-parse','HEAD'], cwd=repo, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else 'unavailable'


def parser_binary():
    from factory_ng_go_helper import helper_binary
    return helper_binary(OPS / 'scripts/go-source-symbols.go')


def symbols(repo, relatives):
    root = Path(repo).resolve()
    paths = []
    for relative in dict.fromkeys(relatives):
        if not relative.startswith(ROOTS) or '..' in Path(relative).parts:
            continue
        p = (root / relative).resolve()
        if p.is_relative_to(root) and p.is_file() and p.suffix == '.go':
            paths.append(relative)
    if not paths:
        return []
    result = subprocess.run([parser_binary()], cwd=root, input=json.dumps(paths),
                            capture_output=True, text=True, check=True, timeout=60)
    rows = json.loads(result.stdout)
    for row in rows:
        qualifier = '.'.join(p for p in (row['package'],row['receiver'],row['name']) if p)
        if row['kind'] == 'case': qualifier = '.'.join(p for p in (row['package'],row['receiver'],row['signature']) if p)
        row['qualified'] = qualifier
        row['symbol_id'] = row['path'] + '::' + qualifier
    return rows


def resolve(repo, candidate, budget=180):
    """Re-locate identity in this checkout; indexed line numbers are hints only."""
    matches = [s for s in symbols(repo, [candidate['path']])
               if s['symbol_id'] == candidate.get('symbol_id')]
    if len(matches) != 1:
        return {'status':'unresolved', 'candidate':candidate, 'reason':'declaration absent or ambiguous in this checkout'}
    row = matches[0]
    path = Path(repo) / row['path']
    text = path.read_text()
    end = min(row['end'], row['start'] + max(0,budget) - 1)
    row.update(status='resolved', source_revision=revision(repo),
               sha256='sha256:'+hashlib.sha256(text.encode()).hexdigest(),
               supplied_end=end, truncated=end < row['end'],
               excerpt='\n'.join('%5d %s' % (i+1,line) for i,line in enumerate(text.splitlines())
                                 if row['start'] <= i+1 <= end))
    return row


def render(row):
    if row.get('status') != 'resolved':
        return 'UNRESOLVED: ' + row.get('reason','source unavailable')
    return '### %s:%d-%d [%s; %s%s]\n%s' % (
        row['path'],row['start'],row['supplied_end'],row['qualified'],row['source_revision'],
        '; truncated at source budget' if row['truncated'] else '',row['excerpt'])
