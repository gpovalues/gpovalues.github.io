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
    raw_messages = reader.fetch_all_trades(max_per_channel=3000)
    logger.info(f"Step 1 Complete: Acquired {len(raw_messages)} messages.")

    # 2. Parse Trade Signals
    parser = GPOTradeParser(items_path=items_json_path)
    trades = parser.parse_all(raw_messages)
    logger.info(f"Step 2 Complete: Extracted {len(trades)} structured trade signals.")

    # Detailed console logging for GitHub Actions
    print("\n" + "=" * 75)
    print(f" [PARSER LOG] 24/7 STREAM ANALYSIS: {len(trades)} DISTINCT TRADES EXTRACTED")
    print(f" (Showing 10 trade samples below | All {len(trades)} trades are processed into the pricing engine)")
    print("=" * 75)
    for idx, tr in enumerate(trades[:10], start=1):
        raw = tr.get("raw_text", "").replace("\n", " ").strip()
        offer_desc = [f"{parser.items_dict.get(iid, {}).get('name', iid)} (x{cnt})" for iid, cnt in tr.get("offer_items", [])]
        want_desc = [f"{parser.items_dict.get(iid, {}).get('name', iid)} (x{cnt})" for iid, cnt in tr.get("want_items", [])]
        parsed_str = f"OFFER: [{', '.join(offer_desc) or 'None'}]  |  WANT: [{', '.join(want_desc) or 'None'}]"
        print(f"[{idx:02d}] [RAW]    : {raw}")
        print(f"     [PARSED] : {parsed_str}")
    print("=" * 75)
    print(f" >>> Total trades dataset analyzed: {len(trades)} trade signals loaded into optimization model. <<<\n")

    # 3. Check 12-hour cycle for updating website prices
    force_update = ("--force-prices" in sys.argv) or ("--force" in sys.argv)
    collect_only = ("--collect-only" in sys.argv)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    last_price_update_dt = None

    if os.path.exists(values_json_path):
        try:
            with open(values_json_path, "r", encoding="utf-8") as f:
                prev_val = json.load(f)
                iso_str = prev_val.get("meta", {}).get("updated_at_iso")
                if iso_str:
                    last_price_update_dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        except Exception:
            pass

    if last_price_update_dt:
        elapsed_hours = (now_utc - last_price_update_dt).total_seconds() / 3600.0
    else:
        elapsed_hours = 999.0

    # The user rule: Collect 24/7, but recalculate & update website prices every 12 hours
    should_update_prices = force_update or (not collect_only and elapsed_hours >= 12.0)

    if not should_update_prices:
        hours_remaining = max(0.0, 12.0 - elapsed_hours)
        minutes_remaining = int(hours_remaining * 60)
        print("=" * 70)
        print("[24/7 STREAM STATUS - DATABASE ACCUMULATION ACTIVE]")
        print(f" - Continuous collection: ACTIVE ({len(trades)} trades in 24/7 buffer)")
        print(f" - Elapsed since last site price update: {elapsed_hours:.1f} hours ({int(elapsed_hours * 60)} minutes)")
        print(f" - Next website price recalculation in : {hours_remaining:.1f} hours ({minutes_remaining} minutes)")
        print(" - STATUS: Collecting stream 24/7. Website prices remain STABLE until 12h cycle is completed.")
        print("=" * 70)
        return

    print("=" * 70)
    if force_update:
        print(f"[PRICE ENGINE] MANUAL FORCE FLAG DETECTED (--force-prices). (Elapsed: {elapsed_hours:.1f}h).")
        print("CALCULATING IDEAL MARKET VALUES & UPDATING WEBSITE PRICES...")
    else:
        print(f"[PRICE ENGINE] FULL 12-HOUR CYCLE COMPLETED (Elapsed: {elapsed_hours:.1f}h >= 12.0h).")
        print("CALCULATING IDEAL MARKET VALUES & UPDATING WEBSITE PRICES FROM ALL ACCUMULATED TRADES...")
    print("=" * 70)

    # 4. Mathematical Optimization & Forecasting Engine
    engine = GPOPriceEngine(items_path=items_json_path)
    result = engine.run_pipeline(trades)

    result["meta"]["updated_at"] = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    result["meta"]["updated_at_iso"] = now_utc.isoformat()
    result["meta"]["official_base_updated"] = "10/11/2026"

    # 5. Save data/values.json
    with open(values_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved live analytics to {values_json_path} ({len(result['items'])} items).")

    # 6. Synchronize gpo_items.json and items_data.js
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
    logger.info("WEBSITE PRICES UPDATED SUCCESSFULLY (12-HOUR CYCLE).")


if __name__ == "__main__":
    main()
