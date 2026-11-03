"""Robust, anchored barter estimates with an immutable ordinary-tier subsequence.

Observations are asking prices, not completed trades. Unknown portions are excluded.
The optimization shares one variable per physical unit, including all chest packs.
"""
import datetime as dt
import hashlib
import json
import math
from collections import Counter, defaultdict

import numpy as np
from scipy.optimize import LinearConstraint, minimize

from scripts.market_data import load_catalog, utc_time, validate_snapshot


MIN_AUTHORS = 5
HALF_LIFE_HOURS = 48


class GPOPriceEngine:
    def __init__(self, items_path=None):
        self.catalog = load_catalog(items_path)
        self.items = self.catalog["items"]
        self.by_id = {item["id"]: item for item in self.items}
        self.locked = sorted((item for item in self.items if item["rank_locked"]),
                             key=lambda item: item["official_rank"])
        self.anchor = next((item["unit_id"] for item in self.items if item["name"] == "SP Reset Essence"), None)
        if not self.anchor:
            raise ValueError("Catalogue is missing the SP Reset anchor")

    def _side(self, entries):
        result = defaultdict(float)
        for entry in entries:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise ValueError("Malformed trade item")
            iid, quantity = entry
            if iid not in self.by_id or isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
                raise ValueError("Unknown trade item")
            if not math.isfinite(quantity) or quantity != int(quantity) or not 1 <= quantity <= 100000:
                raise ValueError("Invalid trade quantity")
            item = self.by_id[iid]
            multiplier = item["unit_quantity"] if iid != item["unit_id"] else 1
            result[item["unit_id"]] += quantity * multiplier
        return dict(result)

    def _observations(self, trades, now):
        latest = {}
        for trade in trades:
            try:
                stamp = utc_time(trade.get("timestamp"))
                age = (now - stamp).total_seconds() / 3600
                if not 0 <= age <= 168 or not trade.get("author_id") or not trade.get("counts_eligible", True):
                    continue
                offer, want = self._side(trade.get("offer_items", [])), self._side(trade.get("want_items", []))
            except (ValueError, TypeError, OverflowError):
                continue
            signature = json.dumps([sorted(offer.items()), sorted(want.items()), trade.get("issues", [])])
            key = (str(trade["author_id"]), signature)
            record = {"author": key[0], "signature": signature, "stamp": stamp, "age": age,
                      "offer": offer, "want": want,
                      "eligible": bool(offer and want and trade.get("pricing_eligible", True))}
            if key not in latest or stamp > latest[key]["stamp"]:
                latest[key] = record
        return list(latest.values())

    def _baseline(self, previous):
        old = {item["id"]: item for item in (previous or {}).get("items", [])}
        candidates = defaultdict(list)
        minimum_pack = {}
        for item in self.items:
            unit = item["unit_id"]
            quantity = item["unit_quantity"]
            minimum_pack[unit] = min(minimum_pack.get(unit, quantity), quantity)
            value = old.get(item["id"], {}).get("value", item.get("seed_value", item.get("value")))
            if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
                # A ranked pack is a better initial reference than a formerly unconstrained single.
                priority = (bool(item["rank_locked"]), quantity == 1)
                candidates[unit].append((priority, value / quantity))
        base = {unit: max(values, key=lambda candidate: candidate[0])[1] for unit, values in candidates.items()}
        base[self.anchor] = 1.0
        quantum = {unit: 0.01 / quantity for unit, quantity in minimum_pack.items()}
        return base, quantum, old

    @staticmethod
    def _vector(observation):
        units = observation["offer"].keys() | observation["want"].keys()
        return {unit: observation["offer"].get(unit, 0) - observation["want"].get(unit, 0)
                for unit in units if observation["offer"].get(unit, 0) != observation["want"].get(unit, 0)}

    def _infer_new_units(self, quotes, base):
        """Only identify unknown prices when the observed equations determine them."""
        authors = defaultdict(set)
        vectors = [self._vector(quote) for quote in quotes]
        for quote, vector in zip(quotes, vectors):
            for unit in vector:
                authors[unit].add(quote["author"])
        unknown = sorted(unit for unit in authors if unit not in base and len(authors[unit]) >= MIN_AUTHORS)
        # Iteration also handles chains such as A↔LC followed by B↔A.
        while unknown:
            progress = False
            for unit in list(unknown):
                rows = [(quote, vector) for quote, vector in zip(quotes, vectors)
                        if unit in vector and all(other == unit or other in base for other in vector)]
                if len({quote["author"] for quote, _ in rows}) < MIN_AUTHORS:
                    continue
                estimates = [-sum(base[other] * coefficient for other, coefficient in vector.items() if other != unit) / vector[unit]
                             for _, vector in rows]
                estimates = [value for value in estimates if math.isfinite(value) and value > 0]
                if len(estimates) >= MIN_AUTHORS:
                    base[unit] = float(np.median(estimates))
                    unknown.remove(unit)
                    progress = True
            if not progress:
                break
        if unknown:
            rows = [vector for vector in vectors if all(unit in base or unit in unknown for unit in vector)]
            if rows:
                a = np.array([[row.get(unit, 0) for unit in unknown] for row in rows], dtype=float)
                b = np.array([-sum(coefficient * base[unit] for unit, coefficient in row.items() if unit in base) for row in rows])
                scales = np.maximum(np.linalg.norm(a, axis=1), 1)
                a, b = a / scales[:, None], b / scales
                if np.linalg.matrix_rank(a) == len(unknown):
                    fitted = np.linalg.lstsq(a, b, rcond=None)[0]
                    if np.all(np.isfinite(fitted)) and np.all(fitted > 0):
                        base.update(zip(unknown, map(float, fitted)))

    def _ordered_prices_valid(self, units):
        values = [units[item["unit_id"]] * item["unit_quantity"] for item in self.locked if item["unit_id"] in units]
        return all(a > b for a, b in zip(values, values[1:]))

    def _reference_strength(self, supporters, base):
        groups = [(units, min(1, sum(math.exp(-math.log(2) * age / HALF_LIFE_HOURS)
                                    for age in authors.values()) / 30))
                  for units, authors in supporters.items() if len(authors) >= MIN_AUTHORS and units <= base.keys()]
        strength = {self.anchor: 1.0}
        changed = True
        while changed:
            changed = False
            for units, support in groups:
                # A chain cannot establish a stronger point reference than its weakest link.
                linked = min(support, max(strength.get(unit, 0) for unit in units))
                for unit in units:
                    if linked > strength.get(unit, 0):
                        strength[unit] = linked
                        changed = True
        return strength

    def _fit(self, quotes, base, quantum, previous, now, repair, new_units):
        keys = sorted(base)
        positions = {unit: index for index, unit in enumerate(keys)}
        scale = np.array([base[unit] for unit in keys])
        vectors = [self._vector(quote) for quote in quotes]
        authors = defaultdict(set)
        for quote, vector in zip(quotes, vectors):
            for unit in vector:
                authors[unit].add(quote["author"])
        old = {item["id"]: item for item in (previous or {}).get("items", [])}
        inserting_ranked = any(self.by_id[unit]["rank_locked"] for unit in new_units)
        bounds = []
        for unit, reference in zip(keys, scale):
            if unit == self.anchor:
                bounds.append((1.0, 1.0))
            elif repair:
                bounds.append((max(quantum[unit], 0.000001) / reference, None))
            elif unit in new_units:
                bounds.append((max(quantum[unit], 0.000001) / reference, None))
            elif len(authors[unit]) < MIN_AUTHORS:
                if inserting_ranked and self.by_id[unit]["rank_locked"]:
                    spacing = 0.04 * len(self.locked)
                    bounds.append((max(quantum[unit], reference - spacing) / reference, (reference + spacing) / reference))
                else:
                    bounds.append((1.0, 1.0))
            else:
                source_item = self.by_id[unit]
                prior = old.get(unit, {})
                last_update = prior.get("price_updated_at") or (previous or {}).get("meta", {}).get("price_updated_at")
                hours = max(0, (now - utc_time(last_update)).total_seconds() / 3600) if last_update else 24
                daily_limit = 0.30 if source_item["rank_locked"] else 0.60
                movement = min(0.75, math.expm1(math.log1p(daily_limit) * min(hours, 72) / 24))
                bounds.append((max(quantum[unit] / reference, 1 - movement), 1 + movement))
        movable = {unit for unit, (low, high) in zip(keys, bounds) if high is None or high > low}
        if not movable:
            return base.copy(), base.copy(), authors

        author_counts = Counter(quote["author"] for quote in quotes)
        rows, weights = [], []
        for quote, vector in zip(quotes, vectors):
            nominal = (sum(base[unit] * count for unit, count in quote["offer"].items()) +
                       sum(base[unit] * count for unit, count in quote["want"].items())) / 2
            if nominal <= 0:
                continue
            rows.append([vector.get(unit, 0) * base[unit] / nominal for unit in keys])
            weights.append(math.exp(-math.log(2) * quote["age"] / HALF_LIFE_HOURS) / author_counts[quote["author"]])
        matrix = np.array(rows) if rows else np.empty((0, len(keys)))
        weights = np.array(weights)
        prior_strength = np.full(len(keys), 0.03 if quotes else 1.0)

        def objective(x):
            residual = matrix @ x
            clipped = np.clip(residual, -0.15, 0.15)
            loss = np.where(np.abs(residual) <= 0.15, residual ** 2 / 2, 0.15 * (np.abs(residual) - 0.075))
            prior = x - 1
            return float(weights @ loss + np.sum(prior_strength * prior ** 2) / 2), matrix.T @ (weights * clipped) + prior_strength * prior

        constraints, lower = [], []
        priced = [item for item in self.locked if item["unit_id"] in base]
        for above, below in zip(priced, priced[1:]):
            if above["unit_id"] not in movable and below["unit_id"] not in movable:
                continue
            row = np.zeros(len(keys))
            row[positions[above["unit_id"]]] += above["unit_quantity"] * base[above["unit_id"]]
            row[positions[below["unit_id"]]] -= below["unit_quantity"] * base[below["unit_id"]]
            normalizer = max(abs(row).max(), 1)
            # Leave enough space for both prices to be rounded, including packs.
            gap = 2 * (above["unit_quantity"] * quantum[above["unit_id"]] + below["unit_quantity"] * quantum[below["unit_id"]])
            constraints.append(row / normalizer)
            lower.append(gap / normalizer)

        options = {"maxiter": 500, "ftol": 1e-12}
        raw = minimize(objective, np.ones(len(keys)), jac=True, bounds=bounds, method="SLSQP", options=options)
        if not raw.success:
            raise ValueError(f"Market fit did not converge: {raw.message}")
        linear = [LinearConstraint(np.array(constraints), np.array(lower), np.inf)] if constraints else []
        fitted = minimize(objective, raw.x, jac=True, bounds=bounds, constraints=linear, method="SLSQP", options=options)
        if not fitted.success:
            raise ValueError(f"Constrained price fit did not converge: {fitted.message}")
        return dict(zip(keys, map(float, fitted.x * scale))), dict(zip(keys, map(float, raw.x * scale))), authors

    def run_pipeline(self, trades, previous=None, as_of=None, allow_updates=True):
        now = utc_time(as_of) if as_of else dt.datetime.now(dt.timezone.utc)
        observations = self._observations(trades, now)
        quotes = []
        for quote in observations:
            vector = self._vector(quote)
            if quote["eligible"] and any(count > 0 for count in vector.values()) and any(count < 0 for count in vector.values()):
                quotes.append(quote)
        base, quantum, old_items = self._baseline(previous)
        existing_units = set(base)
        repair = not self._ordered_prices_valid(base)
        supporters = defaultdict(dict)
        for quote in quotes:
            ages = supporters[frozenset(self._vector(quote))]
            ages[quote["author"]] = min(quote["age"], ages.get(quote["author"], quote["age"]))
        # Support belongs to the barter relationship, not to an item's other markets.
        supported_quotes = [quote for quote in quotes
                            if len(supporters[frozenset(self._vector(quote))]) >= MIN_AUTHORS]
        if allow_updates:
            self._infer_new_units(supported_quotes, base)
        new_units = set(base) - existing_units
        quotes = [quote for quote in quotes if all(unit in base for unit in quote["offer"].keys() | quote["want"].keys())]
        supported_quotes = [quote for quote in supported_quotes
                            if all(unit in base for unit in quote["offer"].keys() | quote["want"].keys())]
        reference_strength = self._reference_strength(supporters, base)
        evidence_hash = hashlib.sha256(json.dumps(sorted((quote["author"], quote["signature"]) for quote in supported_quotes)).encode()).hexdigest()
        previous_meta = (previous or {}).get("meta", {})
        same_evidence = evidence_hash == previous_meta.get("evidence_hash")
        last_price_time = previous_meta.get("price_updated_at")
        fresh = not last_price_time or any(quote["stamp"] > utc_time(last_price_time) for quote in supported_quotes)
        active_quotes = supported_quotes if fresh and not same_evidence and allow_updates else []
        if repair or active_quotes or new_units:
            units, raw_units, authors = self._fit(active_quotes, base, quantum, previous, now, repair, new_units)
        else:
            units, raw_units, authors = base.copy(), base.copy(), defaultdict(set)
        observation_ages = defaultdict(list)
        for quote in supported_quotes:
            for unit in self._vector(quote):
                authors[unit].add(quote["author"])
                observation_ages[unit].append(quote["age"])
        units = {unit: round(value / quantum[unit]) * quantum[unit] for unit, value in units.items()}
        units[self.anchor] = 1.0

        implied = defaultdict(lambda: defaultdict(list))
        for quote in supported_quotes:
            vector = self._vector(quote)
            residual = sum(units[unit] * count for unit, count in vector.items())
            for unit, count in vector.items():
                estimate = units[unit] - residual / count
                if math.isfinite(estimate) and estimate > 0:
                    implied[unit][quote["author"]].append(estimate)

        metrics = {}
        for label, hours in (("1h", 1), ("24h", 24), ("7d", 168)):
            supplied, demanded = defaultdict(set), defaultdict(set)
            for observation in observations:
                if observation["age"] <= hours:
                    for unit in observation["offer"]:
                        supplied[unit].add(observation["author"])
                    for unit in observation["want"]:
                        demanded[unit].add(observation["author"])
            metrics[label] = (supplied, demanded)

        records = []
        changes = []
        for item in self.items:
            iid, unit, pack = item["id"], item["unit_id"], item["unit_quantity"]
            value = round(units[unit] * pack, 2) if unit in units else None
            old = old_items.get(iid, {})
            old_value = old.get("value")
            changed = old_value is not None and value is not None and abs(value - old_value) >= 0.005
            tf = {}
            for label, (supplied, demanded) in metrics.items():
                s, d = len(supplied[unit]), len(demanded[unit])
                tf[label] = {"supply_count": s, "demand_count": d,
                             "pressure_ratio": round((d + 2) / (s + 2), 2) if s + d else None}
            s, d = tf["7d"]["supply_count"], tf["7d"]["demand_count"]
            sample_count = len(authors[unit])
            ages = observation_ages[unit]
            latest_age = min(ages) if ages else None
            confidence = round(min(1, sample_count / 30) * math.exp(-math.log(2) * (latest_age or 0) / HALF_LIFE_HOURS), 2) if sample_count else 0
            per_author = [float(np.median(values)) for values in implied[unit].values()]
            quote_range = None
            if len(per_author) >= MIN_AUTHORS:
                q25, median, q75 = map(float, np.percentile(per_author, [25, 50, 75]))
                quote_range = [round(float(q25) * pack, 2), round(float(q75) * pack, 2)]
                confidence = round(confidence / (1 + 4 * (q75 - q25) / max(median, 0.000001)), 2)
            confidence = round(min(confidence, reference_strength.get(unit, 0.3)), 2)
            raw_value = round(raw_units[unit] * pack, 2) if unit in raw_units else None
            constrained = value is not None and raw_value is not None and abs(value - raw_value) > 0.02
            price_status = "unknown" if value is None else "estimated" if sample_count >= MIN_AUTHORS else "carried" if old.get("price_status") in ("estimated", "carried") else "baseline"
            record = {key: val for key, val in item.items() if key not in ("seed_value", "value", "lcValue")}
            record.update({
                "value": value, "price_status": price_status,
                "price_updated_at": now.isoformat() if changed or (value is not None and not old and active_quotes and sample_count >= MIN_AUTHORS) else old.get("price_updated_at"),
                "confidence": confidence, "observation_authors": sample_count,
                "reference_basis": "unknown" if value is None else "sp" if unit in reference_strength else "historical",
                "quote_range": quote_range,
                "last_observed_at": (now - dt.timedelta(hours=latest_age)).isoformat() if latest_age is not None else None,
                "demandScore": round(10 * (d + 2) / (d + s + 4), 1) if d + s else None,
                "timeframes": tf, "constraint_applied": constrained,
                "market_estimate": raw_value if sample_count >= MIN_AUTHORS else None,
                "trend": "Rising" if changed and value > old_value else "Falling" if changed else "Stable",
            })
            records.append(record)
            if changed:
                changes.append({"id": iid, "old_value": old_value, "new_value": value,
                                "delta_pts": round(value - old_value, 2),
                                "delta_pct": round((value / old_value - 1) * 100, 2),
                                "reason": "official_order" if repair or (new_units and sample_count < MIN_AUTHORS) else "market"})

        by_id = {item["id"]: item for item in records}
        ordered = [by_id[item["id"]] for item in self.locked]
        flexible = sorted((item for item in records if not item["rank_locked"]),
                          key=lambda item: (-(item["value"] or 0), item["official_rank"]))
        for item in flexible:
            position = next((i for i, other in enumerate(ordered) if item["value"] is not None and
                             other["value"] is not None and other["value"] < item["value"]), len(ordered))
            ordered.insert(position, item)
        lc = next((item for item in records if item["name"] == "Legendary Fruit Chest"), None)
        for rank, item in enumerate(ordered, 1):
            item["display_rank"] = rank
            item["lcValue"] = round(item["value"] / lc["value"], 4) if lc and lc["value"] and item["value"] is not None else None
        meta = {
            "updated_at_iso": now.isoformat(), "updated_at": now.isoformat(),
            "price_updated_at": now.isoformat() if changes or (active_quotes and not previous and any(len(group) >= MIN_AUTHORS for group in authors.values())) else previous_meta.get("price_updated_at"),
            "catalog_revision": self.catalog["source"]["revision"],
            "evidence_hash": evidence_hash if allow_updates else previous_meta.get("evidence_hash", evidence_hash),
            "updates_paused": not allow_updates,
            "total_items": len(ordered), "total_trades_analyzed": len(observations),
            "price_observations": len(quotes), "supported_observations": len(supported_quotes),
            "pricing_method": "robust_offer_estimate_v1",
            **{f"total_trades_{label}": sum(q["age"] <= hours for q in observations)
               for label, hours in (("1h", 1), ("24h", 24), ("7d", 168))},
        }
        snapshot = {"schema_version": 2, "meta": meta, "official_source": self.catalog["source"],
                    "currency": {"anchor_id": self.anchor, "lc_id": lc["id"] if lc else None},
                    "items": ordered, "changes": changes}
        validate_snapshot(snapshot, self.catalog)
        snapshot["revision"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()).hexdigest()[:20]
        return snapshot
