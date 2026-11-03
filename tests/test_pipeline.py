import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.update_values import run_cycle


class PipelineTests(unittest.TestCase):
    def test_failed_price_fit_keeps_a_restorable_collector_checkpoint(self):
        with tempfile.TemporaryDirectory(prefix="gpo-pipeline-", dir=os.environ.get("GPO_TEST_TMP")) as folder:
            root = Path(folder)
            state = root / "checkpoint" / "market.sqlite3"
            with patch("scripts.update_values.GPOPriceEngine.run_pipeline", side_effect=ValueError("Fit failed")):
                with self.assertRaisesRegex(ValueError, "Fit failed"):
                    run_cycle(state_path=state, output_dir=root / "public", offline=True)
            self.assertTrue(state.is_file())
            self.assertTrue((state.parent / "catalog.json").is_file())
            self.assertFalse((root / "public" / "values.json").exists())

    def test_offline_snapshot_can_be_reopened_without_inventing_activity(self):
        with tempfile.TemporaryDirectory(prefix="gpo-pipeline-", dir=os.environ.get("GPO_TEST_TMP")) as folder:
            root = Path(folder)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps([
                {"id": "A", "name": "A", "tier": "Tier A", "value": 100, "official_rank": 1},
                {"id": "LC", "name": "Legendary Fruit Chest", "tier": "Tier B", "value": 10, "official_rank": 2},
                {"id": "SP", "name": "SP Reset Essence", "tier": "Tier F", "value": 1, "official_rank": 3},
            ]), encoding="utf-8")
            kwargs = dict(catalog_path=catalog, state_path=root / "state.sqlite3", output_dir=root, offline=True)
            run_cycle(**kwargs)
            first = json.loads((root / "values.json").read_text(encoding="utf-8"))
            run_cycle(**kwargs)
            second = json.loads((root / "values.json").read_text(encoding="utf-8"))
            self.assertEqual([i["value"] for i in first["items"]], [i["value"] for i in second["items"]])
            self.assertEqual(second["meta"]["total_trades_1h"], 0)
            self.assertEqual(second["changes"], [])
            self.assertFalse(second["discord_source"]["complete"])
            self.assertTrue((root / "history.json").exists())
