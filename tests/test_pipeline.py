import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.update_values import _report_collection, main, next_catch_up_attempt, run_cycle


class PipelineTests(unittest.TestCase):
    def test_immediate_catch_up_continuations_are_bounded(self):
        source = {"mode": "scheduled", "complete": False, "pages_read": 1000,
                  "messages_read": 100000, "channels": [{"status": "catching_up"}]}
        for attempt in range(3):
            self.assertEqual(next_catch_up_attempt(source, str(attempt)), attempt + 1)
        self.assertIsNone(next_catch_up_attempt(source, "3"))

    def test_continuation_requires_progress_and_a_healthy_forward_collection(self):
        source = {"mode": "scheduled", "complete": False, "pages_read": 1000,
                  "messages_read": 100000, "channels": [{"status": "catching_up"}]}
        for change in (
            {"mode": "offline"}, {"complete": True}, {"complete": None},
            {"pages_read": 0}, {"messages_read": 0}, {"channels": []},
            {"channels": [{"status": "backfilling"}]},
            {"channels": [{"status": "catching_up"}, {"status": "error"}]},
            {"channels": [{"status": "unknown"}, {"status": "catching_up"}]},
        ):
            with self.subTest(change=change):
                self.assertIsNone(next_catch_up_attempt({**source, **change}, "0"))

    def test_invalid_continuation_input_is_rejected_before_dispatch(self):
        for attempt in ("-1", "4", "1.5", "1; command", "", None, False):
            with self.subTest(attempt=attempt):
                with self.assertRaises(ValueError):
                    next_catch_up_attempt({}, attempt)

    def test_cli_uses_the_extended_collection_budget(self):
        with patch("sys.argv", ["update_values"]), patch("scripts.update_values.run_cycle") as cycle:
            main()
        self.assertEqual(cycle.call_args.args[-1], 1000)

    def test_collection_report_explains_a_page_limit_without_claiming_a_source_error(self):
        source = {"mode": "scheduled", "complete": False, "history_complete": False,
                  "messages_read": 100000, "pages_read": 1000, "channels": [{"status": "catching_up"}]}
        output = io.StringIO()
        with redirect_stdout(output):
            _report_collection(source, 1000)
        self.assertIn("100000 messages this run; 1000/1000 pages", output.getvalue())
        self.assertIn("page limit reached", output.getvalue())
        self.assertNotIn("Discord source error", output.getvalue())

    def test_collection_report_prioritizes_source_errors_over_page_limits(self):
        source = {"mode": "scheduled", "complete": False, "history_complete": False,
                  "messages_read": 100000, "pages_read": 1000, "channels": [{"status": "error"}]}
        output = io.StringIO()
        with redirect_stdout(output):
            _report_collection(source, 1000)
        self.assertIn("Discord source error", output.getvalue())
        self.assertNotIn("page limit reached", output.getvalue())

    def test_backfill_does_not_pause_a_successful_forward_collection(self):
        source = {"mode": "scheduled", "complete": True, "history_complete": False,
                  "messages_read": 100000, "pages_read": 1000, "channels": [{"status": "backfilling"}]}
        output = io.StringIO()
        with redirect_stdout(output):
            _report_collection(source, 1000)
        self.assertIn("history_complete=False", output.getvalue())
        self.assertNotIn("repricing paused", output.getvalue())

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
