"""Factory's no-tools Goose adapter; Goose proposes, the harness applies/gates."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

OPS = Path(__file__).resolve().parents[1]
PROVIDER = OPS / 'config/goose/strix_halo.json'
MAX_TOKENS = 32000


def decode_events(raw):
    parts, usage = [], None
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue  # Goose startup notices are not protocol events.
        if event.get('type') == 'error':
            raise ValueError('Goose reported an error')
        if event.get('type') == 'message':
            message = event.get('message', {})
            if message.get('metadata', {}).get('outputTokenLimitReached'):
                raise ValueError('Goose reported truncated output; partial output rejected')
            if message.get('role') != 'assistant':
                continue
            for block in message.get('content', []):
                if block.get('type') in ('toolRequest', 'toolResponse'):
                    raise ValueError('No-tools Goose returned a tool interaction')
                if block.get('type') == 'text':
                    parts.append(block.get('text', ''))
        elif event.get('type') == 'complete':
            usage = event
    if usage is None:
        raise ValueError('Goose did not complete; partial output rejected')
    if usage.get('output_tokens', 0) >= MAX_TOKENS:
        raise ValueError('Goose exhausted the completion budget; partial output rejected')
    text = ''.join(parts)
    if not text.strip():
        raise ValueError('Goose returned no answer')
    return text, usage


def run(prompt, model):
    provider = json.loads(PROVIDER.read_text())
    if provider['engine'] != 'openai' or model not in [m['name'] for m in provider['models']]:
        raise ValueError('Unqualified Goose provider/model configuration')
    executable = shutil.which('goose') or str(Path.home() / '.local/bin/goose')
    with tempfile.TemporaryDirectory(prefix='factory-goose-staged-') as directory:
        root = Path(directory)
        config = root / 'config'
        (config / 'custom_providers').mkdir(parents=True)
        (config / 'custom_providers/strix_halo.json').write_text(json.dumps(provider))
        (config / 'config.yaml').write_text('GOOSE_TELEMETRY_ENABLED: false\n')
        instructions = root / 'packet.txt'
        instructions.write_text(prompt)  # Entire contract, source regions and repair feedback.
        env = {k: v for k, v in os.environ.items() if not k.startswith('GOOSE_')}
        env.update(GOOSE_PATH_ROOT=str(root), GOOSE_MODEL=model, GOOSE_PROVIDER='strix_halo',
                   GOOSE_MODE='auto', GOOSE_MAX_TOKENS=str(MAX_TOKENS), GOOSE_TEMPERATURE='0.7',
                   GOOSE_CONTEXT_LIMIT='131072', CONTEXT_FILE_NAMES='[]')
        command = [executable, 'run', '--instructions', str(instructions), '--no-profile',
                   '--name', 'factory-staged', '--max-turns', '1',
                   '--output-format', 'stream-json', '--stats']
        try:
            proc = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                  text=True, timeout=1200)
            raw, stderr, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            raw = exc.stdout or ''
            stderr = exc.stderr or ''
            raw = raw.decode(errors='replace') if isinstance(raw, bytes) else raw
            stderr = stderr.decode(errors='replace') if isinstance(stderr, bytes) else stderr
            code = 124
        artifact = {'engine': 'goose-qwen-staged', 'model': model, 'provider': 'strix_halo',
                    'max_tokens': MAX_TOKENS, 'request_params': provider['models'][0].get('request_params', {}),
                    'exit_code': code, 'events': raw, 'stderr': stderr}
        return artifact
