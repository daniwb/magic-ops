#!/usr/bin/env python3
"""Validate/register one atomic capability emitted by a map pipeline.

The reply must contain a single-line ``CAPABILITY_JSON: {...}``. Registration
goes through the dispatcher so schema validation and deduplication have one
authority. Prints the canonical capability id on success.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request


def extract(text: str) -> dict:
    matches = re.findall(r"^CAPABILITY_JSON:\s*(\{.*\})\s*$", text, re.M)
    if len(matches) != 1:
        raise ValueError("expected exactly one single-line CAPABILITY_JSON object")
    obj = json.loads(matches[0])
    required = {"key", "summary", "specification"}
    missing = required - set(obj)
    if missing:
        raise ValueError("CAPABILITY_JSON missing: " + ", ".join(sorted(missing)))
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", type=int, required=True)
    ap.add_argument("--reply", required=True)
    ap.add_argument("--dispatcher", default="http://127.0.0.1:9999")
    args = ap.parse_args()
    try:
        obj = extract(open(args.reply, encoding="utf-8").read())
        obj["ticket_id"] = args.ticket
        body = json.dumps(obj, separators=(",", ":")).encode()
        req = urllib.request.Request(
            args.dispatcher.rstrip("/") + "/capability-demand",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.load(resp)
        print("%s %s" % (result["id"], result["state"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print("capability contract rejected: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
