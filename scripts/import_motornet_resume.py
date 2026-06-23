#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.robotparser
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import import_motornet as base

EXTRA_BRAND_CODES = [
    "ALN", "ALP", "BEN", "BES", "CAT", "CHA", "DEN", "COR", "DFS",
    "DOG", "FTH", "GVT", "GRW", "ICH", "ISU", "JAE", "LAM", "LEA", "LEE", "LEP",
    "LYN", "MAH", "MAX", "MHE", "MOR", "OMO", "SER", "SPO",
]
RESUME_STATE = Path("data/cars_motornet_resume_state.json")


def bool_arg(value: object) -> bool:
    return str(value).lower() in {"1", "true", "yes", "si", "sì", "on"}


def extended_brand_codes() -> list[str]:
    out: list[str] = []
    for code in list(base.KNOWN_BRAND_CODES) + EXTRA_BRAND_CODES:
        code = str(code).strip().upper()
        if code and code not in out:
            out.append(code)
    return out


def canonical_url(value: object) -> str:
    text = base.clean(value)
    return base.full_url(text) if text else ""


def normalize_resume_brand_code(value: object, valid_codes: set[str] | None = None) -> str | None:
    """Return a real Motornet brand code.

    Older resume logic could accidentally store values such as SPO0, derived from
    an allestimento code. When we know the brand codes available in the current
    run, prefer those codes and collapse SPO0 -> SPO, MOR0 -> MOR, etc.
    """
    raw = base.clean(value).upper()
    if not raw:
        return None

    codes = sorted((valid_codes or set(extended_brand_codes())), key=len, reverse=True)
    if raw in codes:
        return raw

    for code in codes:
        if raw.startswith(code):
            return code

    letters_before_digit = re.match(r"^([A-Z]{2,4})(?=\d)", raw)
    if letters_before_digit:
        candidate = letters_before_digit.group(1)
        if not valid_codes or candidate in valid_codes:
            return candidate

    letters = re.match(r"^([A-Z]{2,4})", raw)
    if letters:
        candidate = letters.group(1)
        if not valid_codes or candidate in valid_codes:
            return candidate

    return None


def brand_code_from_detail_url(url: object, valid_codes: set[str] | None = None) -> str | None:
    text = canonical_url(url)
    match = re.search(r"/allestimento/([A-Za-z0-9_-]+)", text)
    if not match:
        return None
    token = match.group(1).upper()

    codes = sorted((valid_codes or set(extended_brand_codes())), key=len, reverse=True)
    for code in codes:
        if token.startswith(code):
            return code

    return normalize_resume_brand_code(token, valid_codes)


def last_imported_brand_code(cars: list[dict], valid_codes: set[str] | None = None) -> str | None:
    for car in reversed(cars):
        if not isinstance(car, dict):
            continue
        for key in ("motornet_detail_url", "source_url"):
            code = brand_code_from_detail_url(car.get(key), valid_codes)
            if code:
                return code
    return None


def load_resume_state() -> dict:
    if not RESUME_STATE.exists():
        return {}
    try:
        payload = json.loads(RESUME_STATE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        print(f"WARN resume state not readable, ignoring: {exc}")
        return {}


def write_resume_state(brand_code: str | None, brand_url: str, cars_count: int, requests_count: int) -> None:
    if not brand_code:
        return
    RESUME_STATE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "cars_motornet_resume_state_v1",
        "last_completed_brand_code": brand_code,
        "last_completed_brand_url": canonical_url(brand_url),
        "cars_count_at_completion": cars_count,
        "requests_count_at_completion": requests_count,
        "updated_at": base.now(),
    }
    RESUME_STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_existing_catalog() -> tuple[list[dict], list[dict], set[str], set[str]]:
    if not base.OUT.exists():
        return [], [], set(), set()

    try:
        payload = json.loads(base.OUT.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WARN existing catalog not readable, starting from empty: {exc}")
        return [], [], set(), set()

    cars = payload.get("cars") or []
    errors = payload.get("errors") or []
    if not isinstance(cars, list):
        cars = []
    if not isinstance(errors, list):
        errors = []

    seen_urls: set[str] = set()
    seen_ids: set[str] = set()
    clean_cars: list[dict] = []

    for car in cars:
        if not isinstance(car, dict):
            continue
        clean_cars.append(car)
        if car.get("id"):
            seen_ids.add(str(car["id"]))
        for key in ("motornet_detail_url", "source_url"):
            url = canonical_url(car.get(key))
            if url:
                seen_urls.add(url)
                seen_ids.add(base.make_id(url))

    print(f"RESUME existing catalog: cars={len(clean_cars)} seen_urls={len(seen_urls)}")
    return clean_cars, errors, seen_urls, seen_ids


def already_imported(url: str, seen_urls: set[str], seen_ids: set[str]) -> bool:
    url = canonical_url(url)
    return bool(url and (url in seen_urls or base.make_id(url) in seen_ids))


def mark_seen(car: dict, seen_urls: set[str], seen_ids: set[str]) -> None:
    if car.get("id"):
        seen_ids.add(str(car["id"]))
    for key in ("motornet_detail_url", "source_url"):
        url = canonical_url(car.get(key))
        if url:
            seen_urls.add(url)
            seen_ids.add(base.make_id(url))


def write_payload(cars: list[dict], errors: list[dict], args, requests_count: int, images_downloaded: int) -> None:
    base.write_payload(base.build_payload(cars, errors, args, requests_count, images_downloaded))


def robust_git_checkpoint(count: int, image_dir: Path) -> None:
    subprocess.run(["git", "config", "user.name", "github-actions"], check=False)
    subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=False)
    add_paths = [str(base.OUT), str(image_dir)]
    if RESUME_STATE.exists():
        add_paths.append(str(RESUME_STATE))
    subprocess.run(["git", "add", *add_paths], check=False)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        return

    committed = subprocess.run(["git", "commit", "-m", f"Checkpoint Motornet catalogue ({count} cars)"], check=False)
    if committed.returncode != 0:
        return

    for attempt in range(1, 4):
        print(f"Checkpoint push attempt {attempt}")
        pushed = subprocess.run(["bash", "-lc", "git pull --rebase --autostash origin main && git push"], check=False)
        if pushed.returncode == 0:
            print("Checkpoint pushed.")
            return
        subprocess.run(["git", "rebase", "--abort"], check=False)
        time.sleep(5)

    print("WARN checkpoint commit created but push failed after retries")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Maximum total cars in data/cars_motornet.json. Use 0 for no total limit.")
    parser.add_argument("--delay", type=float, default=8)
    parser.add_argument("--timeout", type=int, default=45000)
    parser.add_argument("--brand-codes", default="", help="CSV brand codes for test runs, e.g. ABA,ROL")
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--checkpoint-commit", default="true")
    parser.add_argument("--download-images", default="true")
    parser.add_argument("--image-dir", default="assets/cars/motornet")
    parser.add_argument("--max-image-mb", type=float, default=6)
    parser.add_argument("--resume-from-last-brand", default="true", help="Skip whole brand pages before the last imported brand when brand_codes is empty.")
    parser.add_argument("--resume-from-completed-brand", default="true", help="Skip whole brand pages through the last completed brand saved in data/cars_motornet_resume_state.json.")
    parser.add_argument("--resume-after-last-imported-brand", default="false", help="Aggressive resume: skip the last imported brand too. Use only if that brand is known complete.")
    parser.add_argument("--checkpoint-completed-brand", default="true", help="Commit resume state after each completed brand, even if no new cars were imported.")
    args = parser.parse_args()

    args.checkpoint_commit = bool_arg(args.checkpoint_commit)
    args.download_images = bool_arg(args.download_images)
    args.resume_from_last_brand = bool_arg(args.resume_from_last_brand)
    args.resume_from_completed_brand = bool_arg(args.resume_from_completed_brand)
    args.resume_after_last_imported_brand = bool_arg(args.resume_after_last_imported_brand)
    args.checkpoint_completed_brand = bool_arg(args.checkpoint_completed_brand)
    image_dir = Path(args.image_dir)
    max_image_bytes = int(args.max_image_mb * 1024 * 1024)

    cars, errors, seen_urls, seen_ids = load_existing_catalog()
    resume_state = load_resume_state()
    initial_count = len(cars)
    last_checkpoint = initial_count
    explicit_brand_run = bool(args.brand_codes.strip())

    if args.limit > 0 and len(cars) >= args.limit:
        print(f"Existing catalog already has {len(cars)} cars, limit={args.limit}. Nothing to import.")
        write_payload(cars, errors, args, 0, 0)
        return

    robots = urllib.robotparser.RobotFileParser()
    robots.set_url(f"{base.BASE}/robots.txt")
    try:
        robots.read()
    except Exception as exc:
        print("WARN robots non leggibile:", exc)

    image_session = requests.Session()
    image_session.headers.update({"User-Agent": base.UA})

    requests_count = 0
    images_downloaded = 0
    skipped_existing = 0
    skipped_brand_pages = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=base.UA, locale="it-IT")
        page = context.new_page()

        if args.brand_codes.strip():
            brand_urls = [f"{base.BASE}/auto/scheda-modello/{code.strip().upper()}" for code in args.brand_codes.split(",") if code.strip()]
        else:
            print("LIST", base.LIST_URL)
            if base.can_fetch(robots, base.LIST_URL):
                page.goto(base.LIST_URL, wait_until="domcontentloaded", timeout=args.timeout)
                page.wait_for_timeout(2500)
                requests_count += 1
                brand_urls = base.discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/[A-Z0-9]{2,4}$")
                if not brand_urls:
                    print("  automatic brand discovery returned 0 links; using known brand code fallback")
                    brand_urls = [f"{base.BASE}/auto/scheda-modello/{code}" for code in extended_brand_codes()]
            else:
                brand_urls = []
                errors.append({"url": base.LIST_URL, "error": "blocked_by_robots"})

        print("brand links:", len(brand_urls))
        brand_codes_in_run = {base.brand_code_from_url(url) for url in brand_urls}
        brand_codes_in_run = {code for code in brand_codes_in_run if code}
        brand_order = {base.brand_code_from_url(url): i for i, url in enumerate(brand_urls) if base.brand_code_from_url(url)}

        last_brand_code = last_imported_brand_code(cars, brand_codes_in_run) if not explicit_brand_run else None
        completed_brand_raw = base.clean(resume_state.get("last_completed_brand_code")).upper() if resume_state else ""
        completed_brand_code = None
        if args.resume_from_completed_brand and not explicit_brand_run:
            completed_brand_code = normalize_resume_brand_code(completed_brand_raw, brand_codes_in_run)
            if completed_brand_raw and completed_brand_code and completed_brand_code != completed_brand_raw:
                print(f"RESUME normalized completed brand state {completed_brand_raw} -> {completed_brand_code}")

        if last_brand_code:
            print(f"RESUME last imported brand resolved: {last_brand_code}")

        resume_after_brand_code = None
        resume_at_brand_code = None

        completed_idx = brand_order.get(completed_brand_code) if completed_brand_code else None
        last_idx = brand_order.get(last_brand_code) if last_brand_code else None

        # Use completed-brand state only if it is not behind the last imported brand.
        # If state says AUD but the JSON already contains SPO, the completed state is stale
        # and would make the importer replay hundreds of existing links.
        if completed_brand_code and completed_brand_code in brand_codes_in_run and (last_idx is None or completed_idx is None or completed_idx >= last_idx):
            resume_after_brand_code = completed_brand_code
            print(f"RESUME completed-brand skip enabled. Starting after completed brand: {completed_brand_code}")
        elif completed_brand_code and completed_brand_code in brand_codes_in_run and last_brand_code and last_brand_code in brand_codes_in_run:
            print(f"RESUME completed-brand state {completed_brand_code} is behind last imported brand {last_brand_code}; ignoring stale state")
        elif completed_brand_raw:
            print(f"WARN completed resume brand {completed_brand_raw} not found in this run; ignoring state")

        if not resume_after_brand_code and args.resume_after_last_imported_brand and last_brand_code and last_brand_code in brand_codes_in_run:
            resume_after_brand_code = last_brand_code
            print(f"RESUME aggressive skip enabled. Starting after last imported brand: {last_brand_code}")
        elif not resume_after_brand_code and args.resume_from_last_brand and last_brand_code and last_brand_code in brand_codes_in_run:
            resume_at_brand_code = last_brand_code
            print(f"RESUME fast brand skip enabled. Starting at last imported brand: {last_brand_code}")
        elif last_brand_code and last_brand_code not in brand_codes_in_run:
            print(f"WARN resume brand {last_brand_code} not found in this run; falling back to URL-level skip")

        reached_after_resume = not bool(resume_after_brand_code)
        reached_at_resume = not bool(resume_at_brand_code)
        run_seen_details: set[str] = set()

        for brand_url in brand_urls:
            brand_code = base.brand_code_from_url(brand_url)
            if not reached_after_resume:
                skipped_brand_pages += 1
                if brand_code == resume_after_brand_code:
                    reached_after_resume = True
                    print("SKIP BRAND completed/aggressive resume", brand_code, brand_url)
                else:
                    print("SKIP BRAND before completed/aggressive resume", brand_code, brand_url)
                continue

            if not reached_at_resume:
                if brand_code == resume_at_brand_code:
                    reached_at_resume = True
                    print("RESUME reached brand", brand_code, brand_url)
                else:
                    skipped_brand_pages += 1
                    print("SKIP BRAND before resume", brand_code, brand_url)
                    continue

            if args.limit > 0 and len(cars) >= args.limit:
                break
            if not base.can_fetch(robots, brand_url):
                errors.append({"url": brand_url, "error": "blocked_by_robots"})
                continue

            try:
                time.sleep(args.delay)
                print("BRAND", brand_url)
                page.goto(brand_url, wait_until="domcontentloaded", timeout=args.timeout)
                page.wait_for_timeout(2500)
                requests_count += 1
                brand_name = base.brand_name_from_page(page, brand_url)

                detail_links = base.discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/modello/\d+/allestimento/[^/]+$")
                model_links = base.discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/modello/\d+$")
                if model_links:
                    expanded, requests_count = base.expand_model_links_to_details(page, model_links, args, robots, errors, requests_count)
                    for detail_url in expanded:
                        if detail_url not in detail_links:
                            detail_links.append(detail_url)

                print("  detail links:", len(detail_links))
            except Exception as exc:
                errors.append({"url": brand_url, "error": str(exc)})
                continue

            for detail_url in detail_links:
                detail_url = canonical_url(detail_url)
                if args.limit > 0 and len(cars) >= args.limit:
                    break
                if detail_url in run_seen_details:
                    continue
                run_seen_details.add(detail_url)

                if already_imported(detail_url, seen_urls, seen_ids):
                    skipped_existing += 1
                    print("  = skip existing", detail_url)
                    continue
                if not base.can_fetch(robots, detail_url):
                    errors.append({"url": detail_url, "error": "blocked_by_robots"})
                    continue

                try:
                    time.sleep(args.delay)
                    page.goto(detail_url, wait_until="domcontentloaded", timeout=args.timeout)
                    try:
                        page.wait_for_selector("text=Scheda tecnica", timeout=8000)
                    except PlaywrightTimeoutError:
                        page.wait_for_timeout(2000)
                    requests_count += 1

                    car = base.parse_detail(page, detail_url, brand_name)
                    if not car:
                        continue
                    if already_imported(car.get("motornet_detail_url") or car.get("source_url") or detail_url, seen_urls, seen_ids):
                        skipped_existing += 1
                        print("  = skip existing after parse", detail_url)
                        continue

                    if args.download_images and car.get("image_source_url"):
                        try:
                            time.sleep(max(1, args.delay / 2))
                            image_data = base.download_image(image_session, car["image_source_url"], car["id"], image_dir, int(args.timeout / 1000), max_image_bytes)
                            if image_data:
                                car.update(image_data)
                                images_downloaded += 1
                        except Exception as exc:
                            car["image_error"] = str(exc)
                            errors.append({"url": car.get("image_source_url"), "error": f"image: {exc}"})

                    cars.append(car)
                    mark_seen(car, seen_urls, seen_ids)
                    print(f"  + {car.get('brand')} {car.get('model')} [{car.get('fuel')}] price={car.get('price_eur')} kwh100={car.get('consumption_kwh_100km')} l100={car.get('consumption_l_100km')}")

                    new_since_start = len(cars) - initial_count
                    if args.checkpoint_commit and args.checkpoint_every > 0 and new_since_start > 0 and new_since_start % args.checkpoint_every == 0 and len(cars) != last_checkpoint:
                        write_payload(cars, errors, args, requests_count, images_downloaded)
                        robust_git_checkpoint(len(cars), image_dir)
                        last_checkpoint = len(cars)

                except Exception as exc:
                    errors.append({"url": detail_url, "error": str(exc)})

            if brand_code:
                write_resume_state(brand_code, brand_url, len(cars), requests_count)
                print("RESUME completed brand", brand_code, brand_url)
                if args.checkpoint_commit and args.checkpoint_completed_brand:
                    robust_git_checkpoint(len(cars), image_dir)

        context.close()
        browser.close()

    write_payload(cars, errors, args, requests_count, images_downloaded)
    print(
        "Done cars=", len(cars),
        "new=", len(cars) - initial_count,
        "skipped_existing=", skipped_existing,
        "skipped_brand_pages=", skipped_brand_pages,
        "errors=", len(errors),
        "requests=", requests_count,
        "images_downloaded=", images_downloaded,
        "status=", "ok" if cars else "empty",
    )


if __name__ == "__main__":
    main()
