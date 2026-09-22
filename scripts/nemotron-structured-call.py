#!/usr/bin/env python3
"""Bounded, model-specific OpenRouter adapter for Nemotron 3.5 Lightning.

The model may inspect exact source ranges once, then must call submit_edits.
It never supplies SEARCH text: the adapter derives that text byte-for-byte
from the requested line range and renders the existing Factory block grammar.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import openrouter_cooldown


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--model", default="nvidia/nemotron-3.5-lightning:free")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--allowed-path", action="append", default=[])
    parser.add_argument("--required-path", action="append", default=[])
    parser.add_argument("--max-tokens", type=int, default=3500)
    parser.add_argument("--timeout", type=int, default=300)
    return parser.parse_args()


ARGS = parse_args()
REPO = ARGS.repo.resolve()
ALLOWED = tuple(dict.fromkeys(ARGS.allowed_path))
REQUIRED = tuple(dict.fromkeys(ARGS.required_path))
API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not API_KEY:
    raise SystemExit("OPENROUTER_API_KEY not set")
if not ALLOWED:
    raise SystemExit("at least one --allowed-path is required")
if any(path not in ALLOWED for path in REQUIRED):
    raise SystemExit("every --required-path must also be allowed")


def safe_path(relative):
    if relative not in ALLOWED:
        raise ValueError("path is outside the Ticket allowlist: %s" % relative)
    path = (REPO / relative).resolve()
    if not path.is_relative_to(REPO) or not path.is_file():
        raise ValueError("path is not a readable repository file: %s" % relative)
    return path


def source_lines(relative):
    return safe_path(relative).read_text(encoding="utf-8").splitlines()


def read_range(arguments):
    relative = arguments.get("path", "")
    lines = source_lines(relative)
    start = int(arguments.get("start_line", 1))
    end = int(arguments.get("end_line", start))
    if start < 1 or end < start or end > len(lines) or end - start + 1 > 160:
        raise ValueError("invalid or over-wide source range")
    content = "\n".join(lines[start - 1:end])
    return json.dumps({
        "path": relative,
        "start_line": start,
        "end_line": end,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "content": content,
        "note": "content is raw and unnumbered; preserve its indentation",
    }, ensure_ascii=False)


READ_TOOL = {
    "type": "function",
    "function": {
        "name": "read_range",
        "description": "Read one exact, unnumbered source range from a Ticket-allowed file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "enum": list(ALLOWED)},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
            },
            "required": ["path", "start_line", "end_line"],
            "additionalProperties": False,
        },
    },
}

SUBMIT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_edit",
        "description": (
            "Submit one edit. Call once per changed file/range, in parallel when needed. "
            "The range identifies existing source and replacement is complete compile-valid text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "enum": list(ALLOWED)},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
                "replacement": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Exact multiline replacement with literal newline characters.",
                },
            },
            "required": ["path", "start_line", "end_line", "replacement"],
            "additionalProperties": False,
        },
    },
}

SYSTEM = """You are the Nemotron structured-edit profile for Factory NG.
The user supplies a complete, frozen implementation packet. Work only on the
requested behavior and Ticket-allowed paths. The harness—not you—applies edits,
runs tests, commits, or integrates anything.

You have one bounded inspection phase. Use read_range only when you need raw,
unnumbered text or exact surrounding syntax; multiple read_range calls may be
made in that one response. Do not browse broadly and do not ask questions.

In the submission phase you must call submit_edit once for every changed
file/range (parallel calls are allowed). Each call replaces an inclusive
existing line range. replacement must contain literal newlines between source
lines; never collapse several statements onto one line. Provide the entire
replacement for that range, with correct indentation and syntax. Never
include line-number prefixes, markdown fences, patch markers, prose, or an
undeclared variable. Every required path must receive an edit. Preserve
adjacent behavior and mentally type-check every replacement. The adapter will
derive exact SEARCH text from the source and syntax-check the candidate before
the deterministic harness checks semantics and scope."""


def api_call(messages, tools, tool_choice, reasoning, max_tokens=None):
    cooldown = openrouter_cooldown.status()
    if not cooldown["allowed"]:
        print("openrouter: cooldown active for %ds until %s" %
              (cooldown["remaining_seconds"], cooldown.get("paused_until", "unknown")),
              file=sys.stderr)
        raise SystemExit(76)
    request_started = time.time()
    body = {
        "model": ARGS.model,
        "messages": messages,
        "max_tokens": max_tokens or ARGS.max_tokens,
        "reasoning": reasoning,
        "temperature": 1.0,
        "top_p": 0.95,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice
        body["parallel_tool_calls"] = True
    request = urllib.request.Request(
        ARGS.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + API_KEY,
            "HTTP-Referer": "https://github.com/daniwb/magic-ops",
            "X-Title": "factory-ng-nemotron-structured",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=ARGS.timeout) as response:
            result = json.load(response)
            if not result.get("choices"):
                error = result.get("error") or {}
                if error.get("code") == 429:
                    cooldown = openrouter_cooldown.record_rate_limit(ARGS.model)
                    print("openrouter: embedded HTTP 429; provider paused %ds until %s" %
                          (cooldown["cooldown_seconds"], cooldown["paused_until"]),
                          file=sys.stderr)
                    raise SystemExit(76)
                raise RuntimeError("OpenRouter response without choices: %s" %
                                   json.dumps(result, sort_keys=True)[:1200])
            openrouter_cooldown.record_success(request_started, ARGS.model)
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        if exc.code == 429:
            cooldown = openrouter_cooldown.record_rate_limit(ARGS.model)
            print("openrouter: HTTP 429; provider paused %ds until %s" %
                  (cooldown["cooldown_seconds"], cooldown["paused_until"]),
                  file=sys.stderr)
            raise SystemExit(76)
        raise RuntimeError("OpenRouter HTTP %d: %s" % (exc.code, detail)) from exc


def add_usage(totals, result):
    usage = result.get("usage", {})
    cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
    totals["input"] += max(0, usage.get("prompt_tokens", 0) - cached)
    totals["cache"] += cached
    totals["output"] += usage.get("completion_tokens", 0)
    print("phase usage=%s" % json.dumps(usage, sort_keys=True), file=sys.stderr)


def assistant_message(message):
    value = {"role": "assistant", "content": message.get("content") or ""}
    if message.get("tool_calls"):
        value["tool_calls"] = message["tool_calls"]
    return value


def validated_operations(operations, require_all=True):
    if not isinstance(operations, list) or not operations:
        raise ValueError("submit_edit did not contain operations")
    edited_paths = {item.get("path") for item in operations}
    missing = set(REQUIRED) - edited_paths
    if require_all and missing:
        raise ValueError("required paths were not edited: %s" % ", ".join(sorted(missing)))
    occupied = {}
    normalized = []
    for operation in operations:
        relative = operation.get("path", "")
        lines = source_lines(relative)
        start = int(operation.get("start_line", 0))
        end = int(operation.get("end_line", 0))
        if start < 1 or end < start or end > len(lines):
            raise ValueError("invalid edit range for %s" % relative)
        for old_start, old_end in occupied.setdefault(relative, []):
            if not (end < old_start or start > old_end):
                raise ValueError("overlapping edit ranges for %s" % relative)
        occupied[relative].append((start, end))
        replacement = operation.get("replacement", "").strip("\n")
        if not replacement or any(marker in replacement for marker in ("<<<", "===REPLACE", ">>>END")):
            raise ValueError("invalid replacement payload for %s" % relative)
        search = "\n".join(lines[start - 1:end])
        if replacement == search:
            raise ValueError("no-op replacement for %s" % relative)
        normalized.append({"path": relative, "start": start, "end": end,
                           "search": search, "replacement": replacement,
                           "replacement_lines": replacement.splitlines()})
    return normalized


def syntax_check(operations):
    by_path = {}
    for operation in operations:
        by_path.setdefault(operation["path"], []).append(operation)
    errors = []
    for relative, edits in by_path.items():
        candidate = source_lines(relative)
        for edit in sorted(edits, key=lambda item: item["start"], reverse=True):
            candidate[edit["start"] - 1:edit["end"]] = edit["replacement_lines"]
        text = "\n".join(candidate) + "\n"
        if relative.endswith(".py"):
            try:
                ast.parse(text, filename=relative)
            except SyntaxError as exc:
                errors.append("%s:%s Python syntax: %s" % (relative, exc.lineno, exc.msg))
        elif relative.endswith(".go"):
            checked = subprocess.run(["gofmt"], input=text, text=True,
                                     capture_output=True, timeout=30)
            if checked.returncode:
                errors.append("%s Go syntax: %s" % (relative, checked.stderr.strip()[-500:]))
    if errors:
        raise ValueError("; ".join(errors))


def render_edits(arguments):
    operations = validated_operations(arguments)
    syntax_check(operations)
    blocks = []
    for operation in operations:
        relative = operation["path"]
        search = operation["search"]
        replacement = operation["replacement"]
        blocks.append("<<<FILE %s\n<<<SEARCH\n%s\n===REPLACE\n%s\n>>>END" %
                      (relative, search, replacement))
    return "\n".join(blocks) + "\nEXPECT: Ticket behavior and required gates pass"


def main():
    packet = sys.stdin.read()
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": packet},
    ]
    totals = {"input": 0, "cache": 0, "output": 0}
    try:
        inspection = api_call(messages, [READ_TOOL], "auto",
                              {"effort": "low", "exclude": True})
        add_usage(totals, inspection)
        message = inspection["choices"][0]["message"]
        messages.append(assistant_message(message))
        for call in message.get("tool_calls") or []:
            if call.get("function", {}).get("name") != "read_range":
                raise ValueError("unexpected inspection tool")
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
                content = read_range(arguments)
            except Exception as exc:
                content = json.dumps({"error": str(exc)})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
        messages.append({
            "role": "user",
            "content": (
                "Inspection is complete. Write a concise implementation plan of at most 500 "
                "tokens. Restate every acceptance boundary, the exact data shape, and how each "
                "required file changes. Check that all introduced variables are declared. Do not "
                "emit patch blocks or call tools."
            ),
        })
        planned = api_call(messages, [], None, {"effort": "none", "exclude": True},
                           max_tokens=1200)
        add_usage(totals, planned)
        plan_message = planned["choices"][0]["message"]
        plan_text = (plan_message.get("content") or "").strip()
        if not plan_text:
            raise ValueError("Nemotron did not produce a bounded implementation plan")
        messages.append({"role": "assistant", "content": plan_text})
        messages.append({
            "role": "user",
            "content": (
                "Now execute that plan. Submit the complete minimal patch via submit_edit calls, "
                "one call per changed range. Use exact inclusive ranges and literal multiline "
                "replacement text. Every required path must be edited. Return no prose."
            ),
        })
        rendered = None
        accepted_operations = []
        for submission_round in range(2):
            submission = api_call(
                messages,
                [SUBMIT_TOOL],
                {"type": "function", "function": {"name": "submit_edit"}},
                {"effort": "none", "exclude": True},
                max_tokens=1800,
            )
            add_usage(totals, submission)
            final_message = submission["choices"][0]["message"]
            calls = [item for item in final_message.get("tool_calls") or []
                     if item.get("function", {}).get("name") == "submit_edit"]
            if not calls:
                raise ValueError("Nemotron did not make a submit_edit call")
            try:
                operations = [json.loads(call["function"].get("arguments") or "{}")
                              for call in calls]
                for operation in operations:
                    print("submit_edit path=%s range=%s-%s" %
                          (operation.get("path"), operation.get("start_line"),
                           operation.get("end_line")), file=sys.stderr)
                rendered = render_edits(accepted_operations + operations)
                break
            except Exception as validation_error:
                if submission_round:
                    raise
                submitted_paths = {item.get("path") for item in operations}
                missing_paths = sorted(set(REQUIRED) - submitted_paths)
                if missing_paths:
                    try:
                        partial = validated_operations(operations, require_all=False)
                        syntax_check(partial)
                        accepted_operations = operations
                    except ValueError as partial_error:
                        # Do not retain unsafe partial work. Feed the more useful
                        # syntax/range error back and spend the correction on a
                        # complete replacement submission.
                        validation_error = partial_error
                        missing_paths = []
                messages.append(assistant_message(final_message))
                for call in calls:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps({
                            "status": "accepted_pending_required_coverage" if missing_paths else "rejected",
                            "error": str(validation_error),
                        }),
                    })
                if missing_paths:
                    correction = (
                        "The submitted edits passed range and syntax preflight and are retained. "
                        "Submit edits ONLY for these still-missing required paths: %s. Do not "
                        "repeat an accepted path. Return no prose." % ", ".join(missing_paths)
                    )
                else:
                    correction = (
                        "The adapter rejected that submission before mutation. Correct the exact "
                        "reported problem and submit the complete patch again. Keep every required path."
                    )
                messages.append({
                    "role": "user",
                    "content": correction,
                })
        if rendered is None:
            raise ValueError("no validated structured edit was produced")
        sys.stdout.write(rendered)
    except Exception as exc:
        print("nemotron-structured: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
    finally:
        print("tokens: in=%d out=%d cache_r=%d cache_w=0" %
              (totals["input"], totals["output"], totals["cache"]), file=sys.stderr)


if __name__ == "__main__":
    main()
