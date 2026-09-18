"""Source evidence and final-call instructions for strict patch repair.

Approximate matching selects read-only evidence, never an edit destination.
The unchanged strict applier alone decides whether a correction can apply.
"""
import difflib
import re

from factory_ng_context import source_path


def repair_instructions(profile):
    tools = ('Read-only source tools remain available: inspect exact source with reads/searches '
             'before answering. Do not edit files or run compilation/tests.'
             if profile in ('codex-constrained@1.0.0', 'codex-constrained@1.1.0') else
             'Use the supplied source evidence; no tool calls.')
    return ('This is the final correction call; the earlier NEED offer is no longer available. '
            'Do not return NEED requests. If evidence remains insufficient, return '
            'VERDICT: AMBIGUOUS and REASON instead of guessing. ' + tools + '\n'
            'Return complete strict edit blocks only (or the bounded verdict). Copy SEARCH '
            'text verbatim from the source, with enough context to match exactly once. '
            'Use precisely these delimiters, each on its own line:\n'
            '<<<FILE path\n<<<SEARCH\nexact existing text\n===REPLACE\nreplacement text\n>>>END\n'
            'For a new file use <<<NEWFILE path, then full content, then >>>END. '
            'Always emit the canonical spellings shown above.\n')


def rejected_patch_context(repo, reply, line_budget=600):
    """Find bounded original-source excerpts for rejected/malformed FILE blocks."""
    sections, seen = [], set()
    headers = list(re.finditer(r'^<<<(?:FILE|NEWFILE) ([^\n]+)\n', reply, re.M))
    for index, header in enumerate(headers[:24]):
        if line_budget <= 0:
            break
        relative = header[1].strip()
        path = source_path(repo, relative)
        if path is None:
            continue
        lines = path.read_text().splitlines()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(reply)
        section = reply[header.end():end]
        searches = re.findall(r'^<<<SEARCH\n(.*?)(?=^===|^<<<REPLACE|\Z)', section, re.M | re.S)
        ranges = []
        for search in searches[:8]:
            wanted = search.rstrip('\n').splitlines()
            if not wanted:
                continue
            exact = [i for i in range(len(lines)) if lines[i:i + len(wanted)] == wanted]
            if exact:
                ranges.extend((max(0, i - 12), min(len(lines), i + len(wanted) + 12)) for i in exact[:3])
            else:
                # Whitespace-normalized anchors are hints for source reads only.
                match = difflib.SequenceMatcher(None, [s.strip() for s in wanted],
                                                 [s.strip() for s in lines], autojunk=False).find_longest_match()
                if match.size:
                    ranges.append((max(0, match.b - 16), min(len(lines), match.b + match.size + 32)))
        if not ranges and len(lines) <= 180:
            ranges = [(0, len(lines))]
        for lo, hi in ranges:
            hi = min(hi, lo + 180, lo + line_budget)
            key = (relative, lo, hi)
            if key in seen or hi <= lo:
                continue
            seen.add(key)
            sections.append('### %s:%d-%d (exact source; nearby evidence, not an automatic match)\n```\n%s\n```'
                            % (relative, lo + 1, hi, '\n'.join(lines[lo:hi])))
            line_budget -= hi - lo
    return '\n\n'.join(sections)


def protocol_repair_prompt(packet, repo, reply, diagnostic, profile):
    return (packet + '\n\n## ONE BOUNDED REPAIR\nYour previous answer was:\n' + reply +
            '\n\nThe strict patch harness rejected it with:\n' + diagnostic[-8000:] +
            '\n\nExact current source for correction (takes precedence over the original packet):\n' +
            rejected_patch_context(repo, reply) + '\n\n' + repair_instructions(profile))
