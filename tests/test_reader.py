import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.discord_reader import DiscordTradeReader
from scripts.trade_store import TradeStore


CHANNEL = "966859339816124438"


class Response:
    def __init__(self, status, payload):
        self.status_code, self.payload = status, payload
        self.headers = {}

    def json(self):
        return self.payload


class ReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gpo-reader-", dir=os.environ.get("GPO_TEST_TMP"))
        self.addCleanup(temporary.cleanup)
        self.store = TradeStore(Path(temporary.name) / "market.sqlite3")
        self.addCleanup(self.store.db.close)
        self.reader = DiscordTradeReader(token="Bot test", channel_ids=[CHANNEL])
        self.now = dt.datetime.now(dt.timezone.utc)

    def raw(self, number, bot=False):
        return {"id": str(123456789012345000 + number), "author": {"id": "player", "bot": bot},
                "content": "Mochi for LC", "timestamp": self.now.isoformat(), "attachments": []}

    def test_filtered_bot_messages_still_advance_the_raw_cursor(self):
        page = [self.raw(n, bot=n > 1) for n in range(1, 101)]
        self.store.save_page(CHANNEL, [], cursor=str(123456789012345000), backfill_complete=True)
        with patch.object(self.reader.session, "get", side_effect=[Response(200, page), Response(200, [])]):
            status = self.reader.collect(self.store, max_pages=2)
        self.assertEqual(self.store.channel(CHANNEL)["cursor"], str(123456789012345100))
        self.assertEqual(len(self.store.messages_since(self.now - dt.timedelta(hours=1))), 1)
        self.assertTrue(status["complete"])

    def test_access_failure_does_not_mark_the_source_as_successfully_read(self):
        old = (self.now - dt.timedelta(days=1)).isoformat()
        self.store.save_page(CHANNEL, [], cursor=str(123456789012345000), last_success_at=old)
        with patch.object(self.reader.session, "get", return_value=Response(403, {})):
            status = self.reader.collect(self.store, max_pages=2)
        self.assertFalse(status["complete"])
        self.assertEqual(self.store.channel(CHANNEL)["last_success_at"], old)
        self.assertEqual(self.store.channel(CHANNEL)["status"], "error")

    def test_initial_backfill_has_a_persistent_separate_checkpoint(self):
        page = [self.raw(n) for n in range(101, 201)]
        with patch.object(self.reader.session, "get", return_value=Response(200, page)):
            self.reader.collect(self.store, max_pages=1)
        state = self.store.channel(CHANNEL)
        self.assertEqual(state["cursor"], str(123456789012345200))
        self.assertEqual(state["backfill_before"], str(123456789012345101))
        self.assertFalse(state["backfill_complete"])

    def test_empty_channel_finishes_after_one_page(self):
        with patch.object(self.reader.session, "get", side_effect=[Response(200, [])]):
            status = self.reader.collect(self.store, max_pages=2)
        self.assertTrue(status["complete"])
        self.assertEqual(status["messages_read"], 0)
