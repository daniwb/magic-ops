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


if __name__ == "__main__":
    unittest.main()
