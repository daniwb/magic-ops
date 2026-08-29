#!/usr/bin/env python3
"""Produce a compact no-tools Map packet from a Factory NG TicketSpec."""
import argparse
import json
import os
import re
import sys
from pathlib import Path


def excerpt(repo, path, anchor, budget):
    source = Path(repo) / path
    if not source.exists() or budget <= 0:
        return [], budget
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    result = []
    for lo, hi in re.findall(r"(\d+)-(\d+)", anchor or ""):
        start, stop = max(0, int(lo) - 1), min(len(lines), int(hi))
        take = min(stop - start, budget)
        if take:
            result.append("### %s:%d-%d\n%s" % (
                path, start + 1, start + take,
                "\n".join("%5d %s" % (i + 1, lines[i]) for i in range(start, start + take))))
            budget -= take
    return result, budget


parser = argparse.ArgumentParser()
parser.add_argument("--ticket-spec", required=True, type=Path)
parser.add_argument("--repo", default="/opt/development/test/openmagic")
args = parser.parse_args()
spec = json.loads(args.ticket_spec.read_text())
if spec.get("schema") != "factory.ticket-spec/v1" or spec.get("work_type") != "map":
    raise SystemExit("--ticket-spec must be a Map factory.ticket-spec/v1")

regions, remaining = [], 340
for item in spec.get("evidence", []):
    path = item.get("path", "")
    if path.startswith("scripts/"):
        part, remaining = excerpt(args.repo, path, item.get("anchor", ""), remaining)
        regions.extend(part)

template = Path(args.repo) / "scripts/paragraph/test_target_player_draw.py"
if template.exists() and remaining:
    lines = template.read_text(encoding="utf-8").splitlines()[:100]
    regions.append("### scripts/paragraph/test_target_player_draw.py (test convention)\n%s" %
                   "\n".join("%5d %s" % (i + 1, line) for i, line in enumerate(lines)))

# A Map worker must know the exact parser output it is supposed to lower.  The
# TicketSpec supplies the bounded probes for its own parser seam; hard-coding
# a previous ticket's switch_pt examples would make a new Map worker reason
# from irrelevant evidence.  The fallback keeps the already-recorded
# switch_pt packet reproducible.
sys.path.insert(0, str(Path(args.repo) / "scripts/paragraph"))
import reparse  # noqa: E402

probes = spec.get("execution", {}).get("parser_probes") or [
    {"function": "map_atom", "text": "Switch this creature's power and toughness until end of turn.", "kind": "activated"},
    {"function": "map_atom", "text": "Switch target creature's power and toughness until end of turn.", "kind": "spell_oneshot"},
    {"function": "map_atom", "text": "Switch each creature's power and toughness until end of turn.", "kind": "activated"},
    {"function": "map_atom", "text": "Switch target player's power and toughness until end of turn.", "kind": "activated"},
]
probe_lines = []
for probe in probes:
    function = probe.get("function", "map_atom")
    text = probe["text"]
    if function == "map_atom":
        kind = probe["kind"]
        verb, atom_args = reparse.O.parse_atom(text)
        current = reparse.map_atom(verb, atom_args, kind=kind) if verb else None
        probe_lines.append("map_atom(%r, kind=%r) -> verb=%r args=%r current=%r" %
                           (text, kind, verb, atom_args, current))
    elif function == "parse_static_condition":
        probe_lines.append("parse_static_condition(%r) -> %r" %
                           (text, reparse.parse_static_condition(text)))
    else:
        raise SystemExit("unsupported TicketSpec parser probe: %s" % function)

print("""# FACTORY NG MAP TASK — prepared direct, no tools

Ticket: {id}
Title: {title}

The TicketSpec below is authoritative. Stay within its allowed paths and emit
only the exact block protocol. The accepted Engine parent already exists only
as an observation overlay; do not edit backend/ and do not change parsing.

## TicketSpec
{ticket}

## Exact source excerpts
{regions}

## Exact parser probes from this source revision
{probes}

## OUTPUT FORMAT
Return either `VERDICT: ...` with a one-line reason, or only edit blocks:
<<<FILE path/relative/to/repo
<<<SEARCH
exact existing lines
===REPLACE
replacement lines
>>>END
<<<NEWFILE path/relative/to/repo
full file content
>>>END

Do not use Markdown fences, Git conflict markers, prose, or tool calls.
""".format(id=spec["id"], title=spec["title"],
             ticket=json.dumps(spec, indent=2, sort_keys=True),
             regions="\n\n".join(regions) or "(No excerpts found.)",
             probes="\n".join(probe_lines)))
