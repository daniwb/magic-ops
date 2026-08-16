#!/usr/bin/env python3
"""codex-usage-fetch — one-shot fetch of Codex's account rate-limit snapshot.

No public `codex` CLI flag exposes usage (confirmed 2026-08-16 against
codex-cli 0.147.0: no `usage`/`quota`/`limit` subcommand). The interactive
TUI's own status bar gets it via the `codex app-server` JSON-RPC protocol's
`account/rateLimits/read` method (confirmed live: `GetAccountRateLimitsResponse`
in `codex app-server generate-json-schema`), so this spawns the app-server,
does the initialize handshake, calls that method, and prints one line of
JSON to stdout: {"used_pct": int, "resets_at": int|null, "window_mins": int|null,
"secondary_used_pct": int|null, "secondary_resets_at": int|null}.

Exit 0 on success, nonzero on any failure (auth, timeout, malformed response)
— callers should fail-open on nonzero, same convention as lib-pace-gate.sh's
Anthropic usage fetch.

Usage: codex-usage-fetch.py [--timeout SECONDS]
"""
import argparse, json, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument('--timeout', type=float, default=15.0)
a = ap.parse_args()

p = subprocess.Popen(['codex', 'app-server'], stdin=subprocess.PIPE,
                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)


def send(obj):
    p.stdin.write(json.dumps(obj) + '\n')
    p.stdin.flush()


def recv_matching(want_id, deadline):
    while time.time() < deadline:
        line = p.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get('id') == want_id and ('result' in ev or 'error' in ev):
            return ev
    return None


try:
    deadline = time.time() + a.timeout
    send({'id': 1, 'method': 'initialize',
          'params': {'clientInfo': {'name': 'codex-usage-fetch', 'version': '1.0'}}})
    init_resp = recv_matching(1, deadline)
    if init_resp is None or 'result' not in init_resp:
        sys.exit(1)

    send({'id': 2, 'method': 'account/rateLimits/read', 'params': None})
    resp = recv_matching(2, deadline)
    if resp is None or 'result' not in resp:
        sys.exit(1)

    rl = resp['result'].get('rateLimits') or {}
    primary = rl.get('primary') or {}
    secondary = rl.get('secondary') or {}
    out = {
        'used_pct': primary.get('usedPercent'),
        'resets_at': primary.get('resetsAt'),
        'window_mins': primary.get('windowDurationMins'),
        'secondary_used_pct': secondary.get('usedPercent'),
        'secondary_resets_at': secondary.get('resetsAt'),
        'plan_type': rl.get('planType'),
    }
    if out['used_pct'] is None:
        sys.exit(1)
    print(json.dumps(out))
finally:
    p.terminate()
    try:
        p.wait(timeout=3)
    except Exception:
        p.kill()
