#!/usr/bin/env python3
"""Update data/charging.json from public charging tariff pages.

There is no single official national daily feed for public EV charging prices in
Italy. This script uses a hybrid approach:
- fetch a small set of public tariff pages from charging operators;
- extract values clearly expressed as EUR/kWh when possible;
- when pages do not expose static EUR/kWh values, use configured public-source
  estimates for that operator/segment;
- avoid daily commits when the resulting market values did not change.

Sources can be overridden with CHARGING_PRICE_SOURCES_JSON, for example:
[
  {"name":"Example","url":"https://example.com/tariffe","segment":"hpc","fallback_values":{"hpc":0.79}}
]
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHARGING_JSON = ROOT / "data" / "charging.json"

DEFAULT_SOURCES = [
    {"name": "Enel X Way", "url": "https://www.enelxway.com/it/it/servizi/soluzioni-ricarica-pubblica/tariffe", "segment": "mixed", "fallback_values": {"ac": 0.69, "dc": 0.89, "hpc": 0.99}},
    {"name": "Plenitude On the Road / Be Charge", "url": "https://www.plenitude.com/it-it/on-the-road/ricarica-pubblica/tariffe", "segment": "mixed", "fallback_values": {"ac": 0.65, "dc": 0.85, "hpc": 0.95}},
    {"name": "A2A e-moving", "url": "https://www.a2a.it/casa/mobilita-elettrica", "segment": "mixed", "fallback_values": {"ac": 0.59, "dc": 0.79, "hpc": 0.87}},
    {"name": "IONITY", "url": "https://www.ionity.eu/it", "segment": "hpc", "fallback_values": {"hpc": 0.69}},
    {"name": "Tesla Supercharger", "url": "https://www.tesla.com/it_it/supercharger", "segment": "tesla", "fallback_values": {"tesla_supercharger_owner": 0.50, "tesla_supercharger_non_tesla": 0.62}},
]

SEGMENT_KEYS = {"ac": "ac", "dc": "dc", "hpc": "hpc", "tesla": "tesla_supercharger_owner", "mixed": "public_mixed"}
PRICE_PATTERNS = [
    re.compile(r"(?P<value>\d{1,2}[\.,]\d{1,3})\s*(?:€|eur|euro)\s*(?:/|al|per)?\s*kwh", re.I),
    re.compile(r"(?:€|eur|euro)\s*(?P<value>\d{1,2}[\.,]\d{1,3})\s*(?:/|al|per)?\s*kwh", re.I),
    re.compile(r"(?P<value>\d{1,3})\s*(?:cent|centesimi)\s*(?:/|al|per)?\s*kwh", re.I),
]


def clean_text(markup: str) -> str:
    markup = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</?(p|div|li|tr|td|th|section|article|h\d)[^>]*>", "\n", markup)
    text = re.sub(r"<[^>]+>", " ", markup)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_price(raw: str, is_cent: bool = False) -> float | None:
    value = raw.replace(".", "").replace(",", ".") if "," in raw and "." in raw else raw.replace(",", ".")
    try:
        price = float(value)
    except ValueError:
        return None
    if is_cent:
        price = price / 100
    if math.isfinite(price) and 0.15 <= price <= 1.50:
        return round(price, 3)
    return None


def extract_prices(text: str) -> list[float]:
    prices: list[float] = []
    for pattern in PRICE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group("value")
            is_cent = "cent" in match.group(0).lower() or "centesimi" in match.group(0).lower()
            price = parse_price(raw, is_cent=is_cent)
            if price is not None and price not in prices:
                prices.append(price)
    return prices


def normalize_values(values: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, raw in (values or {}).items():
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and 0.15 <= value <= 1.50:
            out[str(key)] = round(value, 3)
    return out


def classify_segment_prices(source: dict[str, Any], prices: list[float]) -> dict[str, float]:
    if not prices:
        return {}
    segment = str(source.get("segment", "mixed"))
    values = sorted(prices)
    if segment == "mixed":
        if len(values) >= 3:
            return {"ac": values[0], "dc": values[len(values) // 2], "hpc": values[-1], "public_mixed": round(statistics.fmean(values), 3)}
        return {"public_mixed": round(statistics.fmean(values), 3)}
    return {SEGMENT_KEYS.get(segment, "public_mixed"): round(statistics.median(values), 3)}


def load_sources() -> list[dict[str, Any]]:
    raw = os.environ.get("CHARGING_PRICE_SOURCES_JSON", "").strip()
    if not raw:
        return DEFAULT_SOURCES
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise SystemExit("CHARGING_PRICE_SOURCES_JSON must be a list")
    out = []
    for item in parsed:
        if isinstance(item, dict) and item.get("url"):
            out.append({"name": str(item.get("name") or item.get("url")), "url": str(item.get("url")), "segment": str(item.get("segment") or "mixed"), "fallback_values": normalize_values(item.get("fallback_values") or {})})
    return out or DEFAULT_SOURCES


def fetch_source(source: dict[str, Any], use_estimates: bool) -> tuple[dict[str, float], dict[str, Any]]:
    fallback_values = normalize_values(source.get("fallback_values") or {})
    report = {"name": source.get("name"), "url": source.get("url"), "segment": source.get("segment", "mixed")}
    try:
        response = requests.get(str(source["url"]), timeout=(8, 25), headers={"User-Agent": "Mozilla/5.0 elettrica-tco"})
        response.raise_for_status()
        prices = extract_prices(clean_text(response.text))
        values = classify_segment_prices(source, prices)
        if values:
            return values, {**report, "status": "scraped", "prices_found": prices, "values_used": values}
        if use_estimates and fallback_values:
            return fallback_values, {**report, "status": "configured_estimate_no_static_prices", "prices_found": prices, "values_used": fallback_values}
        return {}, {**report, "status": "no_static_prices", "prices_found": prices, "values_used": {}}
    except Exception as exc:
        if use_estimates and fallback_values:
            return fallback_values, {**report, "status": "configured_estimate_after_fetch_error", "error": str(exc), "values_used": fallback_values}
        return {}, {**report, "status": "fetch_error", "error": str(exc), "values_used": {}}


def load_payload(path: Path) -> dict[str, Any]:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit(f"Invalid charging JSON: {path}")
        payload.setdefault("charging_efficiency", {"home": 0.92, "mixed": 0.90, "public": 0.94})
        payload.setdefault("market_average", {})
        return payload
    return {"updated_at": datetime.now(timezone.utc).isoformat(), "status": "indicative_italy_seed", "charging_efficiency": {"home": 0.92, "mixed": 0.90, "public": 0.94}, "market_average": {"home": 0.30, "ac": 0.59, "dc": 0.72, "hpc": 0.85, "public_mixed": 0.74, "tesla_supercharger_owner": 0.50, "tesla_supercharger_non_tesla": 0.62}}


def market_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    for key in sorted(set(a) | set(b)):
        try:
            if round(float(a.get(key)), 3) != round(float(b.get(key)), 3):
                return False
        except (TypeError, ValueError):
            if a.get(key) != b.get(key):
                return False
    return True


def update_payload(payload: dict[str, Any], sources: list[dict[str, Any]], use_estimates: bool) -> tuple[dict[str, Any], bool]:
    previous_market = dict(payload.get("market_average") or {})
    market = dict(previous_market)
    by_key: dict[str, list[float]] = {}
    reports = []
    for source in sources:
        values, report = fetch_source(source, use_estimates=use_estimates)
        reports.append(report)
        for key, value in values.items():
            by_key.setdefault(key, []).append(float(value))

    for key, values in by_key.items():
        market[key] = round(statistics.fmean(values), 3)

    public_nums = [market.get("ac"), market.get("dc"), market.get("hpc")]
    public_nums = [float(x) for x in public_nums if isinstance(x, (int, float)) and 0.15 <= float(x) <= 1.50]
    if len(public_nums) >= 3:
        market["public_mixed"] = round(public_nums[0] * 0.35 + public_nums[1] * 0.40 + public_nums[2] * 0.25, 3)

    if not by_key or market_equal(previous_market, market):
        return payload, False

    candidate = dict(payload)
    candidate["updated_at"] = datetime.now(timezone.utc).isoformat()
    candidate["status"] = "updated_public_tariff_pages" if any(r.get("status") == "scraped" for r in reports) else "configured_public_tariff_estimates"
    candidate["market_average"] = market
    candidate["source_reports"] = reports
    candidate["notes"] = {"method": "Scrape public tariff pages first; use configured public-source estimates when static prices are not exposed.", "public_mixed": "Weighted approximation from AC/DC/HPC; not an official national price index.", "confidence": "configured estimate" if candidate["status"].startswith("configured") else "scraped best effort"}
    return candidate, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Update public EV charging price estimates.")
    parser.add_argument("--out", default=str(DEFAULT_CHARGING_JSON), help="charging.json path")
    parser.add_argument("--no-configured-estimates", action="store_true", help="Do not use configured source estimates when scraping finds no static prices")
    args = parser.parse_args()
    out = Path(args.out)
    payload = load_payload(out)
    sources = load_sources()
    payload, changed = update_payload(payload, sources, use_estimates=not args.no_configured_estimates)
    if changed:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload.get("status"), "changed": changed, "updated_at": payload.get("updated_at"), "market_average": payload.get("market_average"), "sources_checked": sources, "note": "charging.json updated." if changed else "No market value change; charging.json kept unchanged."}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
