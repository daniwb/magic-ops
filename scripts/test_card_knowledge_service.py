#!/usr/bin/env python3
"""Regression coverage for the compact card-knowledge index."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


OPS = Path(__file__).resolve().parents[1]
REPO = Path(os.environ.get("OPENMAGIC_REPO", "/opt/development/test/openmagic"))


def load_service():
    path = OPS / "scripts" / "card-knowledge-service.py"
    spec = importlib.util.spec_from_file_location("test_card_knowledge_service", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EngineSymbolIndexTest(unittest.TestCase):
    def test_engine_symbols_are_searchable_without_source_dump(self):
        service = load_service()
        with tempfile.TemporaryDirectory(prefix="factory-ng-kb-test-") as directory:
            service.REPO = str(REPO)
            service.DB = str(Path(directory) / "knowledge.db")
            db, counts = service.build_index()
            try:
                self.assertGreater(counts["engine"], 100)
                rows = db.execute(
                    "SELECT title FROM docs WHERE kind='engine' "
                    "AND title IN ('ExecuteAbilityEffect', 'GetPowerWithEffects', "
                    "'GetToughnessWithEffects', 'RemoveUntilEOT')"
                ).fetchall()
                self.assertEqual(
                    {row[0] for row in rows},
                    {"ExecuteAbilityEffect", "GetPowerWithEffects", "GetToughnessWithEffects", "RemoveUntilEOT"},
                )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
