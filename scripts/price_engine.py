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
        Executes the full 4-stage mathematical pipeline:
        Stage 1: Raw implied valuation + EMA clamp.
        Stage 2: Strict Isotonic Regression (PAVA).
        Stage 3: Smooth spacing regularization (no identical values).
        Stage 4: Forecasting & Tier Pressure alerts.
        """
        metrics = self.calculate_market_metrics(trades)
        n = len(self.items)

        # -------------------------------------------------------------
        # STAGE 1: Raw Implied Value & EMA Clamping (+-10% limit)
        # -------------------------------------------------------------
        raw_values: List[float] = []
        raw_market_estimates: List[float] = []

        for it in self.items:
            iid = it["id"]
            curr_val = float(it.get("value", 10.0))
            m = metrics[iid]

            filtered_obs = self.filter_outliers_iqr(m["implied_values"])
            if filtered_obs:
                # Median of filtered observations
                sorted_obs = sorted(filtered_obs)
                obs_median = sorted_obs[len(sorted_obs) // 2]
                raw_market_est = obs_median
            else:
                # Drift from bid/ask pressure
                ratio = (m["demand_count"] + 1.0) / (m["supply_count"] + 1.0)
                drift_factor = math.tanh((ratio - 1.0) * 0.4) * 0.08  # smooth -8% to +8%
                raw_market_est = curr_val * (1.0 + drift_factor)

            raw_market_estimates.append(raw_market_est)

            # Clamp per 12h cycle to maximum +-10% to prevent market manipulation
            clamped = max(curr_val * 0.90, min(curr_val * 1.10, raw_market_est))
            # EMA Smoothing: 88% current weight + 12% market target
            smoothed = 0.88 * curr_val + 0.12 * clamped

            # Preserve baseline for anchor currency (SP Reset ≈ 1)
            if it.get("name") == "SP Reset Essence":
                smoothed = 1.0

            raw_values.append(smoothed)

        # -------------------------------------------------------------
        # STAGE 2: Strict Monotonic Constraint (PAVA)
        # -------------------------------------------------------------
        # All items are ordered by official_rank (index 0 = Rank 1 = most expensive)
        pava_fitted = pava_decreasing(raw_values)

        # -------------------------------------------------------------
        # STAGE 3: Smooth Spacing Regularization (No Zero Gaps)
        # -------------------------------------------------------------
        spaced_values = list(pava_fitted)
        for i in range(n - 1):
            curr_v = spaced_values[i]
            next_v = spaced_values[i + 1]
            min_gap = self.compute_min_gap(curr_v)

            if curr_v - next_v < min_gap:
                spaced_values[i + 1] = max(0.1, curr_v - min_gap)

        # Re-normalize lowest item anchor if needed (SP Reset)
        # Round nicely for display (integers for values >= 100, 1 decimal for < 100)
        final_values: List[float] = []
        for v in spaced_values:
            if v >= 100:
                final_values.append(float(round(v)))
            elif v >= 10:
                final_values.append(round(v, 1))
            else:
                final_values.append(round(v, 2))

        # -------------------------------------------------------------
        # STAGE 4: Forecasting Engine & Tier Pressure Alerts
        # -------------------------------------------------------------
        max_demand = max(m["demand_count"] for m in metrics.values()) if metrics else 1
        processed_items: List[Dict[str, Any]] = []
        tier_pressure_candidates: List[Dict[str, Any]] = []

        for idx, it in enumerate(self.items):
            iid = it["id"]
            m = metrics[iid]
            new_val = final_values[idx]
            old_val = float(it.get("value", new_val))
            raw_market_est = raw_market_estimates[idx]

            demand_cnt = m["demand_count"]
            supply_cnt = m["supply_count"]
            pressure_ratio = round((demand_cnt + 1.0) / (supply_cnt + 1.0), 2)

            # Combined demand score: 70% curated PvP/PvE baseline + 30% dynamic market volume
            curated_score = float(it.get("demandScore", 8.0))
            dynamic_score = 1.0 + 9.0 * (math.log1p(demand_cnt) / math.log1p(max(max_demand, 5)))
            blended_score = round(0.70 * curated_score + 0.30 * dynamic_score, 1)
            demand_score = max(1.0, min(10.0, blended_score))

            # Trend & Expected 24-48h drift
            pct_drift = round((pressure_ratio - 1.0) * 5.5, 1)
            pct_drift = max(-10.0, min(12.0, pct_drift))

            if pressure_ratio >= 1.85 and demand_score >= 8.5:
                trend = "Overpaid"
            elif pressure_ratio >= 1.25 or pct_drift >= 3.0:
                trend = "Rising"
            elif pressure_ratio <= 0.78 or pct_drift <= -3.0:
                trend = "Falling"
            else:
                trend = "Stable"

            # TIER PRESSURE ALERT:
            # Check if actual market trades value this item higher than its neighbor above
            tier_pressure_alert: Optional[Dict[str, str]] = None
            if idx > 0:
                neighbor_above = self.items[idx - 1]
                above_val = final_values[idx - 1]
                if raw_market_est >= above_val * 0.98 and pressure_ratio >= 1.3:
                    alert_en = f"High chance of tier promotion in next official tier list (trading on par with {neighbor_above['name']})"
                    alert_ru = f"Высокий шанс повышения в следующем официальном тир-листе (торгуется на уровне {neighbor_above.get('nameRu', neighbor_above['name'])})"
                    tier_pressure_alert = {"en": alert_en, "ru": alert_ru}
                    tier_pressure_candidates.append({
                        "id": iid,
                        "name": it["name"],
                        "nameRu": it.get("nameRu", it["name"]),
                        "image": it.get("image", ""),
                        "current_rank": idx + 1,
                        "pressure_type": "UP",
                        "target_neighbor": neighbor_above["name"],
                        "target_neighbor_ru": neighbor_above.get("nameRu", neighbor_above["name"]),
                        "pressure_ratio": pressure_ratio,
                        "alert": tier_pressure_alert
                    })

            lc_val = round(new_val / self.LC_POINT_BASE, 2)
            if new_val <= 1.0:
                lc_val = 0.0

            item_record = {
                **it,
                "value": int(new_val) if new_val >= 100 else new_val,
                "lcValue": lc_val,
                "demand": "Extremely High" if demand_score >= 9.5 else "Very High" if demand_score >= 8.5 else "High" if demand_score >= 7.0 else "Medium" if demand_score >= 5.0 else "Low",
                "demandScore": demand_score,
                "trend": trend,
                "official_rank": idx + 1,
                "demand_count": demand_cnt,
                "supply_count": supply_cnt,
                "pressure_ratio": pressure_ratio,
                "predicted_change_pct": pct_drift,
                "tier_pressure_alert": tier_pressure_alert
            }
            processed_items.append(item_record)

        # Highlight summaries
        top_rising = sorted([it for it in processed_items if it["trend"] in ("Rising", "Overpaid")], key=lambda x: -x["pressure_ratio"])[:6]
        top_falling = sorted([it for it in processed_items if it["trend"] == "Falling"], key=lambda x: x["pressure_ratio"])[:6]

        output = {
            "meta": {
                "updated_at": "auto",
                "total_trades_analyzed": len(trades),
                "total_items": len(processed_items),
                "market_sentiment": "Bullish" if len(top_rising) > len(top_falling) else "Neutral"
            },
            "forecast_summary": {
                "top_rising": top_rising,
                "top_falling": top_falling,
                "tier_pressure_candidates": tier_pressure_candidates
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
