#!/usr/bin/env python3
"""Read-only adapter from canonical Oracle faces to the live paragraph parser."""
import hashlib
import importlib.util
import json
import pathlib
import sys

PARSER_DIR = pathlib.Path("/opt/development/test/openmagic/scripts/paragraph")
REPARSE = PARSER_DIR / "reparse.py"


def sha256_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_parser():
    sys.path.insert(0, str(PARSER_DIR))
    spec = importlib.util.spec_from_file_location("ticketspec_live_reparse", REPARSE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def utf8_line_spans(text):
    spans, offset = [], 0
    for index, line in enumerate(text.splitlines(keepends=True), 1):
        assertion = line.rstrip("\r\n")
        size = len(assertion.encode("utf-8"))
        spans.append({"assertion_index": index, "text": assertion,
                      "span": {"start": offset, "end": offset + size}})
        offset += len(line.encode("utf-8"))
    if text and not spans:
        spans.append({"assertion_index": 1, "text": text,
                      "span": {"start": 0, "end": len(text.encode("utf-8"))}})
    return spans


def analyze(face, name):
    revision = face["canonicalSemanticRevision"]
    text = revision["text"]
    card = {"name": name, "text": text, "types": revision["types"],
            "type": revision["types"][0], "keywords": revision.get("keywords") or []}
    parser = load_parser()
    full = parser.reparse_card(card)
    assertions = []
    for item in utf8_line_spans(text):
        line_card = dict(card, text=item["text"])
        result = parser.reparse_card(line_card)
        item["parser_outcome"] = result
        assertions.append(item)
    return {
        "schema": "magic.parser-analysis/v1",
        "oracle_face_id": face["oracleFaceId"],
        "oracle_face_key": face["oracleFaceKey"],
        "name": name,
        "semantic_source": text,
        "semantic_source_hash": sha256_bytes(text.encode("utf-8")),
        "semantic_source_utf8_bytes": len(text.encode("utf-8")),
        "assertions": assertions,
        "full_parser_outcome": full,
        "before_gap_set": sorted({m[0] for m in full["misses"]}),
    }


if __name__ == "__main__":
    face = json.load(sys.stdin)
    print(json.dumps(analyze(face, sys.argv[1]), sort_keys=True, separators=(",", ":")))
