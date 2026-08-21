#!/usr/bin/env python3
"""openrouter-agentic-call.py — agentic tool-loop model_call() backend for
pipe-ox, against OpenRouter's free `stealth/ox-alpha` reasoning model.

Adapted from qwen-agentic-call.py (same TOOLS/run_tool/loop shape — real
read_file/grep/list_dir executed locally against --repo, model_call()'s
stdin-pack-in/stdout-text-out/"tokens: ..."-to-stderr contract honored
exactly, so the surrounding gate/bugfix/commit/push machinery in
map-pipeline.sh/engine-pipeline.sh needs zero changes). Built in response to
pipe-ox's staged (single-shot, NEED-region-fetch) mode repeatedly hitting
its round cap (2026-08-21: 3 of ~18 tickets in the first live hour exhausted
PIPE_MAX_NEED_ROUNDS=4 outright) — the exact same symptom that drove
qwen-agentic-call.py's own creation: a model that explores far more
efficiently with real tools than through pre-packed context + a bounded
back-and-forth NEED protocol. OpenRouter's own listing describes ox-alpha
as "designed for coding, sustained agentic work" — staged single-shot
answering works against that, not with it.

Differences from qwen-agentic-call.py (OpenRouter vs. local llama-server):
  - Real HTTPS endpoint + Bearer auth (OPENROUTER_API_KEY), not a bare
    local server.
  - Reasoning control via OpenRouter's own `reasoning: {max_tokens,
    exclude}` parameter (confirmed live 2026-08-21: reasoning_tokens:0 with
    this set, no runaway) instead of Qwen's chat_template_kwargs/sampling-
    preset dance — no evidence ox-alpha needs temperature/top_p/top_k
    overrides, so none are sent.
  - NEWFILE block format is documented in SYSTEM_PROMPT from the start
    (qwen-agentic-call.py only learned this the hard way on 2026-08-20 for
    the engine tier — carrying the lesson forward here instead of
    rediscovering it).
  - Basic HTTP 429 handling: back off and report distinctly rather than
    treating a rate-limit response as a generic empty reply.

Usage: openrouter-agentic-call.py --repo PATH [--max-turns N] [--max-tokens N]
Exit: 0 with final answer on stdout, 1 on exhaustion (empty stdout — caller
treats this exactly like the staged branch's "empty model reply").
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request, urllib.error

ap = argparse.ArgumentParser()
ap.add_argument('--repo', required=True)
ap.add_argument('--base-url', default='https://openrouter.ai/api/v1')
ap.add_argument('--model', default='stealth/ox-alpha')
ap.add_argument('--max-turns', type=int, default=25)
ap.add_argument('--max-tokens', type=int, default=8000)
ap.add_argument('--reasoning-tokens', type=int, default=3000)
ap.add_argument('--allow-game', action='store_true',
                 help='engine tier: backend/game/ edits are allowed (mirrors map-pipeline-apply.py\'s flag)')
a = ap.parse_args()

API_KEY = os.environ.get('OPENROUTER_API_KEY')
if not API_KEY:
    print('OPENROUTER_API_KEY not set', file=sys.stderr)
    sys.exit(1)

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


if a.allow_game:
    SCOPE_RULE = (
        "This is the ENGINE tier: backend/game/ edits ARE allowed. Prefer "
        "extending an existing executor/switch over inventing a new mechanism. "
        "Your diff MUST include a NEW test function (a line starting 'func "
        "Test...') in a NEW _test.go file — a real behavior test, not just an "
        "assertion of current behavior — or the patch is rejected outright "
        "regardless of whether the code itself is correct. If this demand is "
        "actually FRAMEWORK-sized (new event system, new cross-cutting "
        "dispatch/state), do NOT attempt it — return a park verdict instead."
    )
else:
    SCOPE_RULE = "Registered vocabulary only; never touch backend/game/."

SYSTEM_PROMPT = (
    "You are patching the deterministic MTG reparse pipeline (repo openmagic). "
    "You have REAL tools: read_file, grep, list_dir — use them to explore the "
    "repo yourself; ignore any '## Relevant code regions' or 'TOOL BUDGET' or "
    "'NEED:' instructions in the prompt below, that framing is stale, you have "
    "full real tool access with no call limit. " + SCOPE_RULE + " "
    "When you are ready to answer, STOP calling tools and reply with plain "
    "text ONLY, in exactly this format:\n\n"
    "EITHER a park verdict. NEEDS_PRIMITIVE is legal ONLY when every source_miss "
    "needs the SAME atomic behavior — if the examples need different behaviors, "
    "return AMBIGUOUS instead so discovery can split the ticket; never invent one "
    "umbrella primitive name:\n"
    "VERDICT: NEEDS_PRIMITIVE|SEMANTIC_GAP|AMBIGUOUS|NOT_A_SHAPE\n"
    "For NEEDS_PRIMITIVE, add exactly one single-line JSON object (no markdown) — "
    "quote paragraph EXACTLY as it appears in the card's real oracle text (read_file "
    "the carddb record yourself to verify, don't paraphrase). The dispatcher "
    "REQUIRES exactly one representative source_miss per demand — if multiple "
    "cards/paragraphs share the behavior, pick the single clearest one, do not "
    "list more than one:\n"
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
    "To CREATE a brand-new file (e.g. a new _test.go file — SEARCH/REPLACE only "
    "works on files that already exist), use a NEWFILE block instead:\n"
    "<<<NEWFILE path/relative/to/repo\nfull file content\n>>>END\n\n"
    "End with: EXPECT: <one line>\nSTOP immediately after that line, no more prose "
    "or tool calls."
)

# Only the ticket-framing preamble is useful here — real tool access
# supersedes the pre-fetched/NEED-protocol boilerplate written for the
# staged branch.
raw_pack = sys.stdin.read()
task_desc = raw_pack.split('## Relevant code regions')[0].strip()

messages = [{"role": "user", "content": task_desc}]
NUDGE_AT = max(1, a.max_turns - 6)
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
        "reasoning": {"max_tokens": a.reasoning_tokens, "exclude": True},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + call_messages,
    }
    req = urllib.request.Request(
        a.base_url.rstrip('/') + '/chat/completions',
        data=json.dumps(body).encode(),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % API_KEY,
            'HTTP-Referer': 'https://github.com/daniwb/magic-ops',
            'X-Title': 'pipe-ox-agentic',
        })
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print('turn %d: HTTP 429 rate limited, backing off 30s' % turn, file=sys.stderr)
            time.sleep(30)
            continue
        print('turn %d: HTTP %d: %s' % (turn, e.code, e.read()[:300]), file=sys.stderr)
        break
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
