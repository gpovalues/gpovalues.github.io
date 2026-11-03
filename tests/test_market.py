"""Regression cases from the pricing audit. No Discord access is needed."""
import copy
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.discord_reader import DiscordTradeReader
from scripts.market_data import validate_snapshot
from scripts.price_engine import GPOPriceEngine
from scripts.trade_parser import GPOTradeParser


ROOT = Path(__file__).resolve().parents[1]


def message(content, author="one", age_hours=0, mid="123456789012345678"):
    return {
        "id": mid, "author_id": author, "channel_id": "test-channel",
        "content": content,
        "timestamp": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=age_hours)).isoformat(),
    }


class ParserRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = GPOTradeParser()

    def parse(self, text):
        return self.parser.parse_all([message(text)])

    def test_plain_text_and_suffix_quantity(self):
        trades = self.parse("LC 25 for Mochi")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["offer_items"], [("item_102", 25)])
        self.assertEqual(trades[0]["want_items"], [("item_72", 1)])

    def test_lf_for_means_want_then_offer(self):
        trades = self.parse(":LF: :mochi: :FOR: 2️⃣ :lc:")
        self.assertEqual(trades[0]["offer_items"], [("item_102", 2)])
        self.assertEqual(trades[0]["want_items"], [("item_72", 1)])

    def test_or_keeps_mutually_exclusive_quotes(self):
        trades = self.parse(":mochi: :FOR: :pika: :OR: :tori:")
        self.assertEqual(len(trades), 2)
        self.assertEqual([t["want_items"] for t in trades], [[("item_86", 1)], [("item_84", 1)]])

    def test_unknown_addition_is_not_a_complete_price_observation(self):
        trades = self.parse(":mochi: :FOR: :pika: :unknown_new_item:")
        self.assertTrue(trades)
        self.assertFalse(trades[0].get("pricing_eligible", True))

    def test_adds_cannot_be_valued_as_zero(self):
        trades = self.parse(":mochi: :FOR: :pika: :Adds:")
        self.assertFalse(trades[0].get("pricing_eligible", True))

    def test_reader_preserves_clause_boundary_after_nlf(self):
        text = ":mochi: :NLF: :pika:\n:tori: :FOR: :lc:"
        cleaned = DiscordTradeReader.clean_trade_content(text)
        trades = self.parse(cleaned)
        self.assertTrue(any(t["offer_items"] == [("item_84", 1)] and
                            t["want_items"] == [("item_102", 1)] for t in trades))

    def test_repeat_uses_latest_timestamp_without_multiplying_observations(self):
        old = message(":mochi: :FOR: :lc:", age_hours=48)
        new = message(":mochi: :FOR: :lc:", mid="123456789012345679")
        trades = self.parser.parse_all([old, new])
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["timestamp"], new["timestamp"])

    def test_bundles_are_physical_quantities(self):
        trades = self.parse("10x MC for 25 LC")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["offer_items"], [("item_58", 10)])
        self.assertEqual(trades[0]["want_items"], [("item_102", 25)])

    def test_compound_emojis_keep_the_item_variant(self):
        trades = self.parse(":blessed: :cupid: :wings: :FOR: :flowers:")
        self.assertEqual(trades[0]["offer_items"], [("item_23", 1)])
        self.assertEqual(trades[0]["want_items"], [("item_64", 1)])
        trade = self.parse(":tung: :club: :FOR: 2 :mc:")[0]
        self.assertEqual(trade["offer_items"], [("item_44", 1)])

    def test_explicit_lf_starts_another_clause_after_a_complete_offer(self):
        trades = self.parse(":mochi: :FOR: :lc: :LF: :pika:")
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["want_items"], [("item_102", 1)])
        self.assertEqual(trades[1]["want_items"], [("item_86", 1)])

    def test_oversized_numeric_text_does_not_crash_the_pipeline(self):
        trades = self.parse(':mc: :FOR: ' + '9' * 400 + ' :lc:')
        self.assertTrue(trades)
        self.assertFalse(trades[0]["pricing_eligible"])


class PriceRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gpo-test-", dir=os.environ.get("GPO_TEST_TMP"))
        self.addCleanup(self.tmp.cleanup)
        self.items = [
            {"id": "A", "name": "A", "value": 1000, "tier": "Tier A", "rankInTier": 1,
             "official_rank": 1, "rank_locked": True},
            {"id": "B", "name": "B", "value": 999, "tier": "Tier A", "rankInTier": 2,
             "official_rank": 2, "rank_locked": True},
            {"id": "F", "name": "Flexible", "value": 800, "tier": "Very Unstable",
             "rankInTier": 1, "official_rank": 4, "rank_locked": False},
            {"id": "SP", "name": "SP Reset Essence", "value": 1, "tier": "Tier F",
             "rankInTier": 1, "official_rank": 3, "rank_locked": True},
        ]
        self.path = Path(self.tmp.name) / "items.json"
        self.path.write_text(json.dumps(self.items), encoding="utf-8")

    def run_prices(self, trades):
        return GPOPriceEngine(items_path=str(self.path)).run_pipeline(trades)

    def test_no_evidence_does_not_move_valid_prices(self):
        result = self.run_prices([])
        self.assertEqual({x["id"]: x["value"] for x in result["items"]},
                         {"A": 1000, "B": 999, "F": 800, "SP": 1})

    def test_expired_evidence_is_not_relabelled_as_a_fresh_hour(self):
        trade = {**message("", age_hours=240), "offer_items": [], "want_items": [("B", 100)]}
        result = self.run_prices([trade])
        self.assertEqual(result["meta"]["total_trades_1h"], 0)
        self.assertEqual(result["meta"]["total_trades_24h"], 0)
        self.assertEqual(result["meta"]["total_trades_7d"], 0)

    def test_market_pressure_cannot_swap_locked_items(self):
        trades = [{**message("", author=str(i)), "offer_items": [("SP", 2000)],
                   "want_items": [("B", 1)], "pricing_eligible": True} for i in range(8)]
        result = self.run_prices(trades)
        locked = [x["id"] for x in result["items"] if x["id"] != "F"]
        self.assertEqual(locked, ["A", "B", "SP"])
        by_id = {x["id"]: x for x in result["items"]}
        self.assertGreater(by_id["A"]["value"], by_id["B"]["value"])

    def test_flexible_item_is_not_bound_by_its_official_position(self):
        items = copy.deepcopy(self.items)
        items[2]["value"] = 1500
        self.path.write_text(json.dumps(items), encoding="utf-8")
        result = self.run_prices([])
        self.assertEqual(result["items"][0]["id"], "F")
        self.assertEqual(result["items"][0]["value"], 1500)

    def test_one_trader_cannot_reprice_an_item(self):
        trade = {**message(""), "offer_items": [("SP", 10000)], "want_items": [("F", 1)],
                 "pricing_eligible": True}
        result = self.run_prices([trade])
        self.assertEqual(next(x["value"] for x in result["items"] if x["id"] == "F"), 800)

    def test_flexible_market_price_can_cross_a_locked_item(self):
        trades = [{**message("", author=str(i)), "offer_items": [("SP", 1800)],
                   "want_items": [("F", 1)], "pricing_eligible": True} for i in range(12)]
        result = self.run_prices(trades)
        self.assertEqual(result["items"][0]["id"], "F")

    def test_pack_and_single_price_are_coupled_even_during_initial_repair(self):
        items = [
            {"id": "pack", "name": "10x Chest", "tier": "Tier A", "official_rank": 1,
             "rankInTier": 1, "value": 150, "unit_id": "chest", "unit_quantity": 10},
            {"id": "chest", "name": "Chest", "tier": "Tier B", "official_rank": 2,
             "rankInTier": 1, "value": 12, "unit_id": "chest", "unit_quantity": 1},
            self.items[-1],
        ]
        self.path.write_text(json.dumps(items), encoding="utf-8")
        result = self.run_prices([])
        by_id = {x["id"]: x["value"] for x in result["items"]}
        self.assertAlmostEqual(by_id["pack"], 10 * by_id["chest"], places=2)

    def test_repricing_a_single_in_a_tight_retained_pack_band_is_feasible(self):
        self.path.write_text(json.dumps([
            {"id": "upper", "name": "Upper", "tier": "Tier A", "value": 2.54, "official_rank": 1},
            {"id": "LC", "name": "Legendary Fruit Chest", "tier": "Tier A", "value": 2.5, "official_rank": 2},
            {"id": "pack", "name": "10x Chest", "tier": "Tier A", "value": 2.3, "official_rank": 3,
             "unit_id": "chest", "unit_quantity": 10},
            {"id": "SP", "name": "SP Reset Essence", "tier": "Tier F", "value": 1, "official_rank": 4},
            {"id": "chest", "name": "Chest", "tier": "New Items", "value": 0.23, "official_rank": 5},
        ]), encoding="utf-8")
        engine = GPOPriceEngine(self.path)
        previous = engine.run_pipeline([])
        trades = [{**message("", author=str(i), age_hours=0.1), "offer_items": [("LC", 1)],
                   "want_items": [("SP", 2)]} for i in range(6)]
        try:
            result = engine.run_pipeline(trades, previous=previous)
        except ValueError as error:
            self.fail(f"A valid retained hierarchy must remain feasible: {error}")
        items = {item["id"]: item for item in result["items"]}
        self.assertEqual(items["upper"]["value"], 2.54)
        self.assertEqual(items["pack"]["value"], 2.3)
        self.assertEqual(items["SP"]["value"], 1)
        self.assertGreater(items["LC"]["value"], 2.3)
        self.assertLess(items["LC"]["value"], 2.54)
        self.assertTrue(items["LC"]["constraint_applied"])
        self.assertLess(items["LC"]["market_estimate"], items["LC"]["value"])
        validate_snapshot(result, engine.catalog)

    def test_repricing_a_pack_in_a_tight_retained_band_is_feasible(self):
        self.path.write_text(json.dumps([
            {"id": "upper", "name": "Upper", "tier": "Tier A", "value": 2.54, "official_rank": 1},
            {"id": "pack", "name": "10x Chest", "tier": "Tier A", "value": 2.5, "official_rank": 2,
             "unit_id": "chest", "unit_quantity": 10},
            {"id": "lower", "name": "Lower", "tier": "Tier A", "value": 2.48, "official_rank": 3},
            {"id": "SP", "name": "SP Reset Essence", "tier": "Tier F", "value": 1, "official_rank": 4},
            {"id": "chest", "name": "Chest", "tier": "New Items", "value": 0.25, "official_rank": 5},
        ]), encoding="utf-8")
        engine = GPOPriceEngine(self.path)
        previous = engine.run_pipeline([])
        trades = [{**message("", author=str(i), age_hours=0.1), "offer_items": [("SP", 1)],
                   "want_items": [("chest", 1)]} for i in range(6)]
        try:
            result = engine.run_pipeline(trades, previous=previous)
        except ValueError as error:
            self.fail(f"A valid retained pack hierarchy must remain feasible: {error}")
        items = {item["id"]: item for item in result["items"]}
        self.assertEqual(items["upper"]["value"], 2.54)
        self.assertEqual(items["lower"]["value"], 2.48)
        self.assertEqual(items["SP"]["value"], 1)
        self.assertGreater(items["pack"]["value"], 2.48)
        self.assertLess(items["pack"]["value"], 2.54)
        self.assertEqual(items["pack"]["value"], round(10 * items["chest"]["value"], 2))
        self.assertTrue(items["pack"]["constraint_applied"])
        validate_snapshot(result, engine.catalog)

    def test_unknown_counterpart_cannot_be_assigned_a_default_price(self):
        trade = {**message(""), "offer_items": [("unknown", 1)], "want_items": [("F", 1)],
                 "pricing_eligible": True}
        result = self.run_prices([trade])
        self.assertEqual(next(x["value"] for x in result["items"] if x["id"] == "F"), 800)

    def test_replaying_identical_evidence_does_not_compound_price_changes(self):
        trades = [{**message("", author=str(i)), "offer_items": [("SP", 1800)],
                   "want_items": [("F", 1)], "pricing_eligible": True} for i in range(12)]
        engine = GPOPriceEngine(items_path=str(self.path))
        first = engine.run_pipeline(trades)
        second = engine.run_pipeline(trades, previous=first)
        self.assertEqual([x["value"] for x in first["items"]], [x["value"] for x in second["items"]])
        self.assertEqual(second["changes"], [])

    def test_offer_range_comes_from_observations(self):
        trades = [{**message("", author=str(i)), "offer_items": [("SP", 1800)],
                   "want_items": [("F", 1)], "pricing_eligible": True} for i in range(12)]
        item = next(item for item in self.run_prices(trades)["items"] if item["id"] == "F")
        self.assertEqual(item.get("quote_range"), [1800, 1800])

    def test_new_ranked_price_cannot_drag_established_neighbors_to_its_asking_price(self):
        items = copy.deepcopy(self.items)
        items[1]["official_rank"] = 3
        items[-1]["official_rank"] = 4
        items.append({"id": "new", "name": "New ranked item", "value": None, "tier": "Tier A",
                      "official_rank": 2, "rankInTier": 2, "rank_locked": True})
        self.path.write_text(json.dumps(items), encoding="utf-8")
        trades = [{**message("", author=str(i)), "offer_items": [("SP", 1500)],
                   "want_items": [("new", 1)], "pricing_eligible": True} for i in range(8)]
        by_id = {item["id"]: item for item in self.run_prices(trades)["items"]}
        self.assertLessEqual(by_id["A"]["value"], 1001)
        self.assertGreater(by_id["A"]["value"], by_id["new"]["value"])
        self.assertGreater(by_id["new"]["value"], by_id["B"]["value"])

    def test_catalogue_repair_does_not_bypass_the_minimum_trader_count(self):
        items = copy.deepcopy(self.items)
        items[0]["value"] = 900
        self.path.write_text(json.dumps(items), encoding="utf-8")
        trade = {**message(""), "offer_items": [("SP", 10000)], "want_items": [("F", 1)],
                 "pricing_eligible": True}
        by_id = {item["id"]: item for item in self.run_prices([trade])["items"]}
        self.assertEqual(by_id["F"]["value"], 800)

    def test_disconnected_barter_prices_do_not_claim_a_verified_sp_scale(self):
        trades = [{**message("", author=str(i)), "offer_items": [("A", 1)],
                   "want_items": [("B", 2)], "pricing_eligible": True} for i in range(40)]
        result = self.run_prices(trades)
        item = next(item for item in result["items"] if item["id"] == "A")
        self.assertEqual(item.get("reference_basis"), "historical")
        self.assertLessEqual(item["confidence"], 0.3)

    def test_independent_sp_quotes_establish_the_point_reference(self):
        trades = [{**message("", author=str(i)), "offer_items": [("SP", 1000)],
                   "want_items": [("F", 1)], "pricing_eligible": True} for i in range(40)]
        item = next(item for item in self.run_prices(trades)["items"] if item["id"] == "F")
        self.assertEqual(item.get("reference_basis"), "sp")
        self.assertGreater(item["confidence"], 0.7)

    def test_indirect_point_reference_is_limited_by_its_weaker_link(self):
        trades = [{**message("", author=f"barter-{i}"), "offer_items": [("B", 1)],
                   "want_items": [("F", 1)], "pricing_eligible": True} for i in range(40)]
        trades += [{**message("", author=f"anchor-{i}"), "offer_items": [("SP", 999)],
                    "want_items": [("B", 1)], "pricing_eligible": True} for i in range(5)]
        item = next(item for item in self.run_prices(trades)["items"] if item["id"] == "F")
        self.assertEqual(item.get("reference_basis"), "sp")
        self.assertLessEqual(item["confidence"], 0.17)

    def test_one_new_sp_quote_cannot_reanchor_an_established_market(self):
        trades = [{**message("", author=str(i)), "offer_items": [("A", 1)],
                   "want_items": [("B", 1)], "pricing_eligible": True} for i in range(40)]
        first = self.run_prices(trades)
        poisoned = trades + [{**message("", author="single-anchor-poster"), "offer_items": [("SP", 10000)],
                              "want_items": [("A", 1)], "pricing_eligible": True}]
        second = self.run_prices(poisoned)
        self.assertEqual({i["id"]: i["value"] for i in first["items"]}, {i["id"]: i["value"] for i in second["items"]})

    def test_an_unsupported_new_offer_does_not_reapply_old_price_evidence(self):
        now = dt.datetime.now(dt.timezone.utc)
        trades = [{**message("", author=str(i)), "offer_items": [("SP", 1800)],
                   "want_items": [("F", 1)], "pricing_eligible": True} for i in range(12)]
        now += dt.timedelta(seconds=1)
        engine = GPOPriceEngine(items_path=self.path)
        first = engine.run_pipeline(trades, as_of=now)
        later = now + dt.timedelta(days=1)
        unrelated = {**message("", author="new-poster"), "timestamp": later.isoformat(),
                     "offer_items": [("A", 1)], "want_items": [("F", 1)], "pricing_eligible": True}
        second = engine.run_pipeline(trades + [unrelated], previous=first, as_of=later)
        self.assertEqual(next(i["value"] for i in second["items"] if i["id"] == "F"),
                         next(i["value"] for i in first["items"] if i["id"] == "F"))
        self.assertEqual(second["changes"], [])

    def test_an_offer_of_an_item_for_more_of_itself_is_not_a_price_equation(self):
        trades = [{**message("", author=str(i)), "offer_items": [("F", 1)],
                   "want_items": [("F", 2)], "pricing_eligible": True} for i in range(10)]
        result = self.run_prices(trades)
        self.assertEqual(next(item["value"] for item in result["items"] if item["id"] == "F"), 800)

    def test_read_trades_keep_only_the_latest_hour_without_publishing_author_data(self):
        now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)
        trades = [{**message("private message", author="private-author", age_hours=age),
                   "offer_items": [("F", 1)], "want_items": [("SP", 800)]}
                  for age in (0.75, 0.25, 2, -2)]
        result = GPOPriceEngine(self.path).run_pipeline(trades, as_of=now)
        records = result.get("read_trades", [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["timestamp"], trades[1]["timestamp"])
        self.assertEqual(records[0]["offer"], [["F", 1]])
        self.assertEqual(records[0]["want"], [["SP", 800]])
        self.assertEqual(records[0]["decision"], "waiting")
        self.assertEqual(records[0]["independent_authors"], 1)
        self.assertNotIn("private-author", json.dumps(records))
        self.assertNotIn("private message", json.dumps(records))

    def test_incomplete_read_trades_are_visible_without_counting_unknown_parts_as_market_activity(self):
        trades = [{**message("", author=str(i), age_hours=0.1), "offer_items": [("F", 1)],
                   "want_items": [("SP", 800)], "pricing_eligible": False,
                   "counts_eligible": i == 0, "issues": ["unspecified:adds" if i == 0 else "unknown:secret"]}
                  for i in range(2)]
        result = self.run_prices(trades)
        self.assertEqual([record["decision"] for record in result.get("read_trades", [])], ["incomplete", "incomplete"])
        self.assertEqual(result["meta"]["total_trades_1h"], 1)
        self.assertNotIn("secret", json.dumps(result["read_trades"]))

    def test_read_trade_decisions_distinguish_used_retained_and_paused_evidence(self):
        now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)
        trades = [{**message("", author=str(i), age_hours=0.1), "offer_items": [("F", 1)],
                   "want_items": [("SP", 800)]} for i in range(6)]
        engine = GPOPriceEngine(self.path)
        first = engine.run_pipeline(trades, as_of=now)
        self.assertEqual({record["decision"] for record in first.get("read_trades", [])}, {"used"})
        self.assertEqual({record["independent_authors"] for record in first["read_trades"]}, {6})
        second = engine.run_pipeline(trades, previous=first, as_of=now + dt.timedelta(minutes=1))
        self.assertEqual({record["decision"] for record in second["read_trades"]}, {"retained"})
        paused = engine.run_pipeline(trades, previous=first, as_of=now, allow_updates=False)
        self.assertEqual({record["decision"] for record in paused["read_trades"]}, {"paused"})

    def test_read_trades_explain_unpriced_and_non_pricing_relationships(self):
        items = copy.deepcopy(self.items)
        items[2]["value"] = None
        items.append({"id": "U", "name": "Unpriced", "tier": "New Items", "value": None, "official_rank": 5})
        self.path.write_text(json.dumps(items), encoding="utf-8")
        trades = [{**message("", author=str(i), age_hours=0.1), "offer_items": [("F", 1)],
                   "want_items": [("U", 1)]} for i in range(6)]
        trades.append({**message("", author="self", age_hours=0.1), "offer_items": [("SP", 1)], "want_items": [("SP", 2)]})
        result = self.run_prices(trades)
        self.assertEqual({record["decision"] for record in result.get("read_trades", [])}, {"unpriced", "no_relation"})

    def test_invalid_read_trades_cannot_be_published(self):
        engine = GPOPriceEngine(self.path)
        snapshot = engine.run_pipeline([])
        record = {"id": "read-offer", "timestamp": snapshot["meta"]["updated_at_iso"],
                  "offer": [["F", 1]], "want": [["SP", 800]], "decision": "waiting", "independent_authors": 1}
        stale = (dt.datetime.fromisoformat(record["timestamp"]) - dt.timedelta(hours=2)).isoformat()
        for invalid in ({"want": [["missing", 1]]}, {"offer": [["F", True]]}, {"timestamp": stale}):
            with self.subTest(invalid=invalid):
                snapshot["read_trades"] = [{**record, **invalid}]
                with self.assertRaisesRegex(ValueError, "Invalid read trade"):
                    validate_snapshot(snapshot, engine.catalog)


if __name__ == "__main__":
    unittest.main()
