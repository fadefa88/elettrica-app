#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


def clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def safe_image_filename(version: str) -> str:
    """Build the Motornet local WebP filename from the vehicle version text.

    Example:
    Alfa Romeo Stelvio 2.9 V6 520cv Quadrifoglio Q4 AT8
    -> Alfa_Romeo_Stelvio_2.9_V6_520cv_Quadrifoglio_Q4_AT8.webp
    """
    text = clean(version)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    # Keep letters, numbers, dots, dashes and underscores. Replace path separators.
    text = text.replace("/", " ").replace("\\", " ")
    text = re.sub(r"[^A-Za-z0-9._ -]+", "", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("._-")

    if not text:
        text = "motornet_image"

    return f"{text}.webp"


def normalize_catalog(path: Path, image_prefix: str, require_existing: bool) -> tuple[int, int, int]:
    payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    cars = payload.get("cars")
    if not isinstance(cars, list):
        raise SystemExit("Catalog JSON must be an object with cars[]")

    image_prefix = image_prefix.strip().strip("/")
    updated = 0
    skipped_missing_version = 0
    skipped_missing_file = 0

    for car in cars:
        if not isinstance(car, dict):
            continue

        version = clean(car.get("version") or car.get("powertrain") or car.get("model"))
        if not version:
            skipped_missing_version += 1
            continue

        new_url = f"{image_prefix}/{safe_image_filename(version)}"
        if require_existing and not Path(new_url).exists():
            skipped_missing_file += 1
            continue

        changed = False
        if car.get("image_url") != new_url:
            car["image_url"] = new_url
            changed = True

        # Full/non-slim Motornet payloads may still contain image_local_path.
        # Keep it aligned when present, but do not create or delete image files.
        if "image_local_path" in car and car.get("image_local_path") != new_url:
            car["image_local_path"] = new_url
            changed = True

        if changed:
            updated += 1

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return updated, skipped_missing_version, skipped_missing_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize Motornet image_url values using version-based WebP filenames.")
    parser.add_argument("--catalog", default="data/cars_motornet.json")
    parser.add_argument("--image-prefix", default="assets/cars/motornet")
    parser.add_argument(
        "--require-existing",
        action="store_true",
        help="Only update records whose target WebP file already exists. By default this only updates JSON text.",
    )
    args = parser.parse_args()

    catalog = Path(args.catalog)
    if not catalog.exists():
        raise SystemExit(f"Catalog not found: {catalog}")

    updated, skipped_missing_version, skipped_missing_file = normalize_catalog(
        catalog,
        args.image_prefix,
        args.require_existing,
    )

    print(f"Motornet image URLs normalized: {updated}")
    print(f"Skipped without version: {skipped_missing_version}")
    if args.require_existing:
        print(f"Skipped because target WebP file does not exist: {skipped_missing_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
