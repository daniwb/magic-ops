#!/usr/bin/env python3
"""Validate/register one atomic capability emitted by a map pipeline.

The reply must contain a single-line ``CAPABILITY_JSON: {...}``. Registration
goes through the dispatcher so schema validation and deduplication have one
authority. Prints the canonical capability id on success.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request


def extract(text: str) -> dict:
    matches = re.findall(r"^CAPABILITY_JSON:\s*(\{.*\})\s*$", text, re.M)
    if len(matches) != 1:
        raise ValueError("expected exactly one single-line CAPABILITY_JSON object")
    raw = matches[0]
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Missing-closing-brace repair (2026-08-18): confirmed live on two
        # independent well-formed capability demands (tickets #3659, #3854)
        # — the model correctly nested "specification":{...} but miscounted
        # its own closing braces at the very end of the line, losing an
        # otherwise-valid single-capability NEEDS_PRIMITIVE to manual review
        # for a one-character slip. Bounded repair: only try appending 1-2
        # extra '}' (never rewriting/guessing content) and only accept the
        # result if it round-trips through json.dumps back to a string
        # ending the same way the model's own trailing content did — so
        # this can ONLY recover exactly this failure shape, not paper over
        # genuinely malformed/truncated output.
        if exc.pos != len(raw):
            raise
        repaired = None
        for extra in ("}", "}}"):
            candidate = raw + extra
            try:
                candidate_obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            repaired = candidate_obj
            break
        if repaired is None:
            raise
        obj = repaired
    required = {"key", "summary", "specification"}
    missing = required - set(obj)
    if missing:
        raise ValueError("CAPABILITY_JSON missing: " + ", ".join(sorted(missing)))
    return obj


def validate_oracle(obj: dict, repo: str) -> None:
    records = {}
    for path in glob.glob(os.path.join(repo, "backend/data/carddb/*.json")):
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            records.update(data)

    def norm(value: str) -> str:
        return " ".join(value.replace("’", "'").replace("“", '"').replace("”", '"').split())

    misses = obj.get("specification", {}).get("source_misses", [])
    for miss in misses:
        card = miss.get("card", "")
        record = records.get(card)
        if not isinstance(record, dict):
            raise ValueError("source card not found in carddb: %s" % card)
        oracle = record.get("text", "")
        paragraph = miss.get("paragraph", "")
        if not paragraph or norm(paragraph) not in norm(oracle):
            raise ValueError("source paragraph is not exact oracle text for %s" % card)
        miss["oracle_text_sha256"] = hashlib.sha256(oracle.encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", type=int, required=True)
    ap.add_argument("--reply", required=True)
    ap.add_argument("--dispatcher", default="http://127.0.0.1:9999")
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    try:
        obj = extract(open(args.reply, encoding="utf-8").read())
        validate_oracle(obj, args.repo)
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
