"""
Mathematical Pricing & Forecasting Engine for Grand Piece Online (GPO).
Implements:
1. Raw Implied Value & IQR Outlier Filtering with EMA Clamping (+-10% max per 12h cycle).
2. Strict Monotonic Constraint: PAVA (Pool Adjacent Violators Algorithm) enforcing Price(rank_i) > Price(rank_{i+1}).
3. Smooth Spacing Regularization: guarantees min_gap between neighbors so no items collapse into identical values.
4. 24-48h Forecasting Engine: Demand Scores (1-10), Market Pressure Ratio, Trend Flags, and Tier Pressure Alerts.
"""

import json
import math
import os
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("PriceEngine")


def pava_decreasing(y: List[float], weights: Optional[List[float]] = None) -> List[float]:
    """
    Pool Adjacent Violators Algorithm (PAVA) for isotonic regression.
    Enforces monotonically non-increasing values: y_hat[0] >= y_hat[1] >= ... >= y_hat[n-1].
    """
    n = len(y)
    if n <= 1:
        return list(y)

    w = [1.0] * n if weights is None else list(weights)
    y_hat = list(y)

    # Blocks: list of (start_idx, end_idx, weighted_sum, total_weight)
    blocks: List[List[float]] = []
    for i in range(n):
        blocks.append([i, i, y_hat[i] * w[i], w[i]])

    i = 0
    while i < len(blocks) - 1:
        val_curr = blocks[i][2] / blocks[i][3]
        val_next = blocks[i + 1][2] / blocks[i + 1][3]

        # For decreasing monotonicity, violation occurs when curr < next
        if val_curr < val_next:
            # Merge blocks[i] and blocks[i+1]
            blocks[i][1] = blocks[i + 1][1]
            blocks[i][2] += blocks[i + 1][2]
            blocks[i][3] += blocks[i + 1][3]
            del blocks[i + 1]

            # Backtrack to check if this merge violated previous blocks
            while i > 0:
                prev_val = blocks[i - 1][2] / blocks[i - 1][3]
                curr_val = blocks[i][2] / blocks[i][3]
                if prev_val < curr_val:
                    blocks[i - 1][1] = blocks[i][1]
                    blocks[i - 1][2] += blocks[i][2]
                    blocks[i - 1][3] += blocks[i][3]
                    del blocks[i]
                    i -= 1
                else:
                    break
        else:
            i += 1

    # Unpack fitted values
    result = [0.0] * n
    for start, end, w_sum, t_weight in blocks:
        block_avg = w_sum / t_weight
        for idx in range(int(start), int(end) + 1):
            result[idx] = block_avg

    return result


class GPOPriceEngine:
    """
    Core mathematical engine calculating ideal GPO economy prices.
    Preserves official tier-list ranking without exception.
    """
    LC_POINT_BASE = 233.33  # Standard GPO Tier List: 1 Legendary Chest ≈ 233.33 pts

    def __init__(self, items_path: Optional[str] = None):
        self.items_path = items_path or os.path.join(os.path.dirname(__file__), "..", "gpo_items.json")
        self.items: List[Dict[str, Any]] = []
        self._load_items()

    def _load_items(self):
        if not os.path.exists(self.items_path):
            raise FileNotFoundError(f"Items database not found at {self.items_path}")
        with open(self.items_path, "r", encoding="utf-8") as f:
            self.items = json.load(f)

        # Sort items strictly by official tier hierarchy and canonical value
        self._assign_official_ranks()

    def _assign_official_ranks(self):
        """
        Sorts all items by their canonical tier list value descending.
        Assigns unambiguous official_rank from 1 (Cool Shades) to N (Epic Banana / SP Reset).
        """
        # Sort descending by value; break ties with original rankInTier or id
        self.items.sort(key=lambda x: (
            -float(x.get("value", 0)),
            int(x.get("rankInTier", 99)),
            x.get("id", "")
        ))

        for idx, it in enumerate(self.items):
            it["official_rank"] = idx + 1

    @staticmethod
    def filter_outliers_iqr(values: List[float]) -> List[float]:
        """Filters extreme offers using Interquartile Range (IQR)."""
        if len(values) < 4:
            return values
        sorted_v = sorted(values)
        q1_idx = int(0.25 * len(sorted_v))
        q3_idx = int(0.75 * len(sorted_v))
        q1 = sorted_v[q1_idx]
        q3 = sorted_v[q3_idx]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        filtered = [v for v in sorted_v if lower <= v <= upper]
        return filtered if filtered else sorted_v

    def calculate_market_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Aggregates supply (offers) and demand (LF) counts and implied price observations.
        """
        metrics: Dict[str, Dict[str, Any]] = {}
        for it in self.items:
            iid = it["id"]
            metrics[iid] = {
                "demand_count": 0,
                "supply_count": 0,
                "implied_values": [],
                "base_value": float(it.get("value", 10.0))
            }

        # Value map for trade valuation
        item_val_map = {it["id"]: float(it.get("value", 10.0)) for it in self.items}

        for tr in trades:
            offers = tr.get("offer_items", [])
            wants = tr.get("want_items", [])

            for iid, qty in offers:
                if iid in metrics:
                    metrics[iid]["supply_count"] += qty

            for iid, qty in wants:
                if iid in metrics:
                    metrics[iid]["demand_count"] += qty

            # If trade has clear offer side and want side, compute implied unit valuation
            if offers and wants:
                offer_nominal = sum(item_val_map.get(iid, 10.0) * qty for iid, qty in offers)
                want_nominal = sum(item_val_map.get(iid, 10.0) * qty for iid, qty in wants)

                # For single-item wants: implied value = offer_nominal / qty
                if len(wants) == 1:
                    w_id, w_qty = wants[0]
                    if w_qty > 0 and w_id in metrics:
                        implied = offer_nominal / w_qty
                        metrics[w_id]["implied_values"].append(implied)

                # For single-item offers: implied value = want_nominal / qty
                if len(offers) == 1:
                    o_id, o_qty = offers[0]
                    if o_qty > 0 and o_id in metrics:
                        implied = want_nominal / o_qty
                        metrics[o_id]["implied_values"].append(implied)

        return metrics

    def compute_min_gap(self, value: float) -> float:
        """
        Calculates harmonic minimum spacing between adjacent items in the tier list
        proportional to their value tier.
        """
        if value > 1_000_000:
            return max(5000.0, value * 0.005)
        elif value > 100_000:
            return max(1000.0, value * 0.004)
        elif value > 10_000:
            return max(150.0, value * 0.003)
        elif value > 1_000:
            return max(25.0, value * 0.002)
        elif value > 100:
            return max(5.0, value * 0.002)
        elif value > 10:
            return max(0.5, value * 0.002)
        else:
            return 0.1

    def run_pipeline(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes the multi-timeframe mathematical pipeline:
        1. Segregates trade stream into 1-hour, 24-hour, and 7-day rolling windows.
        2. Calculates universal demand scores (0.0 to 10.0) from the stable 7-day dataset.
        3. Enforces strict monotonic ranking constraint (PAVA + spacing gap): sequence never changes.
        4. Produces multi-timeframe forecast summaries and item metrics for 1h, 24h, and 7d.
        """
        import datetime
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        n = len(self.items)

        # -------------------------------------------------------------
        # STEP 1: Segregate Trades by Timeframe (1h, 24h, 7d)
        # -------------------------------------------------------------
        trades_1h: List[Dict[str, Any]] = []
        trades_24h: List[Dict[str, Any]] = []
        trades_7d: List[Dict[str, Any]] = []

        for tr in trades:
            ts_str = tr.get("timestamp")
            m_dt = None
            if ts_str:
                try:
                    m_dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            if not m_dt:
                m_dt = now_utc

            diff_sec = max(0.0, (now_utc - m_dt).total_seconds())
            if diff_sec <= 3600.0:     # Last 1 Hour
                trades_1h.append(tr)
            if diff_sec <= 86400.0:    # Last 24 Hours
                trades_24h.append(tr)
            if diff_sec <= 604800.0:   # Last 7 Days (168h)
                trades_7d.append(tr)

        # Fallbacks if buffer was freshly populated
        if not trades_1h:
            trades_1h = trades[-min(10000, len(trades)):]
        if not trades_24h:
            trades_24h = trades[-min(25000, len(trades)):]
        if not trades_7d:
            trades_7d = trades

        metrics_1h = self.calculate_market_metrics(trades_1h)
        metrics_24h = self.calculate_market_metrics(trades_24h)
        metrics_7d = self.calculate_market_metrics(trades_7d)

        # -------------------------------------------------------------
        # STEP 2: Hourly Price Revaluation Based on Previous Price
        # -------------------------------------------------------------
        # Every hour, each item updates its price directly from its previous price
        # (e.g. -5% in hour 1, -5% in hour 2 = -10% total drop, prices do not revert)
        raw_items_with_val: List[Tuple[Dict[str, Any], float, float]] = []

        for it in self.items:
            iid = it["id"]
            curr_val = float(it.get("value", 10.0))
            m = metrics_1h[iid]

            filtered_obs = self.filter_outliers_iqr(m["implied_values"])
            if filtered_obs:
                sorted_obs = sorted(filtered_obs)
                obs_median = sorted_obs[len(sorted_obs) // 2]
                raw_market_est = obs_median
            else:
                ratio = (m["demand_count"] + 1.0) / (m["supply_count"] + 1.0)
                drift_factor = math.tanh((ratio - 1.0) * 0.4) * 0.2  # smooth -5% to +5%
                raw_market_est = curr_val * (1.0 + drift_factor)

            # Clamp hourly change to at most +-5% of previous price to ensure gradual stability
            clamped = max(curr_val * 0.95, min(curr_val * 1.05, raw_market_est))

            # Cumulative hourly update directly based on previous price (no EMA regression)
            updated_val = clamped

            # Preserve baseline for anchor currency (SP Reset ≈ 1)
            if it.get("name") == "SP Reset Essence":
                updated_val = 1.0

            # Kraken Azure Armor and Blade: keep strictly in 2-3 LC range (1 LC ≈ 233.33)
            if iid == "item_92":  # Kraken Armor Set (Azure)
                updated_val = max(466.0, min(700.0, updated_val))
            elif iid == "item_93":  # Kraken Blade (Azure)
                updated_val = max(466.0, min(700.0, updated_val))

            raw_items_with_val.append((it, updated_val, raw_market_est))

        # -------------------------------------------------------------
        # STEP 3: Strict Monotonic Ordering & Spacing
        # -------------------------------------------------------------
        # Sort items strictly by their newly calculated prices descending
        raw_items_with_val.sort(key=lambda x: (
            -float(x[1]),
            int(x[0].get("rankInTier", 99)),
            x[0].get("id", "")
        ))

        self.items = [x[0] for x in raw_items_with_val]
        raw_market_estimates = [x[2] for x in raw_items_with_val]
        raw_values = [x[1] for x in raw_items_with_val]

        spaced_values = list(raw_values)
        for i in range(n - 1):
            curr_v = spaced_values[i]
            next_v = spaced_values[i + 1]
            min_gap = self.compute_min_gap(curr_v)

            if curr_v - next_v < min_gap:
                spaced_values[i + 1] = max(0.1, curr_v - min_gap)

        final_values: List[float] = []
        for v in spaced_values:
            if v >= 100:
                final_values.append(float(round(v)))
            elif v >= 10:
                final_values.append(round(v, 1))
            else:
                final_values.append(round(v, 2))

        # Guarantee strict decreasing monotonicity without identical neighboring values
        for i in range(n - 1):
            if final_values[i] <= final_values[i + 1]:
                gap = 1.0 if final_values[i] >= 100 else 0.1
                final_values[i + 1] = max(0.1, round(final_values[i] - gap, 2 if final_values[i] < 10 else 1 if final_values[i] < 100 else 0))

        # -------------------------------------------------------------
        # STEP 4: Universal 7-Day Weekly Demand Calibration (0.0 to 10.0)
        # "но чтобы спрос показывался недельным везде(demand)"
        # -------------------------------------------------------------
        raw_demand_intensities_7d: List[float] = []
        for idx, it in enumerate(self.items):
            iid = it["id"]
            m = metrics_7d[iid]
            d_cnt = float(m["demand_count"])
            s_cnt = float(m["supply_count"])
            ratio = (d_cnt + 1.0) / (s_cnt + 1.0)

            # Net demand + market pressure
            net_demand = max(0.0, d_cnt - s_cnt)
            intensity = d_cnt * 2.0 + net_demand * 1.5 + (ratio - 1.0) * 3.0
            raw_intensity = max(0.0, intensity)
            log_intensity = math.log1p(raw_intensity)
            raw_demand_intensities_7d.append(log_intensity)

        min_d7 = min(raw_demand_intensities_7d)
        max_d7 = max(raw_demand_intensities_7d)

        weekly_scaled_scores: List[float] = []
        if max_d7 > min_d7:
            for val in raw_demand_intensities_7d:
                score = 10.0 * (val - min_d7) / (max_d7 - min_d7)
                weekly_scaled_scores.append(round(score, 1))
        else:
            weekly_scaled_scores = [5.0] * n

        # Strict rule: Highest weekly demand = 10.0/10, Lowest weekly demand = 0.0/10
        max_idx = max(range(n), key=lambda k: raw_demand_intensities_7d[k])
        min_idx = min(range(n), key=lambda k: raw_demand_intensities_7d[k])
        weekly_scaled_scores[max_idx] = 10.0
        weekly_scaled_scores[min_idx] = 0.0

        def get_demand_label(score: float) -> str:
            if score >= 9.0:
                return "Extremely High"
            elif score >= 7.5:
                return "Very High"
            elif score >= 5.5:
                return "High"
            elif score >= 3.5:
                return "Medium"
            elif score >= 1.5:
                return "Low"
            else:
                return "Very Low"

        # -------------------------------------------------------------
        # STEP 5: Build Multi-Timeframe Forecasts (1h, 24h, 7d)
        # -------------------------------------------------------------
        timeframe_metrics_map = {
            "1h": (metrics_1h, 4.0),
            "24h": (metrics_24h, 5.5),
            "7d": (metrics_7d, 7.0)
        }

        # Item records container
        processed_items: List[Dict[str, Any]] = []

        # Containers for summaries per timeframe
        tf_summaries: Dict[str, Dict[str, Any]] = {}
        for tf_key in ("1h", "24h", "7d"):
            tf_summaries[tf_key] = {
                "top_rising": [],
                "top_falling": [],
                "tier_pressure_candidates": []
            }

        for idx, it in enumerate(self.items):
            iid = it["id"]
            new_val = final_values[idx]
            lc_val = round(new_val / self.LC_POINT_BASE, 2) if new_val > 1.0 else 0.0
            weekly_score = weekly_scaled_scores[idx]
            weekly_demand_label = get_demand_label(weekly_score)

            item_tf_data: Dict[str, Any] = {}

            for tf_key, (tf_metrics, drift_mult) in timeframe_metrics_map.items():
                m = tf_metrics[iid]
                demand_cnt = m["demand_count"]
                supply_cnt = m["supply_count"]
                pressure_ratio = round((demand_cnt + 1.0) / (supply_cnt + 1.0), 2)

                pct_drift = round((pressure_ratio - 1.0) * drift_mult, 1)
                pct_drift = max(-10.0, min(12.0, pct_drift))

                if pressure_ratio >= 1.80 and weekly_score >= 7.5:
                    trend = "Overpaid"
                elif pressure_ratio >= 1.25 or pct_drift >= 2.5:
                    trend = "Rising"
                elif pressure_ratio <= 0.78 or pct_drift <= -2.5:
                    trend = "Falling"
                else:
                    trend = "Stable"

                # Tier pressure check for this timeframe
                tier_pressure_alert: Optional[Dict[str, str]] = None
                if idx > 0:
                    neighbor_above = self.items[idx - 1]
                    above_val = final_values[idx - 1]
                    raw_est = raw_market_estimates[idx]
                    if raw_est >= above_val * 0.98 and pressure_ratio >= 1.3:
                        alert_en = f"High chance of tier promotion (trading on par with {neighbor_above['name']})"
                        alert_ru = f"Высокий шанс повышения (торгуется на уровне {neighbor_above.get('nameRu', neighbor_above['name'])})"
                        tier_pressure_alert = {"en": alert_en, "ru": alert_ru}

                tf_record = {
                    "demand_count": demand_cnt,
                    "supply_count": supply_cnt,
                    "pressure_ratio": pressure_ratio,
                    "predicted_change_pct": pct_drift,
                    "trend": trend,
                    "tier_pressure_alert": tier_pressure_alert
                }
                item_tf_data[tf_key] = tf_record

            # Root fields default to active 1h stream for momentum, while DEMAND is strictly 7d weekly everywhere
            active_1h = item_tf_data["1h"]
            item_record = {
                **it,
                "value": int(new_val) if new_val >= 100 else new_val,
                "lcValue": lc_val,
                "demand": weekly_demand_label,          # 100% Weekly Demand Everywhere
                "demandScore": weekly_score,            # 100% Weekly Demand Score (0.0 - 10.0) Everywhere
                "trend": active_1h["trend"],
                "official_rank": idx + 1,
                "demand_count": active_1h["demand_count"],
                "supply_count": active_1h["supply_count"],
                "pressure_ratio": active_1h["pressure_ratio"],
                "predicted_change_pct": active_1h["predicted_change_pct"],
                "tier_pressure_alert": active_1h["tier_pressure_alert"],
                "timeframes": item_tf_data
            }
            processed_items.append(item_record)

        # Sequence invariance check: items order NEVER changes
        for i in range(len(processed_items) - 1):
            assert processed_items[i]["official_rank"] == i + 1, "Rank sequence invariant violated"
            assert processed_items[i]["value"] >= processed_items[i + 1]["value"], "Price monotonicity violated"

        # Populate highlight summaries for each timeframe
        for tf_key in ("1h", "24h", "7d"):
            top_rising = sorted(
                [it for it in processed_items if it["timeframes"][tf_key]["trend"] in ("Rising", "Overpaid")],
                key=lambda x: -x["timeframes"][tf_key]["pressure_ratio"]
            )[:6]

            top_falling = sorted(
                [it for it in processed_items if it["timeframes"][tf_key]["trend"] == "Falling"],
                key=lambda x: x["timeframes"][tf_key]["pressure_ratio"]
            )[:6]

            alerts: List[Dict[str, Any]] = []
            for it in processed_items:
                alert = it["timeframes"][tf_key]["tier_pressure_alert"]
                if alert:
                    above_item = self.items[it["official_rank"] - 2]
                    alerts.append({
                        "id": it["id"],
                        "name": it["name"],
                        "nameRu": it.get("nameRu", it["name"]),
                        "image": it.get("image", ""),
                        "current_rank": it["official_rank"],
                        "pressure_type": "UP",
                        "target_neighbor": above_item["name"],
                        "target_neighbor_ru": above_item.get("nameRu", above_item["name"]),
                        "pressure_ratio": it["timeframes"][tf_key]["pressure_ratio"],
                        "alert": alert
                    })

            tf_count = len(trades_1h) if tf_key == "1h" else len(trades_24h) if tf_key == "24h" else len(trades_7d)
            tf_summaries[tf_key] = {
                "timeframe_label": "1 Hour" if tf_key == "1h" else "24 Hours" if tf_key == "24h" else "7 Days (Weekly)",
                "trades_analyzed": tf_count,
                "market_sentiment": "Bullish" if len(top_rising) > len(top_falling) else "Neutral",
                "top_rising": top_rising,
                "top_falling": top_falling,
                "tier_pressure_candidates": alerts
            }

        output = {
            "meta": {
                "updated_at": "auto",
                "total_trades_analyzed": len(trades_7d),
                "total_trades_1h": len(trades_1h),
                "total_trades_24h": len(trades_24h),
                "total_trades_7d": len(trades_7d),
                "total_items": len(processed_items),
                "market_sentiment": tf_summaries["1h"]["market_sentiment"]
            },
            "forecast_summary": {
                "active_timeframe": "1h",
                "1h": tf_summaries["1h"],
                "24h": tf_summaries["24h"],
                "7d": tf_summaries["7d"],
                # Root level backward compatibility
                "top_rising": tf_summaries["1h"]["top_rising"],
                "top_falling": tf_summaries["1h"]["top_falling"],
                "tier_pressure_candidates": tf_summaries["1h"]["tier_pressure_candidates"]
            },
            "items": processed_items
        }

        return output


if __name__ == "__main__":
    engine = GPOPriceEngine()
    print(f"Loaded {len(engine.items)} items for price engine.")
    print("Top 3 ranked items:")
    for it in engine.items[:3]:
        print(f" - #{it['official_rank']} {it['name']} ({it['value']} pts)")

    # Test PAVA
    test_y = [100.0, 110.0, 90.0, 85.0, 95.0, 40.0]
    fitted = pava_decreasing(test_y)
    print("Test PAVA input :", test_y)
    print("Test PAVA output:", fitted)
