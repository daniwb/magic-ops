#!/usr/bin/env python3
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name('qwen-prepared-normalize.py')


def run(payload, *allowed):
    command = [sys.executable, str(SCRIPT)]
    for path in allowed:
        command.extend(['--allow', path])
    return subprocess.run(command, input=payload, text=True, capture_output=True)


class QwenPreparedNormalizeTests(unittest.TestCase):
    def test_converts_explicit_file_hunk(self):
        result = run('FILE: scripts/example.py\nSEARCH:\nold\nREPLACE:\nnew\n',
                     'scripts/example.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         '<<<FILE scripts/example.py\n<<<SEARCH\nold\n===REPLACE\nnew\n>>>END\n')

    def test_accepts_a_single_wrapper_fence_only(self):
        result = run('```text\nFILE: scripts/example.py\nSEARCH:\nold\nREPLACE:\nnew\n```',
                     'scripts/example.py')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_passes_canonical_output_through(self):
        payload = '<<<FILE scripts/example.py\n<<<SEARCH\nold\n===REPLACE\nnew\n>>>END\n'
        result = run(payload, 'scripts/example.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, payload)

    def test_passes_a_clean_verdict_through(self):
        result = run('VERDICT: NEEDS_PRIMITIVE\nREASON: no matching capability',
                     'scripts/example.py')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_missing_path_like_the_failed_repair(self):
        result = run('SEARCH:\nold\nREPLACE:\nnew\n', 'scripts/example.py')
        self.assertEqual(result.returncode, 2)

    def test_rejects_prose_and_unapproved_paths(self):
        prose = run('Here is the fix:\nFILE: scripts/example.py\nSEARCH:\nold\nREPLACE:\nnew\n',
                    'scripts/example.py')
        wrong_path = run('FILE: scripts/other.py\nSEARCH:\nold\nREPLACE:\nnew\n',
                         'scripts/example.py')
        self.assertEqual(prose.returncode, 2)
        self.assertEqual(wrong_path.returncode, 2)


if __name__ == '__main__':
    unittest.main()
