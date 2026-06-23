#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from normalize_motornet_image_urls import safe_image_filename


def clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def load_rename_map(catalog_path: Path) -> dict[str, str]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8") or "{}")
    cars = payload.get("cars")
    if not isinstance(cars, list):
        raise SystemExit("Catalog JSON must be an object with cars[]")

    mapping: dict[str, str] = {}
    used_targets: dict[str, str] = {}

    for car in cars:
        if not isinstance(car, dict):
            continue

        car_id = clean(car.get("id"))
        version = clean(car.get("version") or car.get("powertrain") or car.get("model"))
        if not car_id or not version:
            continue

        target = safe_image_filename(version)

        # Avoid overwriting in the rare case of duplicated version names.
        previous_id = used_targets.get(target)
        if previous_id and previous_id != car_id:
            stem = Path(target).stem
            target = f"{stem}__{car_id}.webp"

        used_targets[target] = car_id
        mapping[f"{car_id}.webp"] = target

    return mapping


def rename_processed_images(catalog_path: Path, image_dir: Path, dry_run: bool) -> tuple[int, int, int, int]:
    if not catalog_path.exists():
        raise SystemExit(f"Catalog not found: {catalog_path}")
    if not image_dir.exists():
        raise SystemExit(f"Image directory not found: {image_dir}")

    mapping = load_rename_map(catalog_path)
    renamed = 0
    already_ok = 0
    unmatched = 0
    collisions = 0

    for source in sorted(image_dir.glob("motornet_*.webp")):
        target_name = mapping.get(source.name)
        if not target_name:
            unmatched += 1
            print(f"UNMATCHED {source.name}")
            continue

        target = image_dir / target_name
        if source.resolve() == target.resolve():
            already_ok += 1
            continue

        if target.exists():
            # Keep both files. Do not overwrite an already normalized image.
            stem = target.stem
            target = image_dir / f"{stem}__{source.stem}.webp"
            collisions += 1

        print(f"RENAME {source.name} -> {target.name}")
        if not dry_run:
            source.rename(target)
        renamed += 1

    return renamed, already_ok, unmatched, collisions


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename Motornet processed final WebP images in place using catalog version names.")
    parser.add_argument("--catalog", default="data/cars_motornet.json")
    parser.add_argument("--image-dir", default="assets/cars/motornet_processed/final")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    renamed, already_ok, unmatched, collisions = rename_processed_images(
        Path(args.catalog),
        Path(args.image_dir),
        args.dry_run,
    )

    print(f"Renamed: {renamed}")
    print(f"Already ok: {already_ok}")
    print(f"Unmatched id-based files: {unmatched}")
    print(f"Collisions handled: {collisions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
