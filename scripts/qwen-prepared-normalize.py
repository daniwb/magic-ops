#!/usr/bin/env python3
"""Normalize one deliberately narrow Qwen repair grammar to Factory blocks.

The normal Factory applier intentionally accepts only canonical <<<FILE blocks.
This adapter-side recovery is for a Qwen repair that says exactly ``FILE:",
``SEARCH:", and ``REPLACE:" while still naming an allowed file. It rejects
prose, inferred paths, diffs, and any other Markdown so raw model evidence is
never silently interpreted as a patch.
"""
import argparse
import re
import sys


def strip_single_fence(text):
    """Permit a fence only when it wraps the complete alternate payload."""
    match = re.fullmatch(r'```[^\n]*\n(.*)\n```\s*', text, re.S)
    return match.group(1) if match else text


def normalize(text, allowed):
    text = strip_single_fence(text).strip()
    if not text:
        raise ValueError('empty output')
    if re.fullmatch(r'VERDICT:\s*[A-Z_]+(?:\n(?:REASON:.*|CAPABILITY_JSON:\s*\{.*\}))*', text):
        return text + '\n'
    # Keep a valid primary response untouched so this utility can sit directly
    # between the Qwen call and the ordinary applier. The applier remains the
    # authoritative grammar validator; this only verifies that every named
    # file is part of the Ticket's explicit allow-list.
    canonical_paths = re.findall(r'^<<<(?:FILE|NEWFILE) ([^\n]+)\n', text, re.M)
    if text.startswith('<<<'):
        if not canonical_paths:
            raise ValueError('canonical-looking output has no explicit file header')
        for path in canonical_paths:
            if path.strip() not in allowed:
                raise ValueError('path is not explicitly allowed: %s' % path.strip())
        return text + '\n'
    pattern = re.compile(
        r'FILE:\s*([^\n]+)\nSEARCH:\n(.*?)\nREPLACE:\n(.*?)(?=\nFILE:\s*[^\n]+\nSEARCH:\n|\Z)',
        re.S,
    )
    blocks = []
    pos = 0
    for match in pattern.finditer(text):
        if match.start() != pos:
            raise ValueError('unexpected prose or unsupported Markdown')
        path = match.group(1).strip()
        if path not in allowed:
            raise ValueError('path is not explicitly allowed: %s' % path)
        if path.startswith('/') or '..' in path or not re.fullmatch(r'[A-Za-z0-9_./-]+', path):
            raise ValueError('invalid path: %s' % path)
        search, replace = match.group(2), match.group(3)
        if not search:
            raise ValueError('%s: empty SEARCH' % path)
        blocks.append((path, search, replace))
        pos = match.end()
    if not blocks or pos != len(text):
        raise ValueError('not an explicit FILE/SEARCH/REPLACE payload')
    return ''.join(
        '<<<FILE %s\n<<<SEARCH\n%s\n===REPLACE\n%s\n>>>END\n' % block
        for block in blocks
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--allow', action='append', required=True,
                    help='explicit relative path permitted for a recovered hunk; repeatable')
    args = ap.parse_args()
    try:
        sys.stdout.write(normalize(sys.stdin.read(), set(args.allow)))
    except ValueError as exc:
        print('qwen-prepared-normalize: rejected: %s' % exc, file=sys.stderr)
        raise SystemExit(2)


if __name__ == '__main__':
    main()
