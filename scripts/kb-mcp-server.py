#!/usr/bin/env python3
"""Minimal dependency-free MCP stdio server wrapping the card-knowledge
service (localhost:4103) as real tools, instead of a curl-via-Bash
recipe. JSON-RPC 2.0 over stdin/stdout, newline-delimited."""
import json
import sys
import urllib.request
import urllib.parse

KB_BASE = "http://127.0.0.1:4103"

TOOLS = [
    {
        "name": "find_capability",
        "description": (
            "Search the engine's index of every primitive, helper, and "
            "existing card handler for a named capability (e.g. "
            "'grant unearth', 'discard hand', 'draw cards'). Use this "
            "BEFORE grepping the codebase manually — it directly answers "
            "whether a capability already exists and where."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "capability you need, e.g. 'grant unearth to graveyard artifacts'"},
                "kind": {"type": "string", "enum": ["primitive", "helper", "handler"], "description": "optional filter; omit to search everything"},
                "n": {"type": "integer", "description": "max results, default 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "similar_handlers",
        "description": (
            "Given a card's oracle text, find the nearest existing card "
            "handlers to use as templates. Use this FIRST when building a "
            "new card handler, before writing any code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "the card's oracle text"},
                "n": {"type": "integer", "description": "max results, default 2"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "check_capability",
        "description": (
            "Authoritative check for whether the engine supports a specific "
            "named event or condition (e.g. 'discard', 'event_unsupported' "
            "shapes). MISSING means the engine genuinely lacks it — park "
            "with NEEDS_PRIMITIVE immediately, do not explore the engine "
            "first. SUPPORTED means map it via existing converter/parser "
            "rules, never write new engine code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "the event or condition name to check"},
            },
            "required": ["name"],
        },
    },
]


def call_kb(path, params):
    url = f"{KB_BASE}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR calling knowledge service: {e}"


def handle(req):
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "card-knowledge-mcp", "version": "0.1.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "find_capability":
            p = {"q": args.get("query", "")}
            if args.get("kind"):
                p["kind"] = args["kind"]
            p["n"] = args.get("n", 5)
            text = call_kb("/find", p)
        elif name == "similar_handlers":
            p = {"text": args.get("text", ""), "n": args.get("n", 2)}
            text = call_kb("/similar", p)
        elif name == "check_capability":
            p = {"name": args.get("name", "")}
            text = call_kb("/caps", p)
        else:
            text = f"unknown tool: {name}"
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {"content": [{"type": "text", "text": text}]},
        }
    # unknown method
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
