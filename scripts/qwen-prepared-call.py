#!/usr/bin/env python3
"""One-shot, no-tools Qwen adapter for evidence-complete Factory tickets.

The model receives a fully prepared Ticket Execution Bundle and returns only
the constrained patch/decision text.  The Factory harness owns mutation and
gates.  This intentionally differs from qwen-agentic-call.py: it is the
default low-latency profile when deterministic preparation has already removed
the need for repository discovery.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


ap = argparse.ArgumentParser()
ap.add_argument('--base-url', default='http://192.168.1.251:8080')
ap.add_argument('--model', default='./Qwen3.8-27B/Qwen3.8-27B-Q8_0.gguf')
ap.add_argument('--max-tokens', type=int, default=2000)
ap.add_argument('--timeout', type=int, default=900)
args = ap.parse_args()

SYSTEM = '''You are the prepared-direct implementation profile of a software
factory. You have NO tools and cannot inspect or edit the repository. The
ticket bundle contains all authoritative evidence you need. The entire answer
is passed directly to a strict machine parser.

For every file edit, emit only this exact block grammar (including the file
path), with no text before, between, or after blocks:
<<<FILE relative/path.py
<<<SEARCH
exact existing text
===REPLACE
replacement text
>>>END

For a new file use <<<NEWFILE relative/path.py, then its full content, then
>>>END. Every repair must repeat an explicit <<<FILE or <<<NEWFILE header.
Never use Markdown fences, bare SEARCH:/REPLACE: labels, unified diffs,
line numbers, or prose. If the evidence is contradictory, emit only a
structured VERDICT. Keep the patch minimal. The harness, not you, will apply
it and run tests.'''

packet = sys.stdin.read()
body = {
    'model': args.model,
    'max_tokens': args.max_tokens,
    'temperature': 0.7,
    'top_p': 0.8,
    'top_k': 20,
    'min_p': 0,
    # llama.cpp's non-streaming OpenAI response path can terminate with an
    # empty HTTP body after it has already decoded the completion (observed
    # against Qwen3.8 on 2026-08-28: /slots showed 527 decoded tokens while
    # urllib received zero bytes). Its SSE path carries every token reliably.
    'stream': True,
    # This llama.cpp build otherwise omits the final usage event from SSE,
    # which made a successful local run indistinguishable from zero tokens.
    'stream_options': {'include_usage': True},
    # Required for this llama-server/Qwen template: without it the model can
    # spend the entire completion budget on hidden reasoning and emit no patch.
    'chat_template_kwargs': {'enable_thinking': False},
    'messages': [
        {'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': packet},
    ],
}
request = urllib.request.Request(
    args.base_url.rstrip('/') + '/v1/chat/completions',
    data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        parts, usage = [], {}
        for wire in response:
            line = wire.decode('utf-8', errors='replace').strip()
            if not line.startswith('data: '):
                continue
            payload = line[6:]
            if payload == '[DONE]':
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(event.get('usage'), dict):
                usage.update(event['usage'])
            choices = event.get('choices') or []
            if choices:
                delta = choices[0].get('delta') or {}
                # Thinking is disabled, but keep the adapter tolerant of a
                # server that nevertheless serializes visible completion text
                # through a reasoning field rather than content.
                text = delta.get('content') or delta.get('reasoning_content')
                if text:
                    parts.append(text)
except urllib.error.HTTPError as exc:
    print('qwen-prepared: HTTP %s: %s' % (exc.code, exc.read()[:500]), file=sys.stderr)
    raise SystemExit(1)
except Exception as exc:
    print('qwen-prepared: request failed: %s' % exc, file=sys.stderr)
    raise SystemExit(1)

cached = usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)
prompt = usage.get('prompt_tokens', 0)
print('tokens: in=%d out=%d cache_r=%d cache_w=%d' %
      (max(0, prompt - cached), usage.get('completion_tokens', 0), cached, 0),
      file=sys.stderr)
sys.stdout.write(''.join(parts))
