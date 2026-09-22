"""Regression checks for the qualified MiniMax profile and authority limits."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "profile_validate", Path(__file__).with_name("factory-ng-profile-validate.py"))
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class MiniMaxProfileTest(unittest.TestCase):
    def setUp(self):
        self.profile = VALIDATOR.load(
            VALIDATOR.DEFAULT_DIR / "minimax-prepared-direct-1.0.0.json")

    def validate(self, profile):
        with tempfile.TemporaryDirectory(prefix="factory-ng-profile-test-") as directory:
            root = Path(directory)
            baseline = VALIDATOR.load(VALIDATOR.DEFAULT_DIR / "staged-baseline.json")
            (root / "baseline.json").write_text(json.dumps(baseline))
            (root / "minimax.json").write_text(json.dumps(profile))
            return VALIDATOR.validate(root)

    def test_qualified_profile_validates(self):
        self.assertEqual(self.validate(self.profile), 2)

    def test_only_authorized_codex_version_can_use_host_access(self):
        profile = VALIDATOR.load(VALIDATOR.DEFAULT_DIR / 'codex-constrained-v110.json')
        self.assertEqual(self.validate(profile), 2)
        for field, value in [('id', 'minimax-prepared-direct'), ('version', '1.0.0'), ('operator_authorization', '')]:
            changed = copy.deepcopy(profile)
            changed[field] = value
            with self.assertRaises(VALIDATOR.ValidationError):
                self.validate(changed)

    def test_invalid_adapter_and_authority_changes_are_rejected(self):
        for field, value in [
            ("adapter_id", "unregistered-v1"),
            ("executable", "arbitrary-command"),
            ("engine", "openrouter-agentic"),
            ("network", "OpenRouter API only"),
            ("filesystem", "read-write"),
            ("allowed_tools", ["read_file"]),
            ("reasoning", "unsupported field"),
        ]:
            with self.subTest(field=field):
                profile = copy.deepcopy(self.profile)
                profile["adapter"][field] = value
                with self.assertRaises(VALIDATOR.ValidationError):
                    self.validate(profile)
        profile = copy.deepcopy(self.profile)
        profile["authority"] = {"model_edits_workspace": True}
        with self.assertRaises(VALIDATOR.ValidationError):
            self.validate(profile)


if __name__ == "__main__":
    unittest.main()
