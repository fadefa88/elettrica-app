#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

CATALOG = Path("data/cars_motornet.json")

BATTERY_TEXT_RE = re.compile(r"(?<!\d)([1-9]\d{0,2}(?:[\.,]\d{1,2})?)\s*k\s*w\s*h\b", re.I)
CONSUMPTION_TEXT_RE = re.compile(r"\d+(?:[\.,]\d+)?\s*(?:k\s*w\s*h|k\s*w\s*/\s*h)\s*/?\s*100\s*km", re.I)


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalize(value: Any) -> str:
    text = clean(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # Motornet sometimes exposes a typo in the technical sheet.
    text = text.replace("automonia", "autonomia")
    # Motornet sometimes writes electric consumption as kW/h 100 km.
    text = re.sub(r"k\s*w\s*/\s*h", "kwh", text)
    text = re.sub(r"k\s*w\s*h", "kwh", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_number(value: Any) -> float | None:
    text = clean(value)
    if not text:
        return None
    match = re.search(r"-?\d+(?:[\.,]\d+)?", text.replace(" ", ""))
    if not match:
        return None
    raw = match.group(0).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def rounded(value: float, digits: int = 1) -> float:
    q = Decimal(str(value)).quantize(Decimal("1") if digits == 0 else Decimal("0.1"), rounding=ROUND_HALF_UP)
    out = float(q)
    return int(out) if digits == 0 else out


def valid_kwh_100(value: Any) -> float | None:
    n = parse_number(value)
    if n is not None and 5 <= n <= 60:
        return rounded(n)
    return None


def valid_range_km(value: Any) -> int | None:
    n = parse_number(value)
    if n is not None and 30 <= n <= 1500:
        return int(rounded(n, 0))
    return None


def valid_battery_kwh(value: Any) -> float | None:
    n = parse_number(value)
    if n is not None and 5 <= n <= 250:
        return rounded(n)
    return None


def is_electric(car: dict[str, Any]) -> bool:
    fuel = normalize(car.get("fuel"))
    category = normalize(car.get("category"))
    fuel_code = normalize(car.get("fuel_code"))
    return "elettric" in fuel or category == "electric" or fuel_code == "e"


def flatten_specs(car: dict[str, Any]) -> list[tuple[str, str]]:
    raw = car.get("specs_raw")
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(key: Any, value: Any) -> None:
        k = clean(key)
        v = clean(value)
        if not k or not v or v == "[object Object]":
            return
        sig = (k, v)
        if sig in seen:
            return
        seen.add(sig)
        out.append(sig)

    def walk(node: Any, path: list[str]) -> None:
        if node is None:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, path)
            return
        if not isinstance(node, dict):
            add(" ".join(path), node)
            return

        label = node.get("label") or node.get("name") or node.get("key") or node.get("title")
        value = node.get("value") or node.get("val") or node.get("text")
        if label is not None and value is not None:
            add(" ".join(path + [clean(label)]), value)

        for key, value in node.items():
            if key in {"label", "name", "key", "title", "value", "val", "text"} and not isinstance(value, (dict, list)):
                continue
            if isinstance(value, (dict, list)):
                walk(value, path + [clean(key)])
            else:
                # Add both with and without path so malformed flat Motornet specs remain findable.
                add(" ".join(path + [clean(key)]), value)
                add(key, value)

    walk(raw, [])
    return out


def find_ev_consumption(car: dict[str, Any]) -> float | None:
    direct = valid_kwh_100(car.get("consumption_kwh_100km"))
    if direct:
        return direct

    for key, value in flatten_specs(car):
        nk = normalize(key)
        nv = normalize(value)
        if "max" in nk:
            continue
        # Motornet examples: "kW/h 100 km": "15.2".
        if "kwh" in nk and "100" in nk and "km" in nk:
            n = valid_kwh_100(value)
            if n:
                return n
        # Safer fallback for textual rows.
        joined = f"{key} {value}"
        if CONSUMPTION_TEXT_RE.search(joined):
            # Prefer the value column if it is numeric, else parse the whole row.
            n = valid_kwh_100(value) or valid_kwh_100(joined)
            if n:
                return n
        if "consumo" in nk and "combinato" in nk and not any(bad in nk for bad in ("co2", "gas")):
            n = valid_kwh_100(value)
            if n:
                return n
    return None


def find_ev_range(car: dict[str, Any]) -> int | None:
    direct = valid_range_km(car.get("range_wltp_km")) or valid_range_km(car.get("autonomy_wltp_km"))
    if direct:
        return direct

    entries = flatten_specs(car)

    # Prefer combined non-full-optional range over urbano/full optional.
    priority_rules = (
        ("autonomia", "solo", "elettrico", "combinato"),
        ("autonomia", "elettrico", "combinato"),
        ("autonomia", "wltp", "combinato"),
        ("autonomia", "combinato"),
        ("autonomia", "solo", "elettrico"),
        ("autonomia", "elettrico"),
        ("autonomia",),
    )
    hard_excludes = ("urbano", "max")
    soft_excludes = ("full", "optional")

    for required in priority_rules:
        for allow_full_optional in (False, True):
            for key, value in entries:
                nk = normalize(key)
                if any(token not in nk for token in required):
                    continue
                if any(token in nk for token in hard_excludes):
                    continue
                if not allow_full_optional and any(token in nk for token in soft_excludes):
                    continue
                n = valid_range_km(value)
                if n:
                    return n
    return None


def find_battery_from_specs(car: dict[str, Any]) -> float | None:
    for key, value in flatten_specs(car):
        nk = normalize(key)
        if any(token in nk for token in ("batter", "accumulator", "accumulatore")) and any(
            token in nk for token in ("capac", "kwh", "utile", "netta", "lorda", "energia")
        ):
            n = valid_battery_kwh(value)
            if n:
                return n
    return None


def find_battery_from_name(car: dict[str, Any]) -> float | None:
    fields = [
        car.get("display_name"),
        car.get("title"),
        car.get("name"),
        car.get("brand"),
        car.get("model"),
        car.get("version"),
        car.get("powertrain"),
    ]
    text = " · ".join(clean(v) for v in fields if clean(v))
    if not text:
        return None
    text = CONSUMPTION_TEXT_RE.sub(" ", text)
    for match in BATTERY_TEXT_RE.finditer(text):
        n = valid_battery_kwh(match.group(1))
        if n:
            return n
    return None


def enrich_ev(car: dict[str, Any]) -> bool:
    if not is_electric(car):
        return False

    changed = False

    kwh100 = find_ev_consumption(car)
    if kwh100 is not None and car.get("consumption_kwh_100km") != kwh100:
        car["consumption_kwh_100km"] = kwh100
        car["consumption_source"] = "motornet_specs_raw"
        changed = True

    range_km = find_ev_range(car)
    if range_km is not None and car.get("range_wltp_km") != range_km:
        car["range_wltp_km"] = range_km
        car["range_source"] = "motornet_specs_raw"
        changed = True

    existing_battery = valid_battery_kwh(car.get("battery_kwh"))
    if existing_battery:
        if car.get("battery_kwh") != existing_battery:
            car["battery_kwh"] = existing_battery
            changed = True
        return changed

    battery = find_battery_from_specs(car)
    source = "motornet_specs_raw" if battery else None

    if battery is None:
        battery = find_battery_from_name(car)
        source = "motornet_model_name" if battery else None

    if battery is None and kwh100 and range_km:
        battery = valid_battery_kwh((range_km * kwh100) / 100)
        source = "estimated_from_wltp_range_and_consumption" if battery else None

    if battery is not None:
        car["battery_kwh"] = battery
        car["battery_source"] = source or "motornet_derived"
        if source == "estimated_from_wltp_range_and_consumption":
            car["battery_estimated"] = True
        else:
            car.pop("battery_estimated", None)
        changed = True

    return changed


def main() -> None:
    if not CATALOG.exists():
        raise SystemExit("data/cars_motornet.json not found")

    data = json.loads(CATALOG.read_text(encoding="utf-8") or "{}")
    cars = data.get("cars") or []

    changed = 0
    estimated = 0
    with_consumption = 0
    with_range = 0
    with_battery = 0

    for car in cars:
        if not isinstance(car, dict):
            continue
        before = json.dumps(car, ensure_ascii=False, sort_keys=True)
        enrich_ev(car)
        after = json.dumps(car, ensure_ascii=False, sort_keys=True)
        if before != after:
            changed += 1
        if is_electric(car):
            if valid_kwh_100(car.get("consumption_kwh_100km")):
                with_consumption += 1
            if valid_range_km(car.get("range_wltp_km")):
                with_range += 1
            if valid_battery_kwh(car.get("battery_kwh")):
                with_battery += 1
            if car.get("battery_estimated"):
                estimated += 1

    post = data.get("postprocess") if isinstance(data.get("postprocess"), dict) else {}
    post["ev_battery_derivation"] = {
        "version": "ev_battery_derivation_v1",
        "changed_cars": changed,
        "ev_with_consumption_kwh_100km": with_consumption,
        "ev_with_range_wltp_km": with_range,
        "ev_with_battery_kwh": with_battery,
        "estimated_batteries": estimated,
        "rule": "EV battery_kwh derived from direct battery specs, model-name kWh, or WLTP range * kWh/100 km; handles Motornet Automonia typo and kW/h 100 km labels",
    }
    data["postprocess"] = post

    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "Derived EV fields: "
        f"changed={changed}, ev_consumption={with_consumption}, ev_range={with_range}, "
        f"ev_battery={with_battery}, estimated_batteries={estimated}, cars={len(cars)}"
    )


if __name__ == "__main__":
    main()
