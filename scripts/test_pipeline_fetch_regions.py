#!/usr/bin/env python3
import pathlib
import subprocess
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).with_name("pipeline-fetch-regions.py")


class FetchRegionsTest(unittest.TestCase):
    def test_named_symbol_beats_early_generic_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "backend/game/example.go"
            path.parent.mkdir(parents=True)
            lines = ["package game"] + ["// damage noise"] * 300
            lines += ["func executeDamageEffect() {"] + ["// body"] * 20 + ["}"]
            path.write_text("\n".join(lines) + "\n")
            result = subprocess.run(
                ["python3", str(SCRIPT)], cwd=root, text=True, check=True,
                input=("NEED: backend/game/example.go exact damage switch and "
                       "executeDamageEffect function\n"), capture_output=True)
            self.assertIn("func executeDamageEffect()", result.stdout)

    def test_python_def_is_treated_as_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "scripts/paragraph/reparse.py"
            path.parent.mkdir(parents=True)
            lines = ["# damage noise"] * 300
            lines += ["def map_atom(verb, args):", "    return None"]
            path.write_text("\n".join(lines) + "\n")
            result = subprocess.run(
                ["python3", str(SCRIPT)], cwd=root, text=True, check=True,
                input=("NEED: scripts/paragraph/reparse.py exact damage branch "
                       "in map_atom\n"), capture_output=True)
            self.assertIn("def map_atom(verb, args):", result.stdout)

    def test_engine_roots_prefer_engine_symbol_over_parser_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            parser = root / "scripts/paragraph/reparse.py"
            parser.parent.mkdir(parents=True)
            parser.write_text("# effectAffectsCard is mentioned in a comment\n")
            engine = root / "backend/game/effects.go"
            engine.parent.mkdir(parents=True)
            engine.write_text("package game\nfunc effectAffectsCard() bool { return true }\n")
            result = subprocess.run(
                ["python3", str(SCRIPT), "--roots", "backend/game,backend/cards"],
                cwd=root, text=True, check=True,
                input="NEED: effectAffectsCard\n", capture_output=True)
            self.assertIn("func effectAffectsCard()", result.stdout)
            self.assertNotIn("reparse.py", result.stdout)


if __name__ == "__main__":
    unittest.main()
