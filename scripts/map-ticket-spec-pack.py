#!/usr/bin/env python3
"""Produce a compact no-tools Map packet from a Factory NG TicketSpec."""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from factory_ng_knowledge import resolve_candidate
from factory_ng_symbols import render as render_symbol


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
parser.add_argument("--read-only-tools", action="store_true",
                    help="render the registered Codex local read-only tool contract")
args = parser.parse_args()
spec = json.loads(args.ticket_spec.read_text())
if spec.get("schema") != "factory.ticket-spec/v1" or spec.get("work_type") != "map":
    raise SystemExit("--ticket-spec must be a Map factory.ticket-spec/v1")

from factory_ng_map_context import trace_card, map_regions, upstream_regions, prepared_ticket_view
sys.path.insert(0, str(Path(args.repo) / 'scripts/paragraph'))
import reparse
card_probes = {}
trace_calls = []
for probe in spec.get('execution', {}).get('parser_probes', []):
    if probe.get('function') == 'reparse_card':
        card = reparse.load_card(probe['card'])
        if card is None:
            raise SystemExit('TicketSpec parser probe card not found: ' + probe['card'])
        result, calls = trace_card(reparse, card)
        card_probes[probe['card']] = (result, calls)
        trace_calls.extend(calls)
regions, remaining = map_regions(args.repo, trace_calls) if trace_calls else ([], 340)
upstream, _ = upstream_regions(args.repo, trace_calls)
regions.extend(upstream)
for item in spec.get("evidence", []):
    path = item.get("path", "")
    if path.startswith("scripts/"):
        part, remaining = excerpt(args.repo, path, item.get("anchor", ""), remaining)
        regions.extend(part)

# Read-only Engine context survives the dependency handoff. Resolve symbols in
# this checkout rather than trusting an old ticket's copied line numbers.
runtime_regions, runtime_budget = [], 280
for item in spec.get("evidence", []):
    candidate = item.get("symbol")
    if not candidate or runtime_budget <= 0: continue
    row = resolve_candidate(args.repo, candidate, caller='map-dependency-handoff', budget=min(140, runtime_budget))
    if row['status'] == 'resolved':
        runtime_regions.append(render_symbol(row))
        runtime_budget -= row['supplied_end'] - row['start'] + 1
regions.extend(runtime_regions)

# A bounded context repair retains the worker's unanswered questions. Resolve
# them against this clone, never paste historical source into a new attempt.
context_requests = spec.get('execution', {}).get('context_requests', [])
if context_requests:
    from factory_ng_context import requested_context
    regions.append(requested_context('\n'.join('NEED: ' + request for request in context_requests[:3]), args.repo, spec))

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
    if function == "map_atom":
        text = probe["text"]
        kind = probe["kind"]
        verb, atom_args = reparse.O.parse_atom(text)
        current = reparse.map_atom(verb, atom_args, kind=kind) if verb else None
        probe_lines.append("map_atom(%r, kind=%r) -> verb=%r args=%r current=%r" %
                           (text, kind, verb, atom_args, current))
    elif function == "parse_static_condition":
        text = probe["text"]
        probe_lines.append("parse_static_condition(%r) -> %r" %
                           (text, reparse.parse_static_condition(text)))
    elif function == "reparse_card":
        card_name = probe["card"]
        card = reparse.load_card(card_name)
        if card is None:
            raise SystemExit("TicketSpec parser probe card not found: %s" % card_name)
        probe_lines.append("Oracle text for %r -> %r" % (card_name, card.get("text", "")))
        result, calls = card_probes[card_name]
        probe_lines.append("reparse_card(load_card(%r)) -> %s" %
                           (card_name, json.dumps(result, sort_keys=True)))
        probe_lines.append('Actual parser handoffs during this card parse (map_atom arguments and failed trigger spine):\n' +
                           json.dumps(calls, indent=2, sort_keys=True))
    else:
        raise SystemExit("unsupported TicketSpec parser probe: %s" % function)

missing_allowed = [path for path in spec.get("scope", {}).get("allowed_paths", [])
                   if not (Path(args.repo) / path).exists()]

tool_contract = ("Local read-only source tools are available in this isolated checkout. "
                 "Use targeted reads/searches (about ten calls) to resolve missing or truncated evidence. "
                 "Do not edit files, run tests, use the network, commit, or integrate; the harness owns those actions. "
                 "Return only the block protocol or a bounded verdict in your final answer."
                 if args.read_only_tools else
                 "No repository tools are available. Use the supplied evidence and the bounded NEED mechanism.")
print("""# FACTORY NG MAP TASK — prepared evidence

## Source access
{tool_contract}

Ticket: {id}
Title: {title}

The TicketSpec below is authoritative. Stay within its allowed paths and emit
only the exact block protocol. Do not assume an Engine overlay unless the
TicketSpec names one; do not edit backend/ or corpus data. Engine source below
is read-only evidence for the mapping. Reuse the integrated representation;
a new NEEDS_PRIMITIVE must identify behavior it still cannot perform. Parser
eligibility alone does not verify that the complete card uses that behavior.

## TicketSpec (historical lookup logs summarized; contract fields unchanged)
{ticket}

## Exact source excerpts
{regions}

## Exact parser probes from this source revision
{probes}

## Required new paths
{missing}
Every path listed above does not exist in this clone and MUST use
`<<<NEWFILE path`, never `<<<FILE` with SEARCH/REPLACE.

## OUTPUT FORMAT
Return either a structured verdict or only edit blocks. `NEEDS_PRIMITIVE` is
legal only for one atomic missing behavior shared by the ticket scope:
VERDICT: NEEDS_PRIMITIVE|SEMANTIC_GAP|AMBIGUOUS|NOT_A_SHAPE
For NEEDS_PRIMITIVE add exactly one single-line JSON object and one reason:
CAPABILITY_JSON: {{"key":"lowercase_snake_case","summary":"short description","specification":{{"required_behavior":"one precise atomic behavior","source_misses":[{{"card":"exact card name","paragraph":"exact Oracle paragraph","required_behavior":"same precise atomic behavior"}}],"negative_examples":["adjacent behavior that must not change"],"expected_unlock":0}}}}
REASON: one line

Otherwise return only edit blocks:
<<<FILE path/relative/to/repo
<<<SEARCH
exact existing lines
===REPLACE
replacement lines
>>>END
<<<NEWFILE path/relative/to/repo
full file content
>>>END

Do not put Markdown fences, Git conflict markers, prose, or tool calls in the final answer.
Keep each SEARCH region to the smallest unique 3-12 exact lines; never copy a
whole evidence excerpt into SEARCH.
""".format(id=spec["id"], title=spec["title"], tool_contract=tool_contract,
             ticket=json.dumps(prepared_ticket_view(spec), indent=2, sort_keys=True),
             regions="\n\n".join(regions) or "(No excerpts found.)",
             probes="\n".join(probe_lines),
             missing="\n".join(missing_allowed) or "(none)"))
