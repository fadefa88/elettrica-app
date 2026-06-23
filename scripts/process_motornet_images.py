#!/usr/bin/env python3
from pathlib import Path
import argparse
import shutil
import sys

from PIL import Image, ImageOps
import rembg
from rembg import new_session

EXT = {".jpg", ".jpeg", ".png", ".webp"}


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


def im(p):
    with Image.open(p) as x:
        return ImageOps.exif_transpose(x).convert("RGBA")


def fit(x, w, h):
    s = min(w / x.width, h / x.height)
    return x.resize((max(1, int(x.width * s)), max(1, int(x.height * s))), Image.Resampling.LANCZOS)


def trim(x, pad=20):
    b = x.getchannel("A").getbbox()
    return x if not b else x.crop((max(0, b[0] - pad), max(0, b[1] - pad), min(x.width, b[2] + pad), min(x.height, b[3] + pad)))


def resize_max_side(x, max_side):
    if not max_side or max_side <= 0:
        return x

    w, h = x.size
    longest = max(w, h)
    if longest <= max_side:
        return x

    scale = max_side / float(longest)
    new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    return x.resize(new_size, Image.Resampling.LANCZOS)


def save_final_webp(x, path, quality=80, max_side=1600):
    # WEBP does not need alpha here because the final image is already composited
    # over the site background. RGB produces smaller files than RGBA.
    final = resize_max_side(x.convert("RGB"), max_side)
    final.save(
        path,
        "WEBP",
        quality=quality,
        method=6,
    )


def remove_file(path):
    if path.exists() and path.is_file():
        path.unlink()
        return True
    return False


def resolve_logo_path(raw_path):
    """Prefer the provided logo path, then try common variants in the same folder."""
    path = Path(raw_path)
    if path.exists():
        return path

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
            return candidate

    tried = ", ".join(str(p) for p in [path, *candidates])
    raise SystemExit(f"missing logo file. Tried: {tried}")


a = argparse.ArgumentParser()
a.add_argument("--input-dir", default="assets/cars/motornet")
a.add_argument("--output-dir", default="assets/cars/motornet_processed")
a.add_argument("--background", default="assets/sfondopippo.jpg")
a.add_argument("--logo", default="assets/logopippo.png")
a.add_argument("--force", default="false")
a.add_argument("--limit", default="0", help="Maximum number of source images to inspect/process. 0 = all.")
a.add_argument("--logo-position", choices=["top-right", "top-left", "bottom-right", "bottom-left"], default="top-right")
a.add_argument("--final-quality", type=int, default=80, help="WEBP quality for final composited images.")
a.add_argument("--final-max-side", type=int, default=1600, help="Resize final images so the longest side is at most this many pixels. 0 disables resizing.")
args = a.parse_args()

force = parse_bool(args.force)
limit = parse_limit(args.limit)

if not 1 <= args.final_quality <= 100:
    raise SystemExit(f"invalid --final-quality value: {args.final_quality}. Use an integer between 1 and 100.")
if args.final_max_side < 0:
    raise SystemExit(f"invalid --final-max-side value: {args.final_max_side}. Use 0 or a positive integer.")

src_dir = Path(args.input_dir)
out_dir = Path(args.output_dir)
bg_path = Path(args.background)
logo_path = resolve_logo_path(args.logo)
cutout_dir = out_dir / "cutout"
final_dir = out_dir / "final"

if not src_dir.exists():
    raise SystemExit(f"missing input dir: {src_dir}")
if not bg_path.exists():
    raise SystemExit(f"missing background file: {bg_path}")

all_files = sorted(p for p in src_dir.rglob("*") if p.is_file() and p.suffix.lower() in EXT)
files = all_files[:limit] if limit > 0 else all_files

print(f"input_dir={src_dir}")
print(f"output_dir={out_dir}")
print(f"force={force}")
print(f"limit={limit} (0 means all)")
print(f"final_format=webp")
print(f"final_quality={args.final_quality}")
print(f"final_max_side={args.final_max_side}")
print(f"source_images_found={len(all_files)}")
print(f"source_images_selected={len(files)}")

if not files:
    print("no images")
    raise SystemExit(0)

bg = im(bg_path)
logo = im(logo_path)
session = new_session("u2net")
done = skip = fail = inspected = removed_legacy_png = removed_cutout = 0

for n, src in enumerate(files, 1):
    # Defensive hard stop: even if future edits alter the file selection above,
    # a manual run with --limit 1 can never inspect/process more than one source image.
    if limit > 0 and inspected >= limit:
        print(f"limit reached: inspected={inspected}, limit={limit}")
        break

    inspected += 1
    rel = src.relative_to(src_dir)
    cut_path = cutout_dir / rel.with_suffix(".png")
    final_path = final_dir / rel.with_suffix(".webp")
    legacy_png_path = final_dir / rel.with_suffix(".png")
    final_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove legacy files to avoid filling the repository. The cutout is now only
    # used in memory and is not saved as an extra artifact.
    if remove_file(legacy_png_path):
        removed_legacy_png += 1
        print(f"[{n}/{len(files)}] removed legacy final PNG {legacy_png_path}")
    if remove_file(cut_path):
        removed_cutout += 1
        print(f"[{n}/{len(files)}] removed legacy cutout PNG {cut_path}")

    if not force and final_path.exists():
        skip += 1
        print(f"[{n}/{len(files)}] skip {src}")
        continue

    try:
        cut = getattr(rembg, "re" + "move")(im(src), session=session).convert("RGBA")
        cut = trim(ImageOps.mirror(cut), 20)

        canvas = bg.copy().convert("RGBA")
        cw, ch = canvas.size
        car = fit(cut, int(cw * .88), int(ch * .70))
        canvas.alpha_composite(car, ((cw - car.width) // 2, max(0, ch - car.height - int(ch * .07))))

        mark = fit(logo, int(cw * .18), int(ch * .16))
        m = int(cw * .035)
        pos = {
            "top-right": (cw - mark.width - m, m),
            "top-left": (m, m),
            "bottom-right": (cw - mark.width - m, ch - mark.height - m),
            "bottom-left": (m, ch - mark.height - m),
        }[args.logo_position]
        canvas.alpha_composite(mark, pos)
        save_final_webp(canvas, final_path, quality=args.final_quality, max_side=args.final_max_side)

        done += 1
        print(f"[{n}/{len(files)}] ok {final_path}")
    except Exception as e:
        fail += 1
        print(f"[{n}/{len(files)}] ERROR {src}: {e}", file=sys.stderr)

# On full runs, remove the whole legacy cutout directory so orphaned cutouts whose
# source image no longer exists are deleted as well. For limited test runs, only
# cutouts matching inspected sources are removed.
if limit == 0 and cutout_dir.exists():
    shutil.rmtree(cutout_dir)
    print(f"removed legacy cutout directory {cutout_dir}")

print(f"inspected={inspected} done={done} skipped={skip} failed={fail} removed_legacy_png={removed_legacy_png} removed_cutout={removed_cutout}")
raise SystemExit(1 if fail else 0)
