import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.price_engine import GPOPriceEngine
from scripts.update_values import run_cycle


class PriceReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gpo-references-", dir=os.environ.get("GPO_TEST_TMP"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps([
            {"id": "A", "name": "A", "tier": "Tier A", "value": 1000, "official_rank": 1},
            {"id": "LC", "name": "Legendary Fruit Chest", "tier": "Tier B", "value": 10, "official_rank": 2},
            {"id": "SP", "name": "SP Reset Essence", "tier": "Tier F", "value": 1, "official_rank": 3},
            {"id": "F", "name": "Flexible", "tier": "Very Unstable", "value": 800, "official_rank": 4},
        ]), encoding="utf-8")
        self.checked_at = dt.datetime.now(dt.timezone.utc).isoformat()

    def review(self, value=300, lc_value=100):
        (self.root / "price_references.json").write_text(json.dumps({
            "checked_at": self.checked_at, "lc_points": 10,
            "items": {"F": {"source_value": value, "source_lc_value": lc_value,
                            "source_url": "https://example.org/flexible", "source_updated_at": "2026-10-24"}},
        }), encoding="utf-8")

    def cycle(self):
        return run_cycle(catalog_path=self.catalog, state_path=self.root / "market.sqlite3",
                         output_dir=self.root, offline=True)

    def test_price_check_replaces_an_old_checkpoint_without_inventing_trades(self):
        self.cycle()
        self.review()
        snapshot = self.cycle()
        items = {item["id"]: item for item in snapshot["items"]}
        self.assertEqual(items["F"]["value"], 30)
        self.assertEqual(items["F"]["lcValue"], 3)
        self.assertEqual(items["F"]["price_status"], "reviewed")
        self.assertEqual(items["F"]["reference_basis"], "lc")
        self.assertEqual(items["F"]["price_reference"]["checked_at"], self.checked_at)
        self.assertEqual(items["F"]["observation_authors"], 0)
        self.assertEqual(snapshot["meta"]["supported_observations"], 0)
        self.assertEqual(snapshot["changes"][0]["reason"], "reviewed_reference")
        self.assertEqual({iid: items[iid]["value"] for iid in ("A", "LC", "SP")},
                         {"A": 1000, "LC": 10, "SP": 1})
        repeated = self.cycle()
        self.assertEqual(next(item["value"] for item in repeated["items"] if item["id"] == "F"), 30)
        self.assertEqual(repeated["changes"], [])

    def test_missing_quote_clears_the_unsupported_price_across_restarts(self):
        self.cycle()
        self.review(None)
        for _ in range(2):
            item = next(item for item in self.cycle()["items"] if item["id"] == "F")
            self.assertIsNone(item["value"])
            self.assertIsNone(item["lcValue"])
            self.assertEqual(item["price_status"], "unknown")

    def test_newer_market_evidence_supersedes_the_reviewed_reference(self):
        self.review()
        previous = self.cycle()
        self.assertEqual(next(item["value"] for item in previous["items"] if item["id"] == "F"), 30)
        now = dt.datetime.fromisoformat(self.checked_at) + dt.timedelta(days=1)
        trades = [{"author_id": str(i), "timestamp": now.isoformat(),
                   "offer_items": [("SP", 60)], "want_items": [("F", 1)]} for i in range(8)]
        engine = GPOPriceEngine(self.catalog)
        market = engine.run_pipeline(trades, previous=previous, as_of=now)
        priced = next(item for item in market["items"] if item["id"] == "F")
        self.assertGreater(priced["value"], 30)
        self.assertEqual(priced["price_status"], "estimated")
        reopened = engine.run_pipeline([], previous=market, as_of=now + dt.timedelta(hours=1))
        retained = next(item for item in reopened["items"] if item["id"] == "F")
        self.assertEqual(retained["value"], priced["value"])
        self.assertEqual(retained["price_status"], "carried")

    def test_invalid_reference_prices_are_rejected_before_publication(self):
        for value, lc_value in ((-2, 100), (True, 100), (float("nan"), 100), (300, 0), (300, True)):
            with self.subTest(value=value, lc_value=lc_value):
                self.review(value, lc_value)
                with self.assertRaisesRegex(ValueError, "Invalid price reference"):
                    self.cycle()


if __name__ == "__main__":
    unittest.main()
