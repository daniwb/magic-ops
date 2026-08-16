import importlib.util
import pathlib
import unittest


PATH = pathlib.Path(__file__).parents[1] / "capability-contract.py"
SPEC = importlib.util.spec_from_file_location("capability_contract", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class CapabilityContractTest(unittest.TestCase):
    def test_extract_atomic_historical_3482_shape(self):
        reply = '''VERDICT: NEEDS_PRIMITIVE
PRIMITIVE: affects_filter_negation
CAPABILITY_JSON: {"key":"affects_filter_negation","summary":"exclude attacking objects","specification":{"required_behavior":"exclude attacking objects","source_misses":[{"card":"Arcades Sabboth","paragraph":"Other creatures you control that aren't attacking get +0/+2.","required_behavior":"exclude attacking objects"}],"negative_examples":["attacking creatures"]}}
REASON: engine filter supports only the positive form'''
        obj = MOD.extract(reply)
        self.assertEqual(obj["key"], "affects_filter_negation")
        self.assertEqual(len(obj["specification"]["source_misses"]), 1)

    def test_rejects_old_free_text_umbrella_3484(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MOD.extract("VERDICT: NEEDS_PRIMITIVE\nPRIMITIVE: grant_protection_static\nREASON: unrelated examples")

    def test_rejects_multiple_capability_objects(self):
        one = 'CAPABILITY_JSON: {"key":"a","summary":"a","specification":{}}'
        two = 'CAPABILITY_JSON: {"key":"b","summary":"b","specification":{}}'
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MOD.extract(one + "\n" + two)


if __name__ == "__main__":
    unittest.main()
