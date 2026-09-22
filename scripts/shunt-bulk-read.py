#!/usr/bin/env python3
"""PreToolUse hook for the claude-agentic-test engine: shunts large Read
calls to a local model for a summary instead of letting Claude read the raw
file, mirroring Spotify's bulk-reader token-reduction pattern
(https://engineering.atspotify.com/2026/9/portal-by-spotify-cut-my-claude-code-token-usage-by-90).

Wired in ONLY for the claude-agentic-test adapter via
scripts/claude-agentic-test-settings.json — the production claude-agentic
engine never loads this hook, so this is opt-in per profile, not global.

Two interchangeable backends (SHUNT_BACKEND, default llama-server):
  llama-server — the unmetered Qwen3.8-27B-Q8_0 llama-server box already
    registered as factory-ng's "qwen-local" worker (config/factory-ng-workers
    .json, 192.168.1.251:8080), same box qwen-prepared-call.py/
    qwen-agentic-call.py use. Two llama.cpp quirks those adapters already
    work around apply here too: this build returns an empty body on
    non-streaming completions (SSE is reliable), and
    chat_template_kwargs.enable_thinking must be false or the model spends
    its whole budget on hidden reasoning and emits nothing. Slow: measured
    ~145s for a 1154-line file (CPU-bound generation).
  openrouter — minimax/minimax-m3:free, the same free-tier model factory-ng's
    "minimax-m3-free" worker uses, via the same shared, file-locked cooldown
    state (scripts/openrouter_cooldown.py) that worker's usage_policy
    "openrouter-cooldown" reads/writes, so the shunt backs off identically on
    a 429 instead of racing real ticket dispatch for the same free-tier
    budget. Needs OPENROUTER_API_KEY (magic-ops/.env, gitignored). Skips
    (fails open) rather than calls out during an active cooldown.

Deliberately does NOT touch the old dispatcher's LOCAL_GPU_OFF kill switch or
ollama-triage.sh's qwen3-coder box — those belong to the pre-factory-ng
dispatcher lane, a separate system. Factory-ng's own gating (the worker's
`enabled` flag in config/factory-ng-workers.json, plus the controller's
state/factory-ng-worker-pauses.json) already fully controls whether this
hook's engine ever runs at all.

Contract: read the PreToolUse hook JSON on stdin; for a Read of a file over
the line threshold, print a "deny" hookSpecificOutput whose
permissionDecisionReason carries the summary (Claude sees the reason text in
place of the file). Any failure — missing file, local model unreachable,
bad JSON — fails OPEN (prints nothing, exit 0) so the shunt can never block
real work; it can only make a read cheaper.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openrouter_cooldown

BACKEND = os.environ.get("SHUNT_BACKEND", "llama-server")
LINE_THRESHOLD = int(os.environ.get("SHUNT_LINE_THRESHOLD", "350"))
MAX_TOKENS = int(os.environ.get("SHUNT_MAX_TOKENS", "800"))
# Measured 2026-09-05 against the llama-server box: a 1154-line file took
# ~145s end to end (CPU-bound generation, not network). A short timeout
# mostly just fails open and silently loses the savings, so default high
# enough to actually get a summary back; tune down once real latency on your
# hardware (or the openrouter backend, which is much faster) is known.
MAX_TIME = int(os.environ.get("SHUNT_MAX_TIME", "180"))

LLAMA_BASE_URL = os.environ.get("SHUNT_BASE_URL", "http://192.168.1.251:8080")
LLAMA_MODEL = os.environ.get("SHUNT_MODEL", "Qwen3.8-27B-Q8_0")

OPENROUTER_MODEL = os.environ.get("SHUNT_OPENROUTER_MODEL", "minimax/minimax-m3:free")

SYSTEM = (
    "Summarize source files for a coding agent that needs their structure, "
    "not every line: exported/public symbols with exact signatures, key "
    "types/constants, what each function does in one line, and any "
    "non-obvious control flow. Preserve exact names and signatures verbatim "
    "so they can be grepped for later. Be dense, not chatty."
)


SHUNT_EVENT = {}


def record_decision(decision, reason):
    """Measure whether the experiment actually treated a read; never log source."""
    try:
        path = Path(os.environ.get('SHUNT_TELEMETRY_PATH',
                    '/opt/development/magic-ops/state/factory-ng-shunt.jsonl'))
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {'schema': 'factory.shunt-decision/v1', 'ts': time.time(),
                 'backend': BACKEND, 'decision': decision, 'reason': reason,
                 'session_id': SHUNT_EVENT.get('session_id'),
                 'tool_use_id': SHUNT_EVENT.get('tool_use_id')}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(value) + '\n').encode())
        finally:
            os.close(fd)
    except OSError:
        pass


def allow(reason='not_eligible'):
    record_decision('pass_through', reason)
    sys.exit(0)


def deny(reason):
    record_decision('summarized', 'summary_delivered')
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def summarize_llama_server(path, content):
    body = {
        "model": LLAMA_MODEL,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "FILE: %s\n\n%s" % (path, content)},
        ],
    }
    req = urllib.request.Request(
        LLAMA_BASE_URL.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    parts = []
    with urllib.request.urlopen(req, timeout=MAX_TIME) as resp:
        for wire in resp:
            line = wire.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                text = delta.get("content") or delta.get("reasoning_content")
                if text:
                    parts.append(text)
    return "".join(parts).strip()


class SkipShunt(Exception):
    """Raised to fail open without it looking like a real transport error."""


def summarize_openrouter(path, content):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SkipShunt("OPENROUTER_API_KEY not set")
    cooldown = openrouter_cooldown.status()
    if not cooldown["allowed"]:
        raise SkipShunt("openrouter cooldown active for %ds" % cooldown["remaining_seconds"])
    body = {
        "model": OPENROUTER_MODEL,
        "max_tokens": MAX_TOKENS,
        "stream": False,
        "reasoning": {"exclude": True},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "FILE: %s\n\n%s" % (path, content)},
        ],
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % api_key,
            "HTTP-Referer": "https://github.com/daniwb/magic-ops",
            "X-Title": "shunt-bulk-read",
        })
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=MAX_TIME) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            openrouter_cooldown.record_rate_limit(OPENROUTER_MODEL)
        raise
    result = json.loads(raw)
    choices = result.get("choices") or []
    if not choices:
        return ""
    openrouter_cooldown.record_success(started, OPENROUTER_MODEL)
    return (choices[0].get("message") or {}).get("content", "").strip()


def summarize(path, content):
    if BACKEND == "openrouter":
        return summarize_openrouter(path, content)
    return summarize_llama_server(path, content)


def main():
    global SHUNT_EVENT
    try:
        event = json.load(sys.stdin)
    except Exception:
        allow()
    SHUNT_EVENT = event
    if event.get("tool_name") != "Read":
        allow()
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path")
    if not path or not os.path.isfile(path):
        allow()
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        # A scoped read: Claude already asked for a specific range, almost
        # certainly to get exact copyable text for a SEARCH/REPLACE block
        # after seeing a summary. Never shunt this or exact-text edits on
        # large files become impossible — only whole-file reads get summarized.
        allow('scoped_read')
    try:
        with open(path, "r", errors="strict") as fh:
            lines = fh.readlines()
    except Exception:
        allow()  # binary or unreadable — let the real tool handle/reject it
        return
    if len(lines) <= LINE_THRESHOLD:
        allow()
    try:
        summary = summarize(path, "".join(lines))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, SkipShunt) as exc:
        allow('summary_failed:' + type(exc).__name__)
        return
    if not summary:
        allow('empty_summary')
        return
    model_label = OPENROUTER_MODEL if BACKEND == "openrouter" else LLAMA_MODEL
    deny(
        "Direct Read blocked: %s is %d lines (> %d), routed to %s "
        "for a summary to save tokens. If you need exact lines for an edit "
        "(e.g. a SEARCH/REPLACE block), ask for that specific line range "
        "with Read's offset/limit instead of the whole file.\n\n"
        "--- local-model summary ---\n%s"
        % (path, len(lines), LINE_THRESHOLD, model_label, summary)
    )


if __name__ == "__main__":
    main()
