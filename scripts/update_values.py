"""
Main Orchestration Script for GPO Values Automatic Updates.
Coordinates:
1. Discord trade reading (read-only HTTP GET or simulation fallback).
2. Trade message parsing and normalization.
3. Mathematical pricing engine (strict isotonic tier monotonicity + smoothing + forecasting).
4. Exporting data/values.json, gpo_items.json, and items_data.js.
"""

import os
import sys
import json
import datetime
import logging

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure local scripts folder is in import path
sys.path.insert(0, os.path.dirname(__file__))

from discord_reader import DiscordTradeReader
from trade_parser import GPOTradeParser
from price_engine import GPOPriceEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("UpdateValues")


def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_dir = os.path.join(root_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    items_json_path = os.path.join(root_dir, "gpo_items.json")
    items_js_path = os.path.join(root_dir, "items_data.js")
    values_json_path = os.path.join(data_dir, "values.json")

    logger.info("=" * 60)
    logger.info("STARTING GPO VALUES 12-HOUR AUTOMATED UPDATE PIPELINE")
    logger.info("=" * 60)

    # 1. Read Discord Trade Messages
    reader = DiscordTradeReader()
    raw_messages = reader.fetch_all_trades(max_per_channel=1000)
    logger.info(f"Step 1 Complete: Acquired {len(raw_messages)} messages.")

    # 2. Parse Trade Signals
    parser = GPOTradeParser(items_path=items_json_path)
    trades = parser.parse_all(raw_messages)
    logger.info(f"Step 2 Complete: Extracted {len(trades)} structured trade signals.")

    # Detailed console logging for GitHub Actions
    print("\n" + "=" * 75)
    print(" [PARSER LOG] LIVE TRADE PARSER SAMPLES (10 EXAMPLES: [RAW] -> [PARSED])")
    print("=" * 75)
    for idx, tr in enumerate(trades[:10], start=1):
        raw = tr.get("raw_text", "").replace("\n", " ").strip()
        offer_desc = [f"{parser.items_dict.get(iid, {}).get('name', iid)} (x{cnt})" for iid, cnt in tr.get("offer_items", [])]
        want_desc = [f"{parser.items_dict.get(iid, {}).get('name', iid)} (x{cnt})" for iid, cnt in tr.get("want_items", [])]
        parsed_str = f"OFFER: [{', '.join(offer_desc) or 'None'}]  |  WANT: [{', '.join(want_desc) or 'None'}]"
        print(f"[{idx:02d}] [RAW]    : {raw}")
        print(f"     [PARSED] : {parsed_str}")
    print("=" * 75 + "\n")

    # 3. Mathematical Optimization & Forecasting Engine
    engine = GPOPriceEngine(items_path=items_json_path)
    result = engine.run_pipeline(trades)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    result["meta"]["updated_at"] = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    result["meta"]["updated_at_iso"] = now_utc.isoformat()
    result["meta"]["official_base_updated"] = "10/11/2026"

    # 4. Save data/values.json
    with open(values_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved live analytics to {values_json_path} ({len(result['items'])} items).")

    # 5. Synchronize gpo_items.json and items_data.js
    updated_items = result["items"]
    with open(items_json_path, "w", encoding="utf-8") as f:
        json.dump(updated_items, f, indent=2, ensure_ascii=False)

    with open(items_js_path, "w", encoding="utf-8") as f:
        f.write("// Official Grand Piece Online Trading Database (Live Synchronized)\n")
        f.write("window.GPO_ITEMS = " + json.dumps(updated_items, indent=2, ensure_ascii=False) + ";\n")
    logger.info(f"Synchronized {items_json_path} and {items_js_path}.")

    # Summary Report
    summary = result.get("forecast_summary", {})
    rising = summary.get("top_rising", [])
    falling = summary.get("top_falling", [])
    alerts = summary.get("tier_pressure_candidates", [])

    logger.info("-" * 60)
    logger.info(f"UPDATE SUMMARY | Market Sentiment: {result['meta']['market_sentiment']}")
    logger.info(f"Top Rising Items ({len(rising)}): {', '.join(it['name'] for it in rising[:4])}")
    logger.info(f"Top Falling Items ({len(falling)}): {', '.join(it['name'] for it in falling[:4])}")
    logger.info(f"Tier Pressure Alerts ({len(alerts)}): {', '.join(it['name'] for it in alerts[:3]) if alerts else 'None'}")
    logger.info("-" * 60)
    logger.info("PIPELINE COMPLETED SUCCESSFULLY.")


if __name__ == "__main__":
    main()
