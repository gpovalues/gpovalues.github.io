import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

from scripts.trade_store import TradeStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gpo-store-", dir=os.environ.get("GPO_TEST_TMP"))
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "market.sqlite3"
        self.now = dt.datetime.now(dt.timezone.utc)

    def message(self, content="Mochi for LC"):
        return {"id": "123456789012345678", "author_id": "trader", "content": content,
                "timestamp": self.now.isoformat(), "channel_id": "channel"}

    def test_reopened_store_resumes_cursor_without_duplicate_messages(self):
        with TradeStore(self.path) as store:
            store.save_page("channel", [self.message()], cursor="123456789012345678")
        with TradeStore(self.path) as store:
            store.save_page("channel", [self.message()], cursor="123456789012345678")
            self.assertEqual(len(store.messages_since(self.now - dt.timedelta(hours=1))), 1)
            self.assertEqual(store.channel("channel")["cursor"], "123456789012345678")

    def test_edit_replaces_content_but_preserves_original_date(self):
        with TradeStore(self.path) as store:
            store.save_page("channel", [self.message()])
            changed = {**self.message("Mochi for 2 LC"), "edited_at": (self.now + dt.timedelta(minutes=1)).isoformat()}
            store.save_page("channel", [changed])
            messages = store.messages_since(self.now - dt.timedelta(hours=1))
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["content"], "Mochi for 2 LC")
            self.assertEqual(dt.datetime.fromisoformat(messages[0]["timestamp"]), self.now)

    def test_corrupt_page_does_not_advance_the_checkpoint(self):
        with TradeStore(self.path) as store:
            store.save_page("channel", [self.message()], cursor="123456789012345678")
            with self.assertRaises((ValueError, KeyError)):
                store.save_page("channel", [{**self.message(), "timestamp": "not-a-date"}], cursor="123456789012345679")
            self.assertEqual(store.channel("channel")["cursor"], "123456789012345678")

    def test_history_is_written_once_for_a_snapshot(self):
        snapshot = {"revision": "run-1", "meta": {"updated_at_iso": self.now.isoformat()},
                    "items": [{"id": "item_72", "value": 100}]}
        with TradeStore(self.path) as store:
            store.save_snapshot(snapshot)
            store.save_snapshot(snapshot)
            self.assertEqual(store.latest_snapshot()["revision"], "run-1")
            self.assertEqual(len(store.history()["item_72"]), 1)
