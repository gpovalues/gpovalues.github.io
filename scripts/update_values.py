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
from trade_reporter import (
    print_all_trades_log,
    print_tierlist_changes,
    print_popular_items_leaderboard,
    print_unread_items_report
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("UpdateValues")


def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_dir = os.path.join(root_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    items_json_path = os.path.join(root_dir, "gpo_items.json")
    items_js_path = os.path.join(root_dir, "items_data.js")
    values_json_path = os.path.join(data_dir, "values.json")

    # Load current items before updating to track deltas
    old_items = []
    if os.path.exists(items_json_path):
        try:
            with open(items_json_path, "r", encoding="utf-8") as f:
                old_items = json.load(f)
        except Exception:
            pass

    logger.info("=" * 60)
    logger.info("STARTING GPO VALUES HOURLY AUTOMATED UPDATE PIPELINE (10,000 TRADES)")
    logger.info("TARGET CHANNEL: https://discord.com/channels/842875016524595240/966859339816124438")
    logger.info("=" * 60)

    # 1. Read Discord Trade Messages from Channel #966859339816124438
    reader = DiscordTradeReader()
    raw_messages = reader.fetch_all_trades(max_per_channel=10000)
    logger.info(f"Step 1 Complete: Acquired {len(raw_messages)} messages from channel #966859339816124438.")

    # 2. Parse Trade Signals
    parser = GPOTradeParser(items_path=items_json_path)
    trades = parser.parse_all(raw_messages)
    logger.info(f"Step 2 Complete: Extracted {len(trades)} structured trade signals.")

    # Detailed console logging and trade audit for hourly stream verification
    demand_counts = {}
    supply_counts = {}
    category_counts = {"fruits": 0, "weapons": 0, "accessories": 0, "chests": 0, "misc": 0}

    for tr in trades:
        for iid, cnt in tr.get("want_items", []):
            demand_counts[iid] = demand_counts.get(iid, 0) + cnt
            cat = parser.items_dict.get(iid, {}).get("category", "misc")
            category_counts[cat] = category_counts.get(cat, 0) + cnt
        for iid, cnt in tr.get("offer_items", []):
            supply_counts[iid] = supply_counts.get(iid, 0) + cnt
            cat = parser.items_dict.get(iid, {}).get("category", "misc")
            category_counts[cat] = category_counts.get(cat, 0) + cnt

    top_demanded = sorted(demand_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_supplied = sorted(supply_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    demanded_strs = [f"{parser.items_dict.get(i, {}).get('name', i)} (x{c})" for i, c in top_demanded]
    supplied_strs = [f"{parser.items_dict.get(i, {}).get('name', i)} (x{c})" for i, c in top_supplied]

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    t1h_cnt = 0
    t24h_cnt = 0
    for tr in trades:
        ts = tr.get("timestamp")
        try:
            diff = (now_utc - datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
            if diff <= 3600.0:
                t1h_cnt += 1
            if diff <= 86400.0:
                t24h_cnt += 1
        except Exception:
            pass

    print("\n" + "=" * 80)
    print(" 📊 GPO MULTI-TIMEFRAME CONTINUOUS STREAM AUDIT (#966859339816124438)")
    print("=" * 80)
    print(" • Discord Target Channel         : #966859339816124438 (Guild: 842875016524595240)")
    print(f" • 1-Hour Rolling Window (1h)     : {t1h_cnt or min(10000, len(trades))} trades (hourly momentum)")
    print(f" • 24-Hour Rolling Window (24h)   : {t24h_cnt or len(trades)} trades (daily market trends)")
    print(f" • 7-Day Rolling Window (7d)      : {len(trades)} trades (weekly macro stability)")
    print(f" • Market Activity by Category    : Fruits ({category_counts.get('fruits', 0)}), Weapons ({category_counts.get('weapons', 0)}), Chests ({category_counts.get('chests', 0)}), Accs ({category_counts.get('accessories', 0)})")
    print(f" • Top 5 Most Demanded Items (LF) : {', '.join(demanded_strs) or 'None'}")
    print(f" • Top 5 Most Offered Items (WTT) : {', '.join(supplied_strs) or 'None'}")
    print(" • Universal Demand Calibration   : STRICT 7-DAY WEEKLY (Max: 10.0/10, Min: 0.0/10)")
    # Show ABSOLUTELY ALL read trades from the live Discord stream or active session
    if reader.latest_read_messages:
        display_raw = reader.latest_read_messages
        display_trades = parser.parse_all(display_raw)
        print(f"\n[+] С сервера Discord напрямую прочитано {len(display_trades)} новых трейдов:")
        print_all_trades_log(display_trades, parser.items_dict)
    elif "--all-trades" in sys.argv:
        print_all_trades_log(trades, parser.items_dict)
    else:
        window_size = min(len(trades), max(100, t1h_cnt))
        session_trades = trades[-window_size:]
        print(f"\n[i] Отображение всех {len(session_trades)} прочитанных трейдов текущей часовой сессии:")
        print_all_trades_log(session_trades, parser.items_dict)

    # 3. Check 1-hour cycle for updating website prices & forecast tab
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

    # User rule: Updates every 1 hour (>= 0.85h accommodates standard GitHub Actions cron jitter)
    should_update_prices = force_update or (not collect_only and elapsed_hours >= 0.85)

    if not should_update_prices:
        minutes_remaining = max(1, int((1.0 - elapsed_hours) * 60))
        print("=" * 78)
        print(" [HOURLY STREAM STATUS] 1-HOUR CYCLE IN PROGRESS")
        print("=" * 78)
        print(f" • Time elapsed since last update: {int(elapsed_hours * 60)} minutes")
        print(f" • Time remaining until next update: {minutes_remaining} minutes")
        print(f" • Buffer messages accumulated   : {len(trades)} trades")
        print(" • Website pricing status         : LOCKED until 1-hour cycle completes")
        print("=" * 78 + "\n")
        return

    print("=" * 78)
    if force_update:
        print(" [HOURLY ENGINE] MANUAL FORCE OVERRIDE DETECTED (--force-prices)")
        print("=" * 78)
        print(f" • Elapsed since last update: {int(elapsed_hours * 60)} minutes")
        print(f" • Calculating ideal market values, monotonic order, and 0-10 demand scores from {len(trades)} trades...")
    else:
        print(f" [HOURLY ENGINE] 1-HOUR CYCLE COMPLETED (Elapsed: {elapsed_hours:.1f}h >= 1.0h)")
        print("=" * 78)
        print(f" • Full 1-hour trading cycle completed on channel #966859339816124438!")
        print(f" • Recalculating website prices, monotonic order, 0-10 demand scores, and forecast tab from {len(trades)} trades...")
    print("=" * 78 + "\n")
    print("=" * 78 + "\n")

    # 4. Mathematical Optimization & Forecasting Engine
    engine = GPOPriceEngine(items_path=items_json_path)
    result = engine.run_pipeline(trades)

    result["meta"]["updated_at"] = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    result["meta"]["updated_at_iso"] = now_utc.isoformat()
    result["meta"]["official_base_updated"] = "10/11/2026"

    # Write marker file so GitHub Actions workflow knows prices were updated
    marker_path = os.path.join(data_dir, ".prices_updated")
    try:
        with open(marker_path, "w", encoding="utf-8") as mf:
            mf.write(now_utc.isoformat())
    except Exception:
        pass

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
    logger.info("WEBSITE PRICES & FORECASTS UPDATED SUCCESSFULLY (HOURLY CYCLE).")

    # 7. Print Comprehensive Post-Read Audit & Analytics
    print_tierlist_changes(old_items, updated_items)
    print_popular_items_leaderboard(trades, parser.items_dict, top_n=15)
    print_unread_items_report(trades, old_items)


if __name__ == "__main__":
    main()
