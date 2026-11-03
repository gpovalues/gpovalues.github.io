"""A single SQLite checkpoint, carried between scheduled Actions runs."""
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

from scripts.market_data import iso_time, utc_time


class TradeStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, author_id TEXT NOT NULL,
                content TEXT NOT NULL, timestamp TEXT NOT NULL, edited_at TEXT,
                has_attachments INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS messages_time ON messages(timestamp);
            CREATE INDEX IF NOT EXISTS messages_edited ON messages(edited_at);
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY, cursor TEXT, backfill_before TEXT,
                backfill_complete INTEGER NOT NULL DEFAULT 0,
                last_success_at TEXT, status TEXT NOT NULL DEFAULT 'pending', error TEXT
            );
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history (
                snapshot_id TEXT NOT NULL, as_of TEXT NOT NULL, item_id TEXT NOT NULL,
                value REAL NOT NULL, PRIMARY KEY(snapshot_id, item_id)
            );
            CREATE INDEX IF NOT EXISTS history_time ON history(as_of);
        """)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def channel(self, channel_id):
        row = self.db.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
        return dict(row) if row else {"channel_id": channel_id, "cursor": None,
            "backfill_before": None, "backfill_complete": False, "last_success_at": None,
            "status": "pending", "error": None}

    def save_page(self, channel_id, messages, **checkpoint):
        rows = []
        for message in messages:
            if not re.fullmatch(r"\d{17,22}", str(message.get("id", ""))):
                raise ValueError("Invalid Discord message ID")
            if not isinstance(message.get("content"), str):
                raise ValueError("Invalid message content")
            rows.append((str(message["id"]), channel_id, str(message["author_id"]),
                         message["content"], iso_time(message["timestamp"]),
                         iso_time(message["edited_at"]) if message.get("edited_at") else None,
                         int(bool(message.get("has_attachments")))))
        state = {**self.channel(channel_id), **checkpoint}
        with self.db:
            self.db.executemany("""
                INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET content=excluded.content,
                  edited_at=excluded.edited_at, has_attachments=excluded.has_attachments
            """, rows)
            self.db.execute("""
                INSERT INTO channels VALUES (:channel_id, :cursor, :backfill_before,
                  :backfill_complete, :last_success_at, :status, :error)
                ON CONFLICT(channel_id) DO UPDATE SET cursor=excluded.cursor,
                  backfill_before=excluded.backfill_before, backfill_complete=excluded.backfill_complete,
                  last_success_at=excluded.last_success_at, status=excluded.status, error=excluded.error
            """, state)

    def messages_since(self, since):
        stamp = iso_time(since)
        return [dict(row) for row in self.db.execute("""
            SELECT * FROM messages WHERE timestamp >= ? OR edited_at >= ?
            ORDER BY COALESCE(edited_at, timestamp), id
        """, (stamp, stamp))]

    def prune(self, now):
        cutoff = iso_time(now - dt.timedelta(days=8))
        with self.db:
            self.db.execute("DELETE FROM messages WHERE timestamp < ? AND (edited_at IS NULL OR edited_at < ?)", (cutoff, cutoff))
            self.db.execute("DELETE FROM history WHERE as_of < ?", (iso_time(now - dt.timedelta(days=30)),))

    def latest_snapshot(self):
        row = self.db.execute("SELECT value FROM state WHERE key = 'snapshot'").fetchone()
        return json.loads(row[0]) if row else None

    def save_snapshot(self, snapshot):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES ('snapshot', ?)",
                            (json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":")),))
            self.db.executemany("INSERT OR IGNORE INTO history VALUES (?, ?, ?, ?)", [
                (snapshot["revision"], snapshot["meta"]["updated_at_iso"], item["id"], item["value"])
                for item in snapshot["items"] if item["value"] is not None
            ])

    def history(self):
        result = {}
        # Four-hour samples keep the public chart small; the database retains every snapshot.
        for row in self.db.execute("SELECT item_id, as_of, value FROM history ORDER BY as_of"):
            bucket = int(utc_time(row["as_of"]).timestamp()) // 14400
            result.setdefault(row["item_id"], {})[bucket] = [row["as_of"], row["value"]]
        return {iid: list(points.values())[-43:] for iid, points in result.items()}
