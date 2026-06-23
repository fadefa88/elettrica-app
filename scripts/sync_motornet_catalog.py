#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.robotparser
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import import_motornet as base
import import_motornet_resume as resume

IGNORED_BRAND_CODES = {"COR"}


def bool_arg(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sì", "on"}


def canonical_url(value: object) -> str:
    text = base.clean(value)
    return base.full_url(text) if text else ""


def car_url(car: dict[str, Any]) -> str:
    return canonical_url(car.get("source_url") or car.get("motornet_detail_url"))


def brand_code_from_brand_url(value: object) -> str:
    text = canonical_url(value)
    if not text:
        return ""
    return text.rstrip("/").split("/")[-1].strip().upper()


def is_ignored_brand_code(value: object) -> bool:
    return str(value or "").strip().upper() in IGNORED_BRAND_CODES


def is_ignored_brand_url(value: object) -> bool:
    return is_ignored_brand_code(brand_code_from_brand_url(value))


def is_ignored_detail_url(value: object) -> bool:
    code = resume.brand_code_from_detail_url(canonical_url(value))
    return is_ignored_brand_code(code)


def is_ignored_car(car: dict[str, Any]) -> bool:
    brand = base.clean(car.get("brand")).upper()
    url = car_url(car)
    if is_ignored_brand_code(brand):
        return True
    if is_ignored_detail_url(url):
        return True
    return False


def filter_ignored_brand_urls(urls: list[str]) -> list[str]:
    filtered = []
    skipped = 0
    for url in urls:
        if is_ignored_brand_url(url):
            skipped += 1
            continue
        filtered.append(url)
    if skipped:
        print(f"Ignored brand URLs: {skipped} codes={sorted(IGNORED_BRAND_CODES)}")
    return filtered


def load_existing_catalog(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], [], {}
    payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    cars = payload.get("cars") or []
    errors = payload.get("errors") or []
    valid_cars = [car for car in cars if isinstance(car, dict) and not is_ignored_car(car)]
    skipped = len([car for car in cars if isinstance(car, dict)]) - len(valid_cars)
    if skipped:
        print(f"Ignored existing cars from skipped brand codes: {skipped} codes={sorted(IGNORED_BRAND_CODES)}")
    return (
        valid_cars,
        [err for err in errors if isinstance(err, dict)],
        payload if isinstance(payload, dict) else {},
    )


def dedupe_keep_last(cars: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for car in cars:
        if is_ignored_car(car):
            continue
        url = car_url(car)
        if url:
            by_url[url] = car
    return by_url


def build_brand_urls(page, args, robots, errors: list[dict[str, Any]]) -> tuple[list[str], int]:
    requests_count = 0
    if args.brand_codes.strip():
        urls = [
            f"{base.BASE}/auto/scheda-modello/{code.strip().upper()}"
            for code in args.brand_codes.split(",")
            if code.strip() and not is_ignored_brand_code(code)
        ]
        return filter_ignored_brand_urls(urls), requests_count

    if not base.can_fetch(robots, base.LIST_URL):
        errors.append({"url": base.LIST_URL, "error": "blocked_by_robots"})
        return [], requests_count

    print("LIST", base.LIST_URL)
    page.goto(base.LIST_URL, wait_until="domcontentloaded", timeout=args.timeout)
    page.wait_for_timeout(2500)
    requests_count += 1
    urls = base.discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/[A-Z0-9]{2,4}$")
    if not urls:
        print("  automatic brand discovery returned 0 links; using known brand code fallback")
        urls = [f"{base.BASE}/auto/scheda-modello/{code}" for code in resume.extended_brand_codes()]
    return filter_ignored_brand_urls(urls), requests_count


def discover_active_detail_urls(page, brand_urls: list[str], args, robots, errors: list[dict[str, Any]]) -> tuple[list[str], int]:
    active: list[str] = []
    seen: set[str] = set()
    requests_count = 0

    for brand_url in brand_urls:
        if is_ignored_brand_url(brand_url):
            print("SKIP ignored brand", brand_url)
            continue
        if not base.can_fetch(robots, brand_url):
            errors.append({"url": brand_url, "error": "blocked_by_robots"})
            continue
        try:
            time.sleep(args.delay)
            print("BRAND", brand_url)
            page.goto(brand_url, wait_until="domcontentloaded", timeout=args.timeout)
            page.wait_for_timeout(2500)
            requests_count += 1

            detail_links = base.discover_links_after_clicking_menus(
                page,
                r"^/auto/scheda-modello/modello/\d+/allestimento/[^/]+$",
            )
            model_links = base.discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/modello/\d+$")
            if model_links:
                expanded, requests_count = base.expand_model_links_to_details(page, model_links, args, robots, errors, requests_count)
                for detail_url in expanded:
                    if detail_url not in detail_links:
                        detail_links.append(detail_url)

            print("  active detail links:", len(detail_links))
            for detail_url in detail_links:
                url = canonical_url(detail_url)
                if is_ignored_detail_url(url):
                    continue
                if url and url not in seen:
                    seen.add(url)
                    active.append(url)
        except Exception as exc:
            errors.append({"url": brand_url, "error": f"brand_scan: {exc}"})

    return active, requests_count


def parse_new_car(page, detail_url: str, brand_name: str, args, robots, image_session, errors: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, bool]:
    if is_ignored_detail_url(detail_url):
        print("SKIP ignored detail", detail_url)
        return None, False
    if not base.can_fetch(robots, detail_url):
        errors.append({"url": detail_url, "error": "blocked_by_robots"})
        return None, False

    page.goto(detail_url, wait_until="domcontentloaded", timeout=args.timeout)
    try:
        page.wait_for_selector("text=Scheda tecnica", timeout=8000)
    except PlaywrightTimeoutError:
        page.wait_for_timeout(2000)

    car = base.parse_detail(page, detail_url, brand_name)
    if not car or is_ignored_car(car):
        return None, False

    downloaded = False
    if args.download_images and car.get("image_source_url"):
        try:
            time.sleep(max(1, args.delay / 2))
            image_data = base.download_image(
                image_session,
                car["image_source_url"],
                car["id"],
                Path(args.image_dir),
                int(args.timeout / 1000),
                int(args.max_image_mb * 1024 * 1024),
            )
            if image_data:
                car.update(image_data)
                downloaded = True
        except Exception as exc:
            car["image_error"] = str(exc)
            errors.append({"url": car.get("image_source_url"), "error": f"image: {exc}"})

    return car, downloaded


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily Motornet catalog sync: add new cars and remove cars no longer listed.")
    parser.add_argument("--catalog", default=str(base.OUT), help="Catalog JSON path")
    parser.add_argument("--brand-codes", default="", help="CSV brand codes for limited test runs. Empty = all brands")
    parser.add_argument("--new-limit", type=int, default=0, help="Maximum new cars to parse. 0 = no limit")
    parser.add_argument("--delay", type=float, default=4)
    parser.add_argument("--timeout", type=int, default=45000)
    parser.add_argument("--download-images", default="true")
    parser.add_argument("--image-dir", default="assets/cars/motornet")
    parser.add_argument("--max-image-mb", type=float, default=6)
    parser.add_argument("--remove-missing", default="true")
    parser.add_argument("--allow-large-removal", default="false")
    parser.add_argument("--max-removal-ratio", type=float, default=0.25)
    parser.add_argument("--min-active-links", type=int, default=100)
    parser.add_argument("--checkpoint-every", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()

    args.download_images = bool_arg(args.download_images)
    args.remove_missing = bool_arg(args.remove_missing)
    args.allow_large_removal = bool_arg(args.allow_large_removal)
    args.image_dir = str(args.image_dir)
    catalog_path = Path(args.catalog)

    existing_cars, existing_errors, existing_payload = load_existing_catalog(catalog_path)
    existing_by_url = dedupe_keep_last(existing_cars)
    print(f"Existing Motornet cars: {len(existing_cars)} unique_urls={len(existing_by_url)}")

    robots = urllib.robotparser.RobotFileParser()
    robots.set_url(f"{base.BASE}/robots.txt")
    try:
        robots.read()
    except Exception as exc:
        print("WARN robots non leggibile:", exc)

    errors = list(existing_errors[-50:])
    image_session = requests.Session()
    image_session.headers.update({"User-Agent": base.UA})
    requests_count = 0
    images_downloaded = 0
    full_catalog_scan = not bool(args.brand_codes.strip())

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=base.UA, locale="it-IT")
        page = context.new_page()

        brand_urls, count = build_brand_urls(page, args, robots, errors)
        requests_count += count
        print("brand links:", len(brand_urls))

        active_urls, count = discover_active_detail_urls(page, brand_urls, args, robots, errors)
        requests_count += count
        active_urls = [url for url in active_urls if not is_ignored_detail_url(url)]
        print("Active Motornet detail URLs:", len(active_urls))

        if full_catalog_scan and len(active_urls) < args.min_active_links:
            raise SystemExit(
                f"Safety stop: only {len(active_urls)} active detail URLs discovered; "
                f"min-active-links={args.min_active_links}. Existing catalog was not modified."
            )

        active_set = set(active_urls)
        removed_urls: set[str] = set()
        if args.remove_missing and full_catalog_scan and existing_by_url:
            removed_urls = set(existing_by_url) - active_set
            removal_ratio = len(removed_urls) / max(1, len(existing_by_url))
            if removed_urls and removal_ratio > args.max_removal_ratio and not args.allow_large_removal:
                raise SystemExit(
                    f"Safety stop: would remove {len(removed_urls)} cars ({removal_ratio:.1%}), "
                    f"above max-removal-ratio={args.max_removal_ratio:.1%}. "
                    "Rerun manually with allow_large_removal=true if this is expected."
                )
        elif args.remove_missing and not full_catalog_scan:
            print("Limited brand run: deletion disabled outside full-catalog scans.")

        new_urls = [url for url in active_urls if url not in existing_by_url and not is_ignored_detail_url(url)]
        if args.new_limit > 0:
            new_urls = new_urls[: args.new_limit]
        print("New URLs to parse:", len(new_urls))
        print("URLs to remove:", len(removed_urls))

        parsed_new: dict[str, dict[str, Any]] = {}
        brand_name_cache: dict[str, str] = {}
        for index, detail_url in enumerate(new_urls, start=1):
            brand_code = resume.brand_code_from_detail_url(detail_url)
            if is_ignored_brand_code(brand_code):
                print("SKIP ignored brand code", brand_code, detail_url)
                continue
            brand_name = ""
            if brand_code:
                brand_url = f"{base.BASE}/auto/scheda-modello/{brand_code}"
                if brand_code not in brand_name_cache:
                    try:
                        time.sleep(args.delay)
                        page.goto(brand_url, wait_until="domcontentloaded", timeout=args.timeout)
                        page.wait_for_timeout(1200)
                        requests_count += 1
                        brand_name_cache[brand_code] = base.brand_name_from_page(page, brand_url)
                    except Exception:
                        brand_name_cache[brand_code] = base.BRAND_NAME_BY_CODE.get(brand_code, brand_code)
                brand_name = brand_name_cache.get(brand_code, "")

            try:
                time.sleep(args.delay)
                car, downloaded = parse_new_car(page, detail_url, brand_name, args, robots, image_session, errors)
                requests_count += 1
                if car and not is_ignored_car(car):
                    parsed_new[canonical_url(car.get("source_url") or detail_url)] = car
                    images_downloaded += int(downloaded)
                    print(f"  + [{index}/{len(new_urls)}] {car.get('brand')} {car.get('model')} price={car.get('price_eur')}")
            except Exception as exc:
                errors.append({"url": detail_url, "error": f"detail_parse: {exc}"})

        cars_by_url = dict(existing_by_url)
        for url in removed_urls:
            cars_by_url.pop(url, None)
        cars_by_url.update(parsed_new)

        # Preserve Motornet list order for stable frontend dropdowns and deterministic diffs.
        ordered_cars = [cars_by_url[url] for url in active_urls if url in cars_by_url and not is_ignored_car(cars_by_url[url])]
        if not full_catalog_scan:
            touched = set(active_urls)
            untouched = [car for url, car in cars_by_url.items() if url not in touched and not is_ignored_car(car)]
            ordered_cars = untouched + [cars_by_url[url] for url in active_urls if url in cars_by_url and not is_ignored_car(cars_by_url[url])]

        context.close()
        browser.close()

    payload_args = SimpleNamespace(
        delay=args.delay,
        limit=args.new_limit,
        checkpoint_every=0,
        download_images=args.download_images,
        image_dir=args.image_dir,
    )
    payload = base.build_payload(ordered_cars, errors, payload_args, requests_count, images_downloaded)
    payload["schema"] = "cars_motornet_daily_sync_v1"
    payload["sync"] = {
        "mode": "full" if full_catalog_scan else "brand_subset",
        "active_urls": len(active_urls),
        "existing_unique_urls_before": len(existing_by_url),
        "new_added": len(parsed_new),
        "removed_missing_from_motornet": len(removed_urls),
        "ignored_brand_codes": sorted(IGNORED_BRAND_CODES),
        "new_limit": args.new_limit,
        "remove_missing": bool(args.remove_missing and full_catalog_scan),
    }
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "Done sync:",
        f"cars={len(ordered_cars)}",
        f"new_added={len(parsed_new)}",
        f"removed={len(removed_urls)}",
        f"requests={requests_count}",
        f"images_downloaded={images_downloaded}",
        f"errors={len(errors)}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
