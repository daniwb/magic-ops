#!/usr/bin/env python3
"""qwen-agentic-call.py — agentic tool-loop model_call() backend for pipe-qwen.

Plugs into map-pipeline.sh's model_call() contract exactly like the
claude/codex branches: reads the pack on stdin, prints final answer text to
stdout, logs "tokens: in=X out=Y cache_r=Z cache_w=W" to stderr (captured by
the caller into $LOG) — so ALL of map-pipeline.sh's existing gate/bugfix/
commit/push machinery works unchanged. Internally this is NOT a single
completion call: it runs a real agentic loop (read_file/grep/list_dir tools,
executed locally against --repo) instead of relying on the pre-packed code
regions, since qwen3.8 explores far more efficiently than it answers cold
from a static dump (confirmed live, ticket #3790 — see [[qwen agentic
approach]] session notes).

Two upstream findings this depends on, both confirmed live 2026-08-17:
  1. Real tool-calling works correctly on /v1/chat/completions (OpenAI
     format) against this llama-server, unlike the raw /v1/messages
     completion path map-pipeline.sh's staged branch uses.
  2. chat_template_kwargs.enable_thinking:false + Qwen3's non-thinking
     sampling preset (temp 0.7/top_p 0.8/top_k 20/min_p 0) is REQUIRED —
     without it, "thinking" is unbounded and every final-answer turn
     burns its entire budget on reasoning with zero output, even at
     24000 tokens across 5 consecutive attempts. With it: a full 20-turn
     loop (explore + correct final patch) completed in 12.5 minutes.

Usage: qwen-agentic-call.py --repo PATH [--max-turns N] [--max-tokens N]
Exit: 0 with final answer on stdout, 1 on exhaustion (empty stdout — caller
treats this exactly like claude/codex's "empty model reply").
"""
import argparse, json, os, re, subprocess, sys, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument('--repo', required=True)
ap.add_argument('--base-url', default='http://192.168.1.251:8080')
ap.add_argument('--model', default='./Qwen3.8-27B/Qwen3.8-27B-Q8_0.gguf')
ap.add_argument('--max-turns', type=int, default=25)
ap.add_argument('--max-tokens', type=int, default=8000)
a = ap.parse_args()

TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file's contents (optionally a line range) from the repo",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "grep",
        "description": "Search for a regex pattern across the repo, returns matching lines with context",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "file or directory to search, relative to repo root"},
            "context_lines": {"type": "integer"}},
            "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List files in a directory",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                        "required": ["path"]}}},
]


def run_tool(name, args):
    if name == 'read_file':
        p = os.path.join(a.repo, args['path'])
        if not os.path.abspath(p).startswith(os.path.abspath(a.repo)):
            return 'ERROR: path escapes repo'
        if not os.path.exists(p):
            return 'ERROR: file does not exist: %s' % args['path']
        lines = open(p, encoding='utf-8', errors='replace').read().splitlines()
        lo = max(0, (args.get('start_line') or 1) - 1)
        hi = min(len(lines), args.get('end_line') or len(lines))
        seg = '\n'.join('%5d %s' % (i + 1, lines[i]) for i in range(lo, hi))
        return seg[:8000]
    if name == 'grep':
        target = os.path.join(a.repo, args.get('path', '.'))
        if not os.path.abspath(target).startswith(os.path.abspath(a.repo)):
            return 'ERROR: path escapes repo'
        cmd = ['grep', '-rn', '-C', str(args.get('context_lines', 3)), '--', args['pattern'], target]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
        except Exception as e:
            return 'ERROR: %s' % e
        return out[:8000] or '(no matches)'
    if name == 'list_dir':
        p = os.path.join(a.repo, args.get('path', '.'))
        if not os.path.abspath(p).startswith(os.path.abspath(a.repo)):
            return 'ERROR: path escapes repo'
        try:
            return '\n'.join(sorted(os.listdir(p)))
        except Exception as e:
            return 'ERROR: %s' % e
    return 'ERROR: unknown tool %s' % name


SYSTEM_PROMPT = (
    "You are patching the deterministic MTG reparse pipeline (repo openmagic). "
    "You have REAL tools: read_file, grep, list_dir — use them to explore the "
    "repo yourself; ignore any '## Relevant code regions' or 'TOOL BUDGET' "
    "section below, that framing is stale, you have full real tool access with "
    "no call limit. Registered vocabulary only; never touch backend/game/. "
    "When you are ready to answer, STOP calling tools and reply with plain "
    "text ONLY, in exactly this format:\n\n"
    "EITHER a park verdict. NEEDS_PRIMITIVE is legal ONLY when every source_miss "
    "needs the SAME atomic behavior — if the examples need different behaviors, "
    "return AMBIGUOUS instead so discovery can split the ticket; never invent one "
    "umbrella primitive name:\n"
    "VERDICT: NEEDS_PRIMITIVE|SEMANTIC_GAP|AMBIGUOUS|NOT_A_SHAPE\n"
    "For NEEDS_PRIMITIVE, add exactly one single-line JSON object (no markdown) — "
    "quote paragraph EXACTLY as it appears in the card's real oracle text (read_file "
    "the carddb record yourself to verify, don't paraphrase):\n"
    'CAPABILITY_JSON: {"key":"lowercase_snake_case","summary":"short description",'
    '"specification":{"required_behavior":"one precise atomic behavior",'
    '"source_misses":[{"card":"ONE representative exact card name",'
    '"paragraph":"exact relevant oracle paragraph","required_behavior":'
    '"the identical required_behavior text"}],"negative_examples":'
    '["adjacent behavior that must not change"],"expected_unlock":0}}\n'
    "REASON: <one line>\n\n"
    "OR one or more edit blocks (exact-match search text, unique in the file):\n"
    "<<<FILE path/relative/to/repo\n<<<SEARCH\nexact existing lines (copy verbatim, "
    "WITHOUT line-number prefixes)\n===REPLACE\nreplacement lines\n>>>END\n"
    "Each block has EXACTLY ONE <<<SEARCH and EXACTLY ONE ===REPLACE — decide your "
    "final replacement content before writing the block, never a second ===REPLACE "
    "inside the same block.\n\n"
    "End with: EXPECT: <one line>\nSTOP immediately after that line, no more prose "
    "or tool calls."
)

# The pack arrives on stdin exactly as map-pipeline-pack.py built it (ticket
# framing + example cards + pre-fetched code regions + NEED/output-format
# boilerplate written for the claude/codex staged branches). Only the
# ticket-framing preamble is useful here — the pre-fetched regions are a
# static, possibly-incomplete snapshot that real tool access supersedes, and
# the staged OUTPUT FORMAT/TOOL BUDGET text would just confuse a model that
# genuinely does have tools this time.
raw_pack = sys.stdin.read()
task_desc = raw_pack.split('## Relevant code regions')[0].strip()

messages = [{"role": "user", "content": task_desc}]
NUDGE_AT = max(1, a.max_turns - 6)  # keep enough final turns to actually answer
tin = tout = tcr = tcw = 0

for turn in range(a.max_turns):
    call_messages = messages
    if turn >= NUDGE_AT:
        call_messages = messages + [{"role": "user", "content":
            "You have gathered enough context. Stop calling tools now and write your "
            "final answer (edit blocks or a park verdict, exact format from the system "
            "prompt) using what you already know. Do not verify further."}]
    body = {
        "model": a.model, "max_tokens": a.max_tokens, "tools": TOOLS,
        "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + call_messages,
    }
    req = urllib.request.Request(
        a.base_url.rstrip('/') + '/v1/chat/completions',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            result = json.load(resp)
    except Exception as e:
        print('turn %d: request failed: %s' % (turn, e), file=sys.stderr)
        break
    msg = result['choices'][0]['message']
    usage = result.get('usage', {})
    tin += usage.get('prompt_tokens', 0) - usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)
    tcr += usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)
    tout += usage.get('completion_tokens', 0)
    print('--- turn %d --- usage=%s' % (turn, usage), file=sys.stderr)
    if msg.get('tool_calls'):
        messages.append({"role": "assistant", "content": msg.get('content') or '',
                          "tool_calls": msg['tool_calls']})
        for tc in msg['tool_calls']:
            fname = tc['function']['name']
            try:
                fargs = json.loads(tc['function']['arguments'])
            except Exception:
                fargs = {}
            print('CALL %s(%r)' % (fname, fargs), file=sys.stderr)
            out = run_tool(fname, fargs)
            print('  -> %s' % out[:200].replace('\n', ' | '), file=sys.stderr)
            messages.append({"role": "tool", "tool_call_id": tc['id'], "content": out})
        continue
    elif (msg.get('content') or '').strip():
        print('tokens: in=%d out=%d cache_r=%d cache_w=%d' % (tin, tout, tcr, tcw), file=sys.stderr)
        sys.stdout.write(msg['content'])
        sys.exit(0)
    else:
        print('  [empty content AND no tool_calls — discarding, retrying]', file=sys.stderr)

print('tokens: in=%d out=%d cache_r=%d cache_w=%d' % (tin, tout, tcr, tcw), file=sys.stderr)
print('exhausted %d turns without a final answer' % a.max_turns, file=sys.stderr)
sys.exit(1)
