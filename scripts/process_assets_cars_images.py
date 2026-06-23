#!/usr/bin/env python3
from pathlib import Path
import argparse
import sys

from PIL import Image, ImageOps
import rembg
from rembg import new_session

EXT = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


def parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_limit(value):
    raw = "0" if value is None else str(value).strip()
    if raw == "":
        return 0
    try:
        limit = int(raw)
    except ValueError:
        raise SystemExit(f"invalid --limit value: {value!r}. Use an integer, where 0 = all.")
    if limit < 0:
        raise SystemExit(f"invalid --limit value: {value!r}. Use 0 or a positive integer.")
    return limit


def im(path):
    with Image.open(path) as img:
        return ImageOps.exif_transpose(img).convert("RGBA")


def fit(img, width, height):
    scale = min(width / img.width, height / img.height)
    size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    return img.resize(size, Image.Resampling.LANCZOS)


def trim(img, pad=20):
    box = img.getchannel("A").getbbox()
    if not box:
        return img
    return img.crop((
        max(0, box[0] - pad),
        max(0, box[1] - pad),
        min(img.width, box[2] + pad),
        min(img.height, box[3] + pad),
    ))


def resize_max_side(img, max_side):
    if not max_side or max_side <= 0:
        return img
    width, height = img.size
    longest = max(width, height)
    if longest <= max_side:
        return img
    scale = max_side / float(longest)
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return img.resize(size, Image.Resampling.LANCZOS)


def save_webp(img, path, quality, max_side):
    final = resize_max_side(img.convert("RGB"), max_side)
    final.save(path, "WEBP", quality=quality, method=6)


def resolve_logo_path(raw_path):
    path = Path(raw_path)
    if path.exists():
        return path.resolve()

    candidates = [
        path.with_suffix(".png"),
        path.with_suffix(".jpg"),
        path.with_suffix(".jpeg"),
        Path("assets/logopippo.png"),
        Path("assets/logopippo.jpg"),
        Path("assets/logopippo.jpeg"),
    ]
    for candidate in candidates:
        if candidate.exists():
            print(f"Logo not found at {path}; using {candidate} instead.")
            return candidate.resolve()

    tried = ", ".join(str(p) for p in [path, *candidates])
    raise SystemExit(f"missing logo file. Tried: {tried}")


def is_inside(child, parent):
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def source_files(src_dir_abs, out_dir_abs, recursive):
    iterator = src_dir_abs.rglob("*") if recursive else src_dir_abs.iterdir()
    files = []
    for path in sorted(iterator):
        if not path.is_file():
            continue
        if path.suffix.lower() not in EXT:
            continue
        path_abs = path.resolve()
        if is_inside(path_abs, out_dir_abs):
            continue
        files.append(path_abs)
    return files


parser = argparse.ArgumentParser()
parser.add_argument("--input-dir", default="assets/cars")
parser.add_argument("--output-dir", default="assets/cars_processed")
parser.add_argument("--background", default="assets/sfondopippo.jpg")
parser.add_argument("--logo", default="assets/logopippo.png")
parser.add_argument("--force", default="false")
parser.add_argument("--recursive", default="false", help="Process subfolders too.")
parser.add_argument("--limit", default="0", help="Maximum number of source images to inspect/process. 0 = all.")
parser.add_argument("--logo-position", choices=["top-right", "top-left", "bottom-right", "bottom-left"], default="top-right")
parser.add_argument("--final-quality", type=int, default=80, help="WEBP quality for final composited images.")
parser.add_argument("--final-max-side", type=int, default=1600, help="Resize final images so the longest side is at most this many pixels. 0 disables resizing.")
parser.add_argument("--mirror", default="true", help="Mirror the car horizontally before compositing.")
args = parser.parse_args()

force = parse_bool(args.force)
mirror = parse_bool(args.mirror)
recursive = parse_bool(args.recursive)
limit = parse_limit(args.limit)

if not 1 <= args.final_quality <= 100:
    raise SystemExit(f"invalid --final-quality value: {args.final_quality}. Use an integer between 1 and 100.")
if args.final_max_side < 0:
    raise SystemExit(f"invalid --final-max-side value: {args.final_max_side}. Use 0 or a positive integer.")

src_dir = Path(args.input_dir)
out_dir = Path(args.output_dir)
background_path = Path(args.background)
logo_path = resolve_logo_path(args.logo)

if not src_dir.exists():
    raise SystemExit(f"missing input dir: {src_dir}")
if not background_path.exists():
    raise SystemExit(f"missing background file: {background_path}")

src_dir_abs = src_dir.resolve()
out_dir_abs = out_dir.resolve()
final_dir = out_dir_abs / "final"

all_files = source_files(src_dir_abs, out_dir_abs, recursive)
files = all_files[:limit] if limit > 0 else all_files

print(f"input_dir={src_dir}")
print(f"input_dir_abs={src_dir_abs}")
print(f"output_dir={out_dir}")
print(f"output_dir_abs={out_dir_abs}")
print(f"recursive={recursive}")
print(f"force={force}")
print(f"mirror={mirror}")
print(f"limit={limit} (0 means all)")
print(f"final_format=webp")
print(f"final_quality={args.final_quality}")
print(f"final_max_side={args.final_max_side}")
print(f"source_images_found={len(all_files)}")
print(f"source_images_selected={len(files)}")

if not files:
    print("no images")
    raise SystemExit(0)

background = im(background_path.resolve())
logo = im(logo_path)
session = new_session("u2net")
done = skip = fail = inspected = 0

for index, src in enumerate(files, 1):
    if limit > 0 and inspected >= limit:
        print(f"limit reached: inspected={inspected}, limit={limit}")
        break

    inspected += 1
    rel = src.relative_to(src_dir_abs)
    final_path = final_dir / rel.with_suffix(".webp")
    final_path.parent.mkdir(parents=True, exist_ok=True)

    if not force and final_path.exists():
        skip += 1
        print(f"[{index}/{len(files)}] skip {src}")
        continue

    try:
        car_cutout = getattr(rembg, "re" + "move")(im(src), session=session).convert("RGBA")
        if mirror:
            car_cutout = ImageOps.mirror(car_cutout)
        car_cutout = trim(car_cutout, 20)

        canvas = background.copy().convert("RGBA")
        canvas_w, canvas_h = canvas.size
        car = fit(car_cutout, int(canvas_w * 0.88), int(canvas_h * 0.70))
        canvas.alpha_composite(car, ((canvas_w - car.width) // 2, max(0, canvas_h - car.height - int(canvas_h * 0.07))))

        mark = fit(logo, int(canvas_w * 0.18), int(canvas_h * 0.16))
        margin = int(canvas_w * 0.035)
        pos = {
            "top-right": (canvas_w - mark.width - margin, margin),
            "top-left": (margin, margin),
            "bottom-right": (canvas_w - mark.width - margin, canvas_h - mark.height - margin),
            "bottom-left": (margin, canvas_h - mark.height - margin),
        }[args.logo_position]
        canvas.alpha_composite(mark, pos)
        save_webp(canvas, final_path, quality=args.final_quality, max_side=args.final_max_side)

        done += 1
        print(f"[{index}/{len(files)}] ok {final_path}")
    except Exception as exc:
        fail += 1
        print(f"[{index}/{len(files)}] ERROR {src}: {exc}", file=sys.stderr)

print(f"inspected={inspected} done={done} skipped={skip} failed={fail}")
raise SystemExit(1 if fail else 0)
