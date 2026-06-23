#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

CATALOG = Path("data/cars_motornet.json")

PRICE_KEYWORDS = (
    "prezzo",
    "listino",
    "chiavi in mano",
)
BAD_PRICE_KEYWORDS = (
    "cilindrata",
    "kw",
    "cv",
    "co2",
    "emission",
    "consumo",
    "autonomia",
    "batteria",
    "velocità",
    "accelerazione",
)
MONEY_RE = re.compile(
    r"(?<![\w/])(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d{5,7}(?:,\d{1,2})?)\s*(?:€|eur)",
    re.I,
)
BATTERY_TEXT_RE = re.compile(r"(?:^|[^\d])([1-9]\d{0,2}(?:[\.,]\d{1,2})?)\s*kwh\b", re.I)
CONSUMPTION_TEXT_RE = re.compile(r"\d+(?:[\.,]\d+)?\s*kwh\s*/?\s*100\s*km", re.I)


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_number(value: Any) -> float | None:
    text = clean(value)
    if not text:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?(?:[.,]\d+)?", text.replace(" ", ""))
    if not match:
        return None
    raw = match.group(0)
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    elif raw.count(".") == 1:
        before, after = raw.split(".")
        if len(after) == 3 and len(before) <= 3:
            raw = before + after
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
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


def valid_battery_kwh(value: Any) -> float | None:
    n = parse_number(value)
    if n is not None and 5 <= n <= 250:
        return rounded(n)
    return None


def valid_range_km(value: Any) -> int | None:
    n = parse_number(value)
    if n is not None and 30 <= n <= 1500:
        return int(rounded(n, 0))
    return None


def parse_money(value: Any) -> int | None:
    text = clean(value).replace("\xa0", " ")
    if not text:
        return None

    match = MONEY_RE.search(text)
    if not match:
        return None

    raw = match.group(1).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None

    if amount < Decimal("7000") or amount > Decimal("3000000"):
        return None

    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def specs(car: dict[str, Any]) -> dict[str, Any]:
    raw = car.get("specs_raw")
    return raw if isinstance(raw, dict) else {}


def spec_entries(car: dict[str, Any]) -> list[tuple[str, str]]:
    """Return flattened specs, including nested Motornet sections."""
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
        if not isinstance(node, (dict, list)):
            add(" ".join(path), node)
            return
        if isinstance(node, list):
            for item in node:
                walk(item, path)
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
                add(" ".join(path + [clean(key)]), value)
                add(key, value)

    walk(specs(car), [])
    return out


def find_specs_value(car: dict[str, Any], include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> Any | None:
    for key, value in spec_entries(car):
        k = clean(key).lower()
        if all(token.lower() in k for token in include) and not any(token.lower() in k for token in exclude):
            return value
    return None


def find_specs_regex(car: dict[str, Any], patterns: tuple[str, ...], exclude: tuple[str, ...] = ()) -> Any | None:
    compiled = [re.compile(p, re.I) for p in patterns]
    excluded = [re.compile(p, re.I) for p in exclude]
    for key, value in spec_entries(car):
        k = clean(key).lower()
        if any(rx.search(k) for rx in excluded):
            continue
        if any(rx.search(k) for rx in compiled):
            return value
    return None


def find_price(car: dict[str, Any]) -> int | None:
    for key, value in spec_entries(car):
        k = clean(key).lower()
        if any(bad in k for bad in BAD_PRICE_KEYWORDS):
            continue
        if any(token in k for token in PRICE_KEYWORDS):
            money = parse_money(f"{key} {value}")
            if money:
                return money
    return None


def price_equals_non_price_field(car: dict[str, Any], price: int) -> bool:
    for key, value in spec_entries(car):
        k = clean(key).lower()
        if not any(token in k for token in BAD_PRICE_KEYWORDS):
            continue
        n = parse_number(value)
        if n is not None and int(round(n)) == price:
            return True
    return False


def battery_from_text(car: dict[str, Any]) -> float | None:
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


def find_ev_consumption(car: dict[str, Any]) -> float | None:
    direct = valid_kwh_100(car.get("consumption_kwh_100km"))
    if direct:
        return direct
    v = find_specs_regex(
        car,
        (
            r"kw\/?h\s*100\s*km",
            r"kwh\s*\/\s*100\s*km",
            r"kwh\s*100\s*km",
            r"consumo.*elettric.*combinato",
            r"consumo.*combinato",
        ),
        exclude=(r"max",),
    )
    return valid_kwh_100(v)


def find_ev_range(car: dict[str, Any]) -> int | None:
    direct = valid_range_km(car.get("range_wltp_km")) or valid_range_km(car.get("autonomy_wltp_km"))
    if direct:
        return direct
    v = find_specs_regex(
        car,
        (
            r"autonomia.*solo.*elettric.*combinato",
            r"autonomia.*elettric.*combinato",
            r"autonomia.*wltp.*combinato",
            r"autonomia.*combinato",
            r"^autonomia\s+wltp",
            r"autonomia.*solo.*elettric",
            r"autonomia.*elettric",
            r"^autonomia\b",
        ),
        exclude=(r"urbano", r"max"),
    )
    return valid_range_km(v)


def find_ev_battery(car: dict[str, Any], kwh100: float | None = None, range_km: int | None = None) -> tuple[float | None, str | None]:
    direct = valid_battery_kwh(car.get("battery_kwh"))
    if direct:
        return direct, car.get("battery_source") or "motornet_existing"

    v = find_specs_regex(
        car,
        (
            r"capac.*batter",
            r"cap\.?\s*batter",
            r"batter.*capac",
            r"^batteria$",
            r"batteria.*kwh",
            r"batteria.*utile",
            r"batteria.*netta",
            r"batteria.*lorda",
            r"accumulatore",
            r"capac.*accumulator",
            r"energia.*batter",
            r"battery.*capacity",
        ),
    )
    from_specs = valid_battery_kwh(v)
    if from_specs:
        return from_specs, "motornet_specs_raw"

    from_text = battery_from_text(car)
    if from_text:
        return from_text, "motornet_model_name"

    if kwh100 and range_km:
        estimated = valid_battery_kwh((range_km * kwh100) / 100)
        if estimated:
            return estimated, "estimated_from_wltp_range_and_consumption"

    return None, None


def fix_consumption(car: dict[str, Any]) -> bool:
    changed = False
    fuel = clean(car.get("fuel")).lower()
    is_electric = "elettr" in fuel or car.get("category") == "electric"

    if is_electric:
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

        battery, source = find_ev_battery(car, kwh100, range_km)
        if battery is not None and car.get("battery_kwh") != battery:
            car["battery_kwh"] = battery
            car["battery_source"] = source or "motornet_derived"
            if source == "estimated_from_wltp_range_and_consumption":
                car["battery_estimated"] = True
            else:
                car.pop("battery_estimated", None)
            changed = True
    else:
        v = (
            find_specs_value(car, ("consumo", "combinato"), ("co2", "kw/h", "kwh"))
            or find_specs_value(car, ("consumo", "misto"), ("co2", "kw/h", "kwh"))
            or find_specs_value(car, ("consumo",), ("co2", "kw/h", "kwh"))
        )
        n = parse_number(v)
        if n is not None and 0 < n <= 80:
            if "metano" in fuel:
                if car.get("consumption_kg_100km") != n:
                    car["consumption_kg_100km"] = n
                    car.pop("consumption_l_100km", None)
                    changed = True
            else:
                if car.get("consumption_l_100km") != n:
                    car["consumption_l_100km"] = n
                    changed = True
            car["consumption_source"] = "motornet_specs_raw"
    return changed


def fix_price(car: dict[str, Any]) -> bool:
    current = car.get("price_eur")
    current_int = int(current) if isinstance(current, (int, float)) else None
    price = find_price(car)
    if price:
        if current_int != price:
            car["price_eur"] = price
            car["price_source"] = "motornet_prezzo_di_listino"
            car.pop("price_missing", None)
            return True
        car["price_source"] = "motornet_prezzo_di_listino"
        car.pop("price_missing", None)
        return False

    if current_int is not None and price_equals_non_price_field(car, current_int):
        car.pop("price_eur", None)
        car["price_missing"] = True
        car["price_source"] = "not_found_in_motornet_specs"
        return True

    if current_int is not None and current_int < 8000:
        car.pop("price_eur", None)
        car["price_missing"] = True
        car["price_source"] = "not_found_in_motornet_specs"
        return True

    return False


def main() -> None:
    if not CATALOG.exists():
        raise SystemExit("data/cars_motornet.json not found")

    data = json.loads(CATALOG.read_text(encoding="utf-8") or "{}")
    cars = data.get("cars") or []
    changed = 0
    missing_prices = 0
    estimated_batteries = 0

    for car in cars:
        if not isinstance(car, dict):
            continue
        if fix_consumption(car):
            changed += 1
        if fix_price(car):
            changed += 1
        if car.get("price_missing"):
            missing_prices += 1
        if car.get("battery_estimated"):
            estimated_batteries += 1

    data["postprocess"] = {
        "version": "motornet_price_consumption_battery_v3",
        "changed_fields": changed,
        "missing_prices": missing_prices,
        "estimated_batteries": estimated_batteries,
        "rule": "prices only from explicit Motornet euro price/listino fields; EV battery filled from direct kWh, model name, or WLTP range * consumption",
    }
    CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Postprocessed Motornet catalogue: changed={changed}, missing_prices={missing_prices}, "
        f"estimated_batteries={estimated_batteries}, cars={len(cars)}"
    )


if __name__ == "__main__":
    main()
