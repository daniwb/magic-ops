"""Isolated, no-tools Goose transport for the OpenRouter free trial."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import openrouter_cooldown
from goose_staged import decode_events

MODEL = 'openrouter/free'
MAX_TOKENS = 32000


def normalize_patch_markers(text):
    """Translate only unambiguous complete FILE-block delimiter lines.

    Source bytes, paths and NEWFILE contents are never rewritten. The strict
    applier retains responsibility for unique exact matches and scope checks.
    """
    changes = []
    block = re.compile(r'(?P<new>^<<<NEWFILE [^\n]+\n.*?^>>>END(?=\n|$))|'
                       r'^<<<FILE [^\n]+\n(?:(?!^<<<(?:FILE|NEWFILE) ).)*?^>>>END(?=\n|$)', re.M | re.S)
    def translate(match):
        if match.group('new') is not None:
            return match.group()
        lines = match.group().splitlines(keepends=True)
        search = [i for i, line in enumerate(lines) if line.rstrip('\n') in ('<<<SEARCH', '<<<<<<< SEARCH')]
        replace = [i for i, line in enumerate(lines) if line.rstrip('\n') in ('===REPLACE', '>>>REPLACE', '=======')]
        # Multiple hunks, marker-like source and incomplete blocks stay intact.
        if len(search) != 1 or len(replace) != 1 or search[0] != 1 or replace[0] <= search[0] + 1:
            return match.group()
        for index, canonical in ((search[0], '<<<SEARCH\n'), (replace[0], '===REPLACE\n')):
            if lines[index] != canonical:
                changes.append({'path_header': lines[0].rstrip('\n'),
                                'from': lines[index].rstrip('\n'), 'to': canonical.rstrip('\n')})
                lines[index] = canonical
        return ''.join(lines)
    return block.sub(translate, text), changes


def response_contract(phase):
    if phase not in ('initial', 'continuation', 'correction'):
        raise ValueError('Unknown Goose response phase')
    discovery = ('If essential exact source is absent, return ONLY up to three lines of '
                 'NEED: repo-relative-path-or-exact-symbol. This consumes the one source request.'
                 if phase == 'initial' else
                 'The source-request allowance is already closed. Do not emit NEED or ask '
                 'to read files. If evidence is still insufficient, return VERDICT: AMBIGUOUS '
                 'and REASON: one concrete missing fact.')
    return '''You are a text-only patch proposer inside a deterministic harness.
There are NO tools or extensions. Nothing you write can execute a command or
read a file. Do not simulate tools, XML tool calls, shell commands, or an agent
conversation. All usable source is in the supplied packet. Follow the ticket's
scope and behavior; the harness alone edits files and runs tests.
Return the completed answer in this response. Keep analysis concise enough to
leave room for the full patch. Do not narrate a plan or say you will read files.
Response phase: %s. %s

When evidence is sufficient, return exact edit blocks using ONLY this grammar:
<<<FILE path/relative/to/repo
<<<SEARCH
exact original source without displayed line numbers
===REPLACE
replacement source
>>>END
For each new file:
<<<NEWFILE path/relative/to/repo
complete new file content
>>>END

Worked syntax example (illustrative only, do not edit this example path):
<<<FILE example.py
<<<SEARCH
def answer():
    return 0
===REPLACE
def answer():
    return 42
>>>END

Every SEARCH must be copied verbatim from supplied source and match uniquely.
Use one FILE block per edit. The exact marker is <<<SEARCH, not <<<<<<< SEARCH;
the exact separator is ===REPLACE, not =======. No Markdown fences or diffs.
Do not mix a patch with a verdict. If the task cannot be completed, use the
ticket's allowed VERDICT and required evidence fields. Preserve required tests.
Any required CAPABILITY_ASSESSMENT and EXPECT lines follow the ticket contract.
''' % (phase, discovery)


def credential():
    # Prefer the user's Goose credential over the legacy Factory account.
    path = Path.home() / '.config/goose/secrets.yaml'
    if path.is_file():
        import yaml
        value = yaml.safe_load(path.read_text()) or {}
        if value.get('OPENROUTER_API_KEY'):
            return value['OPENROUTER_API_KEY']
    return os.environ.get('OPENROUTER_API_KEY', '')


def classify(artifact):
    events = []
    for line in artifact['events'].splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    # Exhausted reasoning is not a rate limit, even if it mentions "429".
    if any(e.get('type') == 'complete' and e.get('output_tokens', 0) >= MAX_TOKENS
           or e.get('message', {}).get('metadata', {}).get('outputTokenLimitReached')
           for e in events):
        artifact['failure_reason'] = 'completion_budget_exhausted'
        return 1
    try:
        answer, usage = decode_events(artifact['events'])
    except ValueError as exc:
        artifact['failure_reason'] = str(exc)
        answer, usage = '', {}
    if artifact['exit_code'] == 0 and usage.get('output_tokens', 0) > 0:
        return 0
    # Provider errors may arrive as zero-usage assistant text. Never scan
    # reasoning, event IDs, timestamps, or nonzero-usage proposal text.
    diagnostics = [artifact['stderr']]
    diagnostics += [json.dumps(e) for e in events if e.get('type') == 'error']
    if usage and usage.get('output_tokens', 0) == 0:
        diagnostics.append(answer)
    lower = '\n'.join(diagnostics).lower()
    if re.search(r'\b429\b|rate[ _-]limit', lower):
        artifact['failure_reason'] = 'provider_rate_limit'
        return 76
    if re.search(r'\b401\b|unauthorized|invalid api key|authentication', lower):
        artifact['failure_reason'] = 'provider_authentication'
        return 75
    artifact.setdefault('failure_reason', 'provider_failed_or_empty_response')
    return artifact['exit_code'] or 1


def run(prompt, model):
    if model != MODEL:
        raise ValueError('Only openrouter/free is authorized for this adapter')
    phase = os.environ.get('FACTORY_GOOSE_PHASE', 'initial')
    contract = response_contract(phase)
    artifact = {'engine': 'goose-openrouter-staged', 'model': model, 'phase': phase,
                'response_contract_version': 2,
                'provider': 'openrouter', 'max_tokens': MAX_TOKENS,
                'events': '', 'stderr': '', 'exit_code': 1}
    if not openrouter_cooldown.status()['allowed']:
        return dict(artifact, exit_code=76, stderr='OpenRouter cooldown active')
    key = credential()
    if not key:
        return dict(artifact, exit_code=75, stderr='OpenRouter authentication unavailable')
    with tempfile.TemporaryDirectory(prefix='factory-goose-openrouter-') as directory:
        root = Path(directory)
        (root / 'config').mkdir()
        (root / 'config/config.yaml').write_text('GOOSE_TELEMETRY_ENABLED: false\nextensions: {}\n')
        packet = root / 'packet.txt'
        packet.write_text(prompt + '\n\n## Final response reminder\n' + contract)
        env = {k: v for k, v in os.environ.items() if not k.startswith('GOOSE_')}
        env.update(GOOSE_PATH_ROOT=directory, GOOSE_PROVIDER='openrouter',
                   GOOSE_MODEL=model, OPENROUTER_API_KEY=key,
                   OPENROUTER_HOST='https://openrouter.ai', GOOSE_MODE='auto',
                   GOOSE_MAX_TOKENS=str(MAX_TOKENS), CONTEXT_FILE_NAMES='[]')
        command = [shutil.which('goose') or str(Path.home() / '.local/bin/goose'),
                   'run', '--instructions', str(packet), '--no-profile',
                   '--system', contract,
                   '--provider', 'openrouter', '--model', model,
                   '--max-turns', '1', '--output-format', 'stream-json', '--stats']
        started = time.time()
        try:
            proc = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                  text=True, timeout=1200)
            artifact.update(events=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
        except subprocess.TimeoutExpired:
            artifact.update(exit_code=124, stderr='Goose timed out after 1200 seconds')
        for field in ('events', 'stderr'):
            artifact[field] = artifact[field].replace(key, '[REDACTED]')
        artifact['exit_code'] = classify(artifact)
        if artifact['exit_code'] == 76:
            openrouter_cooldown.record_rate_limit(model=model)
        elif artifact['exit_code'] == 0:
            openrouter_cooldown.record_success(request_started_epoch=started, model=model)
            answer, _ = decode_events(artifact['events'])
            answer, changes = normalize_patch_markers(answer)
            if changes:
                artifact.update(normalized_response=answer, marker_normalizations=changes)
        return artifact
