#!/usr/bin/env python3
"""model_call.py — single entrypoint for calling whichever model backend a
worker is configured for. Replaces map-pipeline.sh's and engine-pipeline.sh's
separate model_call() bash functions, which had drifted apart (codex timeout
900s vs 1200s, claude --max-turns 5 vs 10, NEED-round cap configurable vs
hardcoded) and built request JSON via `python3 -c "..."` heredocs
interpolated into bash strings — the direct cause of the 2026-08-21
`curl: Argument list too long` bug (a body too large for -d "$body" as a
literal argv).

Contract unchanged from the bash functions it replaces: prompt on stdin,
final answer text on stdout, "tokens: in=X out=Y cache_r=Z cache_w=W" to
stderr. Callers redirect stderr to their own log file, same as before.

Usage: model_call.py --engine ENGINE --model MODEL [--tier map|engine]
Exit: 0 always (an empty stdout means "no answer", same meaning as before —
callers already handle that by retrying).
"""
import argparse, json, os, subprocess, sys
import urllib.request, urllib.error

OPS = os.environ.get("OPS", "/opt/development/magic-ops")

NO_TOOLS_SYSTEM = (
    "You have NO tools available for this request — no function/tool-calling "
    "capability exists on this API call. Do not attempt any tool or function "
    "call, including Read/Grep/Glob mentioned elsewhere in the prompt; that "
    "instruction does not apply here. Answer directly in plain text using "
    "only the code/context already given, following the OUTPUT FORMAT exactly."
)


def env_int(name, default):
    return int(os.environ.get(name, default))


def log_tokens(tin, tout, cr, cw):
    print(f"tokens: in={tin} out={tout} cache_r={cr} cache_w={cw}", file=sys.stderr)


def save_raw(raw):
    # Kept from the bash implementation — "empty reply" was undiagnosable
    # without the raw response on disk, used repeatedly tonight.
    ticket = os.environ.get("TICKET")
    if ticket:
        with open(f"/tmp/orch/pipeline-{ticket}-raw-last.json", "w") as f:
            f.write(raw if isinstance(raw, str) else json.dumps(raw))


def call_codex(model, tier):
    timeout = 1200 if tier == "engine" else 900
    prompt = sys.stdin.buffer.read()
    try:
        proc = subprocess.run(
            ["timeout", "-k", "30", str(timeout), "codex", "exec", "--json",
             "--sandbox", "read-only", "-m", model],
            input=prompt, capture_output=True, timeout=timeout + 40)
        raw = proc.stdout.decode(errors="replace")
    except subprocess.TimeoutExpired:
        raw = ""
    save_raw(raw)
    text, tin, tout, cr, cw = "", 0, 0, 0, 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("type") == "item.completed" and ev.get("item", {}).get("type") == "agent_message":
            text = ev["item"].get("text", "")
        elif ev.get("type") == "turn.completed":
            u = ev.get("usage", {})
            tin = u.get("input_tokens", 0)
            cr = u.get("cached_input_tokens", 0)
            cw = u.get("cache_write_input_tokens", 0)
            tout = u.get("output_tokens", 0) + u.get("reasoning_output_tokens", 0)
    log_tokens(tin, tout, cr, cw)
    return text


def call_claude(model, tier):
    max_turns = env_int("PIPE_MAX_TURNS", 10 if tier == "engine" else 5)
    timeout = 1200 if tier == "engine" else 900
    need_hint = ("" if tier == "engine" else
                 " If you need more code regions, use the NEED: mechanism described in the prompt.")
    prompt = sys.stdin.read()
    proc = subprocess.run(
        ["timeout", "-k", "30", str(timeout), "claude", "-p", "--output-format", "json",
         "--model", model, "--max-turns", str(max_turns),
         "--permission-mode", "bypassPermissions",
         "--disallowedTools", "Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill,NotebookEdit",
         "--append-system-prompt",
         "You have NO working tools — every tool call will be denied. Do not attempt any. "
         "Reply with plain text only." + need_hint],
        input=prompt, capture_output=True, text=True)
    save_raw(proc.stdout)
    try:
        result = json.loads(proc.stdout)
    except Exception:
        result = {}
    u = result.get("usage", {})
    log_tokens(u.get("input_tokens", 0), u.get("output_tokens", 0),
               u.get("cache_read_input_tokens", 0), u.get("cache_creation_input_tokens", 0))
    return result.get("result", "")


def call_openrouter(model, tier):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return ""
    max_tokens = env_int("PIPE_MAX_TOKENS_CAP", 8000)
    reasoning_tokens = env_int("PIPE_REASONING_TOKENS", 3000)
    timeout = env_int("PIPE_LOCAL_TIMEOUT", 300)
    prompt = sys.stdin.read()
    body = {
        "model": model, "max_tokens": max_tokens, "stream": False,
        "reasoning": {"max_tokens": reasoning_tokens, "exclude": True},
        "messages": [
            {"role": "system", "content": NO_TOOLS_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/daniwb/magic-ops",
            "X-Title": f"pipe-ox-{tier}",
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("openrouter: HTTP 429 rate limited", file=sys.stderr)
        else:
            print(f"openrouter: HTTP {e.code} — {e.read()[:300]}", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"openrouter: request failed: {e}", file=sys.stderr)
        return ""
    save_raw(raw)
    result = json.loads(raw)
    usage = result.get("usage", {})
    log_tokens(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
               usage.get("prompt_tokens_details", {}).get("cached_tokens", 0), 0)
    return (result["choices"][0]["message"].get("content") or "")


def call_agentic(script, model, tier, extra_args):
    # stdout captured (final answer), stderr inherited straight through to
    # whatever our own stderr is (the caller already redirected that to its
    # log file) — no need to buffer/re-print it ourselves.
    args = ["python3", os.path.join(OPS, "scripts", script), "--repo", os.getcwd(),
            "--model", model,
            "--max-turns", str(env_int("PIPE_AGENTIC_MAX_TURNS", 25)),
            "--max-tokens", str(env_int("PIPE_MAX_TOKENS_CAP", 8000))]
    args += extra_args
    if tier == "engine":
        args.append("--allow-game")
    proc = subprocess.run(args, stdin=sys.stdin, stdout=subprocess.PIPE)
    return proc.stdout.decode(errors="replace")


def call_qwen_agentic(model, tier):
    base_url = os.environ.get("PIPE_BASE_URL", "http://192.168.1.251:8080")
    return call_agentic("qwen-agentic-call.py", model, tier, ["--base-url", base_url])


def call_openrouter_agentic(model, tier):
    base_url = os.environ.get("PIPE_BASE_URL", "https://openrouter.ai/api/v1")
    reasoning_tokens = str(env_int("PIPE_REASONING_TOKENS", 3000))
    return call_agentic("openrouter-agentic-call.py", model, tier,
                         ["--base-url", base_url, "--reasoning-tokens", reasoning_tokens])


ENGINES = {
    "codex": call_codex,
    "claude": call_claude,
    "openrouter": call_openrouter,
    "openrouter-agentic": call_openrouter_agentic,
    "qwen-agentic": call_qwen_agentic,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="claude", choices=list(ENGINES))
    ap.add_argument("--model", required=True)
    ap.add_argument("--tier", default="map", choices=["map", "engine"])
    args = ap.parse_args()
    text = ENGINES[args.engine](args.model, args.tier)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
