"""
Standalone 24/7 Trade Collection & 12-Hour Pricing Daemon for GPO Values.
Can be executed as a persistent background service (e.g., systemd, PM2, screen, Docker, or Windows Service).

Functionality:
1. Polls Discord Trade Hub channels continuously 24/7 (default: every 30-60s) via ?after={last_id}.
2. Accumulates every trade message into data/trades_buffer.json without missing any signals.
3. Every 12 hours, triggers the mathematical pricing engine (update_values.py --force-prices).
4. Optionally performs automated git commit and push to publish updated prices to GitHub Pages.
"""

import os
import sys
import time
import signal
import datetime
import argparse
import subprocess
import logging

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure local scripts directory is in path
sys.path.insert(0, os.path.dirname(__file__))

from discord_reader import DiscordTradeReader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CollectorDaemon")

RUNNING = True


def signal_handler(signum, frame):
    global RUNNING
    print("\n[DAEMON] Received shutdown signal. Gracefully exiting 24/7 daemon loop...")
    RUNNING = False


def run_git_push(repo_root: str):
    """Stages, commits, and pushes updated values to GitHub."""
    try:
        print("[DAEMON] Staging updated market values & buffer...")
        subprocess.run(["git", "add", "data/trades_buffer.json", "data/values.json", "gpo_items.json", "items_data.js"], cwd=repo_root, check=True)
        
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        commit_msg = f"📈 24/7 Stream Auto-Update: Market prices & forecasts [{now_str}]"
        
        status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_root, check=True)
            print("[DAEMON] Pushing updates to origin main...")
            subprocess.run(["git", "push", "origin", "main"], cwd=repo_root, check=True)
            print("[DAEMON] ✅ Successfully pushed 12-hour price updates to GitHub Pages!")
        else:
            print("[DAEMON] No file changes to commit.")
    except Exception as e:
        print(f"[DAEMON] ⚠️ Git push encountered an issue: {e}")


def main():
    global RUNNING
    parser = argparse.ArgumentParser(description="GPO Values 24/7 Trade Collection & 12-Hour Pricing Daemon")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between Discord poll checks (default: 30s)")
    parser.add_argument("--price-interval", type=float, default=12.0, help="Hours between website price updates (default: 12.0h)")
    parser.add_argument("--no-git-push", action="store_true", help="Disable automated git commit and push")
    parser.add_argument("--channel-id", type=str, default="966859339816124438", help="Discord Channel ID to monitor")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    update_script = os.path.join(os.path.dirname(__file__), "update_values.py")

    reader = DiscordTradeReader(channel_ids=[args.channel_id])

    print("=" * 75)
    print(" 🚀 GPO VALUES 24/7 CONTINUOUS TRADE COLLECTOR DAEMON STARTED")
    print(f" - Target Discord Channel : {args.channel_id}")
    print(f" - Stream Polling Rate    : Every {args.poll_interval}s")
    print(f" - Website Price Updates  : Every {args.price_interval}h")
    print(f" - Auto Git Push          : {'Disabled' if args.no_git_push else 'Enabled'}")
    print("=" * 75)

    last_price_update = time.time()
    iteration = 0

    while RUNNING:
        iteration += 1
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        time_str = now_dt.strftime("%H:%M:%S UTC")

        try:
            # 1. Collect trades 24/7 into rolling buffer
            trades = reader.fetch_all_trades()
            print(f"[{time_str}] [DAEMON #{iteration}] 24/7 Stream Active: {len(trades)} trades in rolling buffer.")
        except Exception as e:
            print(f"[{time_str}] [DAEMON #{iteration}] ⚠️ Error in trade poll: {e}")

        # 2. Check if 12-hour cycle has elapsed for updating website prices
        elapsed_hours = (time.time() - last_price_update) / 3600.0
        if elapsed_hours >= args.price_interval:
            print("\n" + "=" * 75)
            print(f"[{time_str}] ⏰ {args.price_interval}-HOUR CYCLE REACHED! UPDATING WEBSITE PRICES...")
            print("=" * 75)
            try:
                subprocess.run([sys.executable, update_script, "--force-prices"], cwd=repo_root, check=True)
                last_price_update = time.time()

                if not args.no_git_push:
                    run_git_push(repo_root)
            except Exception as e:
                print(f"[DAEMON] ❌ Error executing price update: {e}")

        # Sleep for poll interval in small increments to respond quickly to shutdown
        sleep_until = time.time() + args.poll_interval
        while RUNNING and time.time() < sleep_until:
            time.sleep(1)

    print("[DAEMON] Service stopped.")


if __name__ == "__main__":
    main()
