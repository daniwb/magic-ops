#!/usr/bin/env python3
import pathlib
import subprocess
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).with_name("map-pipeline-apply.py")


class ApplyBlocksTest(unittest.TestCase):
    def test_multiple_search_replace_pairs_under_one_file_header_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = root / "sample.txt"
            target.write_text("alpha\nbeta\ngamma\n")
            patch = """<<<FILE sample.txt
<<<SEARCH
alpha
===REPLACE
one
>>>END
<<<SEARCH
gamma
===REPLACE
three
>>>END
"""
            result = subprocess.run(
                ["python3", str(SCRIPT)], cwd=root, text=True, input=patch,
                capture_output=True, check=True)
            self.assertEqual(target.read_text(), "one\nbeta\nthree\n")
            self.assertEqual(result.stdout.count("applied: sample.txt"), 2)

    def test_split_replace_separator_preserves_exact_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = root / "sample.txt"
            target.write_text("alpha\nbeta\n")
            reply = "<<<FILE sample.txt\n<<<SEARCH\nalpha\n===\nREPLACE\none\n>>>END\n"
            result = subprocess.run(["python3", str(SCRIPT)], cwd=root, text=True,
                                    input=reply, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(target.read_text(), "one\nbeta\n")

    def test_incomplete_second_hunk_does_not_partially_apply(self):
        self.assert_rejected("<<<FILE sample.txt\n<<<SEARCH\nalpha\n===REPLACE\none\n>>>END\n"
                             "<<<SEARCH\nbeta\n===REPLACE\ntwo\n")

    def test_known_delimiter_variants_apply_identical_exact_patch(self):
        for separator in ('===', '<<<REPLACE', '===REPLACE'):
            for end in ('<<<END', '>>>END'):
                with self.subTest(separator=separator, end=end), tempfile.TemporaryDirectory() as tmp:
                    root = pathlib.Path(tmp)
                    (root/'sample.txt').write_text('alpha\nbeta\n')
                    reply = ('<<<FILE sample.txt\n<<<SEARCH\nalpha\n%s\none\n%s\n'
                             '<<<NEWFILE new.txt\nnew content\n%s\n') % (separator, end, end)
                    result = subprocess.run(['python3', str(SCRIPT)], cwd=root, text=True,
                                            input=reply, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stdout)
                    self.assertEqual((root/'sample.txt').read_text(), 'one\nbeta\n')
                    self.assertEqual((root/'new.txt').read_text(), 'new content\n')

    def test_aliases_do_not_relax_source_matching_or_duplicate_marker_rejection(self):
        for search in ('not present', 'a'):
            # 'a' is ambiguous in alpha/beta; exact matching must still reject it.
            self.assert_rejected('<<<FILE sample.txt\n<<<SEARCH\n%s\n<<<REPLACE\none\n<<<END\n' % search)
        for marker in ('<<<REPLACE', '===', '===REPLACE'):
            self.assert_rejected('<<<FILE sample.txt\n<<<SEARCH\nalpha\n<<<REPLACE\none\n%s\ntwo\n<<<END\n' % marker)

    def test_nested_and_overlong_end_markers_are_rejected(self):
        for marker in (">>>>END", "<<<SEARCH", "===\nREPLACE"):
            with self.subTest(marker=marker):
                self.assert_rejected("<<<FILE sample.txt\n<<<SEARCH\nalpha\n===REPLACE\none\n"
                                     + marker + "\n>>>END\n")

    def assert_rejected(self, reply):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = root / "sample.txt"
            target.write_text("alpha\nbeta\n")
            result = subprocess.run(["python3", str(SCRIPT)], cwd=root, text=True,
                                    input=reply, capture_output=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(target.read_text(), "alpha\nbeta\n")


if __name__ == "__main__":
    unittest.main()
