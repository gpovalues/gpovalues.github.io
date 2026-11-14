"""Collect, estimate, validate, and publish one consistent market snapshot."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from scripts.discord_reader import DiscordTradeReader
from scripts.market_data import ROOT, atomic_json, validate_snapshot
from scripts.price_engine import GPOPriceEngine
from scripts.trade_parser import GPOTradeParser
from scripts.trade_store import TradeStore


def _report_collection(source, max_pages):
    if source["mode"] == "offline":
        return
    statuses = ", ".join(sorted({channel["status"] for channel in source["channels"]})) or "pending"
    print(f"Discord collection: {source['messages_read']} messages this run; "
          f"{source['pages_read']}/{max_pages} pages; history_complete={source['history_complete']}; "
          f"status={statuses}")
    if source["complete"]:
        return
    if any(channel["status"] == "error" for channel in source["channels"]):
        print("Market repricing paused: Discord source error. Checkpoint retained; check access and retry.")
    elif source["pages_read"] >= max_pages:
        print("Market repricing paused: page limit reached before forward collection caught up. "
              "Checkpoint retained; remaining messages resume next run.")
    else:
        print("Market repricing paused: forward collection is incomplete. "
              "Checkpoint retained; remaining messages resume next run.")


def run_cycle(catalog_path=None, state_path=None, output_dir=None, offline=False,
              max_pages=DiscordTradeReader.DEFAULT_MAX_PAGES):
    catalog_path = Path(catalog_path or ROOT / "data/catalog.json")
    state_path = Path(state_path or ROOT / ".state/market.sqlite3")
    output_dir = Path(output_dir or ROOT / "data")
    engine = GPOPriceEngine(items_path=catalog_path)
    with TradeStore(state_path) as store:
        # The raw-message checkpoint must be restorable even if the price fit fails.
        atomic_json(state_path.parent / "catalog.json", engine.catalog)
        previous = store.latest_snapshot()
        published = output_dir / "values.json"
        if previous is None and published.exists():
            saved = json.loads(published.read_text(encoding="utf-8"))
            if saved.get("schema_version") == 2:
                previous = saved
        if offline:
            source = {"mode": "offline", "complete": False, "history_complete": False,
                      "messages_read": 0, "pages_read": 0, "channels": []}
        else:
            reader = DiscordTradeReader()
            try:
                source = {"mode": "scheduled", **reader.collect(store, max_pages=max_pages)}
            finally:
                if reader.session:
                    reader.session.close()
        _report_collection(source, max_pages)
        now = dt.datetime.now(dt.timezone.utc)
        store.prune(now)
        messages = store.messages_since(now - dt.timedelta(days=7))
        parser = GPOTradeParser(items_path=catalog_path)
        trades = parser.parse_all(messages)
        snapshot = engine.run_pipeline(trades, previous=previous, as_of=now,
                                       allow_updates=offline or source["complete"])
        snapshot["discord_source"] = source
        snapshot["parser_stats"] = parser.stats
        snapshot["meta"]["messages_in_window"] = len(messages)
        snapshot.pop("revision", None)
        snapshot["revision"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()).hexdigest()[:20]
        validate_snapshot(snapshot, engine.catalog)
        store.save_snapshot(snapshot)
        atomic_json(output_dir / "history.json", {"revision": snapshot["revision"], "items": store.history()})
        atomic_json(published, snapshot)
    print(f"Snapshot {snapshot['revision']}: {len(snapshot['items'])} items; "
          f"{len(messages)} messages; {len(trades)} unique offers; "
          f"{len(snapshot['changes'])} actual price changes. Source: {source['mode']}, complete={source['complete']}")
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use retained observations without contacting Discord")
    parser.add_argument("--max-pages", type=int, default=DiscordTradeReader.DEFAULT_MAX_PAGES,
                        help="Maximum Discord pages per run (default: 1000); remaining history resumes next time")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--state", type=Path, default=ROOT / ".state/market.sqlite3")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    run_cycle(args.catalog, args.state, args.output_dir, args.offline, args.max_pages)


if __name__ == "__main__":
    main()
