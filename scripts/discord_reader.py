"""GET-only Discord collection with durable forward and backfill checkpoints."""
import datetime as dt
import os
import re
import time

import requests

from scripts.market_data import iso_time, utc_time


class ReadOnlyDiscordSession:
    def __init__(self, token):
        self._session = requests.Session()
        self._token = token.strip()
        self._session.headers.update({"Authorization": self._token, "User-Agent": "GPOValues/3.0"})

    def get(self, url, **kwargs):
        response = self._session.get(url, **kwargs)
        if response.status_code == 401 and not self._token.startswith("Bot "):
            self._session.headers["Authorization"] = f"Bot {self._token}"
            response = self._session.get(url, **kwargs)
        return response

    def close(self):
        self._session.close()


class DiscordTradeReader:
    DEFAULT_CHANNEL_ID = "966859339816124438"
    DISCORD_API_BASE = "https://discord.com/api/v10"

    def __init__(self, token=None, channel_ids=None):
        token = token or os.environ.get("DISCORD_TOKEN", "").strip()
        channels = channel_ids or re.split(r"[,\s]+", os.environ.get("DISCORD_CHANNEL_IDS", self.DEFAULT_CHANNEL_ID).strip())
        self.channel_ids = list(dict.fromkeys(channels))
        if not self.channel_ids or any(not self.is_valid_snowflake(cid) for cid in self.channel_ids):
            raise ValueError("DISCORD_CHANNEL_IDS must contain numeric Discord channel IDs")
        self.session = ReadOnlyDiscordSession(token) if token else None

    @staticmethod
    def is_valid_snowflake(value):
        return bool(re.fullmatch(r"\d{17,22}", str(value)))

    @staticmethod
    def clean_trade_content(content):
        text = re.sub(r"[\ufeff\u200b\u200c\u200d\u2060]", "", content or "")
        return "\n".join(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))

    def _request_batch(self, channel_id, params):
        if not self.session:
            raise ValueError("DISCORD_TOKEN is not configured")
        url = f"{self.DISCORD_API_BASE}/channels/{channel_id}/messages"
        for attempt in range(4):
            try:
                response = self.session.get(url, params={"limit": 100, **params}, timeout=20)
                if response.status_code == 200:
                    data = response.json()
                    if not isinstance(data, list) or any(not self.is_valid_snowflake(m.get("id")) for m in data):
                        raise ValueError("Invalid Discord response")
                    return sorted(data, key=lambda message: int(message["id"]))
                if response.status_code in (401, 403, 404):
                    raise ValueError(f"Discord HTTP {response.status_code}: check channel access and token")
                if response.status_code == 429:
                    delay = float(response.json().get("retry_after", 5))
                    if not 0 <= delay <= 60:
                        raise ValueError("Discord rate limit requires a later collection run")
                    time.sleep(delay + 0.25)
                elif response.status_code >= 500:
                    time.sleep(2 ** attempt)
                else:
                    raise ValueError(f"Discord HTTP {response.status_code}")
            except requests.RequestException:
                if attempt == 3:
                    raise ValueError("Discord network request failed") from None
                time.sleep(2 ** attempt)
        raise ValueError("Discord retry limit reached; checkpoint retained")

    @staticmethod
    def _records(batch, cutoff):
        records = []
        for raw in batch:
            stamp = utc_time(raw.get("timestamp"))
            author = raw.get("author", {})
            if author.get("bot") or not author.get("id"):
                continue
            edited = raw.get("edited_timestamp")
            if stamp < cutoff and (not edited or utc_time(edited) < cutoff):
                continue
            records.append({"id": str(raw["id"]), "author_id": str(author["id"]),
                            "content": raw.get("content", ""), "timestamp": iso_time(stamp),
                            "edited_at": edited, "has_attachments": bool(raw.get("attachments"))})
        return records

    def collect(self, store, max_pages=120):
        if not isinstance(max_pages, int) or not 1 <= max_pages <= 1000:
            raise ValueError("max_pages must be between 1 and 1000")
        now = dt.datetime.now(dt.timezone.utc)
        cutoff = now - dt.timedelta(days=7)
        deadline = time.monotonic() + 600
        pages = 0
        completed = set()
        read_count = 0
        for channel_index, cid in enumerate(self.channel_ids):
            state = store.channel(cid)
            new_complete = False
            refreshed = False
            channel_pages = 0
            budget = max(1, (max_pages - pages) // (len(self.channel_ids) - channel_index))
            try:
                while pages < max_pages and channel_pages < budget and time.monotonic() < deadline:
                    if not state["cursor"]:
                        mode, params = "initial", {}
                    elif not new_complete:
                        mode, params = "new", {"after": state["cursor"]}
                    elif not refreshed:
                        mode, params = "refresh", {}
                    elif not state["backfill_complete"]:
                        mode, params = "backfill", {"before": state["backfill_before"]}
                    else:
                        break
                    batch = self._request_batch(cid, params)
                    pages += 1
                    channel_pages += 1
                    read_count += len(batch)
                    if mode == "refresh":
                        # New arrivals beyond the cursor are collected by the next forward pass.
                        batch = [m for m in batch if int(m["id"]) <= int(state["cursor"])]
                        refreshed = True
                    elif mode == "initial":
                        new_complete = refreshed = True
                        if batch:
                            state["cursor"] = batch[-1]["id"]
                            state["backfill_before"] = batch[0]["id"]
                        state["backfill_complete"] = len(batch) < 100 or (batch and utc_time(batch[0]["timestamp"]) <= cutoff)
                    elif mode == "new":
                        if batch:
                            if int(batch[-1]["id"]) <= int(state["cursor"]):
                                raise ValueError("Discord pagination did not advance")
                            state["cursor"] = batch[-1]["id"]
                        new_complete = len(batch) < 100
                    else:
                        if batch:
                            if state["backfill_before"] and int(batch[0]["id"]) >= int(state["backfill_before"]):
                                raise ValueError("Discord backfill did not advance")
                            state["backfill_before"] = batch[0]["id"]
                        state["backfill_complete"] = len(batch) < 100 or (batch and utc_time(batch[0]["timestamp"]) <= cutoff)
                    state["last_success_at"] = iso_time(dt.datetime.now(dt.timezone.utc))
                    state["status"] = "ok" if new_complete and state["backfill_complete"] else "backfilling" if new_complete else "catching_up"
                    state["error"] = None
                    store.save_page(cid, self._records(batch, cutoff), **{key: value for key, value in state.items() if key != "channel_id"})
                    if mode == "initial" and not batch:
                        break
                if new_complete:
                    completed.add(cid)
            except (ValueError, KeyError, TypeError) as error:
                # Preserve the timestamp of the last successful page, not the failed attempt.
                store.save_page(cid, [], status="error", error=str(error))
        channels = [store.channel(cid) for cid in self.channel_ids]
        return {"checked_at": iso_time(now), "complete": len(completed) == len(self.channel_ids),
                "history_complete": all(bool(channel["backfill_complete"]) for channel in channels),
                "pages_read": pages, "messages_read": read_count, "channels": channels}
