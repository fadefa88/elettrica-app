#!/usr/bin/env python3
"""Rewrite cars_motornet.json as a slim frontend-only catalog.

The script keeps only fields actually used by the site and drops raw scraping/debug
metadata such as specs_raw, fuel_code, fuel_original, image_source_url,
image_local_path, source_site, scraped_at, powertrain and motornet_detail_url.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


SLIM_FIELDS = [
    "id",
    "category",
    "brand",
    "model",
    "version",
    "fuel",
    "price_eur",
    "power_kw",
    "power_cv",
    "consumption_l_100km",
    "consumption_kg_100km",
    "consumption_kwh_100km",
    "battery_kwh",
    "range_wltp_km",
    "emissions_g_km",
    "image_url",
    "source_url",
]

FUEL_LABELS = {
    "E": "elettrica",
    "EH": "elettrica_idrogeno",
    "B": "benzina",
    "D": "diesel",
    "IB": "ibrida_benzina",
    "ID": "ibrida_diesel",
    "G": "gpl",
    "IG": "ibrida_gpl",
    "M": "metano",
    "IM": "ibrida_metano",
}

NUMERIC_FIELDS = {
    "price_eur",
    "power_kw",
    "power_cv",
    "consumption_l_100km",
    "consumption_kg_100km",
    "consumption_kwh_100km",
    "battery_kwh",
    "range_wltp_km",
    "emissions_g_km",
}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def parse_number(value: Any) -> float | int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        if not math.isfinite(n):
            return None
        return int(n) if n.is_integer() else n
    text = clean(value).replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        n = float(text)
    except ValueError:
        return None
    if not math.isfinite(n):
        return None
    return int(n) if n.is_integer() else n


def first_text(car: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = clean(car.get(key))
        if value:
            return value
    return ""


def first_number(car: dict[str, Any], *keys: str) -> float | int | None:
    for key in keys:
        value = parse_number(car.get(key))
        if value is not None:
            return value
    return None


def fuel_of(car: dict[str, Any]) -> str:
    fuel = clean(car.get("fuel")).lower()
    if fuel:
        return fuel
    code = clean(car.get("fuel_code")).upper()
    if code in FUEL_LABELS:
        return FUEL_LABELS[code]
    return clean(car.get("fuel_original")).lower()


def category_of(car: dict[str, Any]) -> str:
    category = clean(car.get("category")).lower()
    if category in {"electric", "thermal"}:
        return category
    fuel = fuel_of(car)
    return "electric" if "elettr" in fuel else "thermal"


def slim_car(car: dict[str, Any]) -> dict[str, Any]:
    slim: dict[str, Any] = {
        "id": first_text(car, "id"),
        "category": category_of(car),
        "brand": first_text(car, "brand"),
        "model": first_text(car, "model"),
        "version": first_text(car, "version", "powertrain"),
        "fuel": fuel_of(car),
    }

    source_url = first_text(car, "source_url", "motornet_detail_url")
    image_url = first_text(car, "image_url", "image_local_path", "image_source_url")
    if source_url:
        slim["source_url"] = source_url
    if image_url:
        slim["image_url"] = image_url

    for field in NUMERIC_FIELDS:
        value = first_number(car, field)
        if value is not None:
            slim[field] = value

    return {key: slim[key] for key in SLIM_FIELDS if key in slim and slim[key] not in (None, "")}


def slim_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cars = payload.get("cars")
    if not isinstance(cars, list):
        raise SystemExit("Input JSON must be an object with cars[]")
    return {
        "source": payload.get("source") or "motornet.it",
        "status": "ok",
        "schema": "cars_motornet_slim_v1",
        "cars": [slim_car(car) for car in cars if isinstance(car, dict)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Slim Motornet JSON to frontend-only fields.")
    parser.add_argument("--input", default="data/cars_motornet.json", help="Input Motornet JSON")
    parser.add_argument("--out", default="data/cars_motornet.slim.json", help="Output JSON")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.out)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    payload = json.loads(in_path.read_text(encoding="utf-8"))
    slim = slim_payload(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(slim, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Cars written: {len(slim['cars'])}")
    print(f"Output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
