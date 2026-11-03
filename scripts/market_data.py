"""Shared data boundaries for the collector, price engine and publisher."""
import datetime as dt
import json
import math
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLEXIBLE_TIERS = {"Very Unstable", "New Items"}


def utc_time(value):
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Missing timestamp")
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def iso_time(value):
    return utc_time(value).isoformat(timespec="microseconds")


def load_catalog(path=None):
    payload = json.loads(Path(path or ROOT / "data/catalog.json").read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = {"schema_version": 1, "source": {"revision": "legacy"}, "items": payload}
    ids = set()
    for index, item in enumerate(payload["items"], 1):
        if not item.get("id") or item["id"] in ids:
            raise ValueError("Catalogue contains missing or duplicate IDs")
        ids.add(item["id"])
        item.setdefault("official_rank", index)
        item.setdefault("rank_locked", item.get("tier") not in FLEXIBLE_TIERS)
        item.setdefault("unit_id", item["id"])
        item.setdefault("unit_quantity", 1)
        if not isinstance(item["unit_quantity"], int) or item["unit_quantity"] < 1:
            raise ValueError("Invalid catalogue pack quantity")
    return payload


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temp = stream.name
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def validate_snapshot(snapshot, catalog):
    items = snapshot["items"]
    expected = {item["id"]: item for item in catalog["items"]}
    actual = {item["id"]: item for item in items}
    if len(actual) != len(items) or actual.keys() != expected.keys():
        raise ValueError("Snapshot catalogue coverage mismatch")
    locked = sorted((item for item in catalog["items"] if item["rank_locked"]),
                    key=lambda item: item["official_rank"])
    if [item["id"] for item in items if expected[item["id"]]["rank_locked"]] != [item["id"] for item in locked]:
        raise ValueError("Official item sequence changed")
    last_value = None
    for item in locked:
        value = actual[item["id"]]["value"]
        if value is not None:
            if last_value is not None and last_value <= value:
                raise ValueError("Official price hierarchy violated")
            last_value = value
    for item in items:
        original = expected[item["id"]]
        if item["official_rank"] != original["official_rank"] or item["tier"] != original["tier"]:
            raise ValueError("Market data overwrote the official rank")
        value = item["value"]
        if value is not None and (isinstance(value, bool) or not math.isfinite(value) or value <= 0):
            raise ValueError("Invalid item price")
        if item["name"] == "SP Reset Essence" and value != 1:
            raise ValueError("SP Reset anchor must equal 1 point")
        if original["unit_id"] != item["id"]:
            unit = actual[original["unit_id"]]
            unit_quantity = expected[unit["id"]]["unit_quantity"]
            if (unit["value"] is None) != (value is None):
                raise ValueError("Pack has a price without its unit")
            if value is not None and abs(value - round(unit["value"] / unit_quantity * original["unit_quantity"], 2)) > 0.001:
                raise ValueError("Pack price is not the sum of its units")
