#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import time
import urllib.parse
import urllib.robotparser
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE = "https://www.motornet.it"
LIST_URL = f"{BASE}/auto/listini-del-nuovo"
OUT = Path("data/cars_motornet.json")
UA = "ElettricaMotornetImporter/1.0 (+https://github.com/fadefa88/elettrica)"
MODEL_IMAGE_PATH_MARKER = "/img/modelli/auto/"
IMAGE_ALLOWED_HOST = "motornet.it"

KNOWN_BRAND_CODES = [
    "ABA", "ALF", "AST", "AUD", "BMW", "BYD", "CAD", "CHE", "CHC", "CIR",
    "CIT", "CUP", "DAC", "DOD", "DR", "DS", "EVO", "FER", "FIA", "FOR",
    "GMC", "HON", "HYU", "INE", "JAG", "JEE", "KIA", "LAN", "LND", "LEX",
    "LOT", "MAS", "MAZ", "MCL", "MER", "MG", "MIL", "MIN", "MIT", "NIS",
    "OPE", "PEU", "POL", "POR", "REN", "ROL", "SEA", "SKO", "SMA", "SUB",
    "SUZ", "TES", "TOY", "VLV", "VLK", "VOL"
]

BRAND_NAME_BY_CODE = {
    "ABA": "Abarth",
    "ALF": "Alfa Romeo",
    "AST": "Aston Martin",
    "AUD": "Audi",
    "BMW": "BMW",
    "BYD": "BYD",
    "CAD": "Cadillac",
    "CHE": "Chevrolet",
    "CHC": "Chrysler",
    "CIR": "Citroen",
    "CIT": "Citroen",
    "CUP": "Cupra",
    "DAC": "Dacia",
    "DOD": "Dodge",
    "DR": "DR",
    "DS": "DS",
    "EVO": "EVO",
    "FER": "Ferrari",
    "FIA": "Fiat",
    "FOR": "Ford",
    "GMC": "GMC",
    "HON": "Honda",
    "HYU": "Hyundai",
    "INE": "INEOS",
    "JAG": "Jaguar",
    "JEE": "Jeep",
    "KIA": "Kia",
    "LAN": "Lancia",
    "LND": "Land Rover",
    "LEX": "Lexus",
    "LOT": "Lotus",
    "MAS": "Maserati",
    "MAZ": "Mazda",
    "MCL": "McLaren",
    "MER": "Mercedes-Benz",
    "MG": "MG",
    "MIL": "Militem",
    "MIN": "Mini",
    "MIT": "Mitsubishi",
    "NIS": "Nissan",
    "OPE": "Opel",
    "PEU": "Peugeot",
    "POL": "Polestar",
    "POR": "Porsche",
    "REN": "Renault",
    "ROL": "Rolls-Royce",
    "SEA": "Seat",
    "SKO": "Skoda",
    "SMA": "Smart",
    "SUB": "Subaru",
    "SUZ": "Suzuki",
    "TES": "Tesla",
    "TOY": "Toyota",
    "VLV": "Volvo",
    "VLK": "Volkswagen",
    "VOL": "Volvo",
}

FUEL_CODE_BY_LABEL = {
    "elettrica": "E",
    "elettrica_idrogeno": "EH",
    "benzina": "B",
    "diesel": "D",
    "ibrida_benzina": "IB",
    "ibrida_diesel": "ID",
    "gpl": "G",
    "ibrida_gpl": "IG",
    "metano": "M",
    "ibrida_metano": "IM",
}

PRICE_LABEL_RE = re.compile(r"\bprezzo\s+(?:di\s+)?listino\b|\blistino\b", re.I)
MONEY_RE = re.compile(
    r"(?<![\w/])(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d{5,7}(?:,\d{1,2})?)\s*(?:€|eur)",
    re.I,
)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_decimal(value: object) -> float | None:
    text = clean(value).replace(".", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_int(value: object) -> int | None:
    number = parse_decimal(value)
    return int(round(number)) if number is not None else None


def parse_italian_money_to_int(text: object) -> int | None:
    """Parse a Motornet euro amount like '269.252,52 €' into 269253.

    Deliberately requires an explicit € / EUR marker. This prevents engine
    displacement, RPM, power, CO2 or consumption numbers from becoming prices.
    """
    match = MONEY_RE.search(clean(text).replace("\xa0", " "))
    if not match:
        return None

    raw = match.group(1)
    normalized = raw.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None

    # Conservative range for new-car Italian list prices.
    if amount < Decimal("7000") or amount > Decimal("3000000"):
        return None

    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_price(text: str, pairs: dict[str, str] | None = None) -> int | None:
    """Extract only the value tied to 'PREZZO DI LISTINO'.

    There is intentionally no generic numeric fallback. Returning None is safer
    than returning numbers such as 6000 RPM or 5204 cc.
    """
    pairs = pairs or {}

    for key, value in pairs.items():
        key_text = clean(key)
        value_text = clean(value)
        if PRICE_LABEL_RE.search(key_text):
            price = parse_italian_money_to_int(f"{key_text} {value_text}")
            if price:
                return price

    body = clean(text).replace("\xa0", " ")
    anchored = re.search(
        r"(?:prezzo\s+di\s+listino|prezzo\s+listino|listino).{0,220}?"
        r"(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d{5,7}(?:,\d{1,2})?)\s*(?:€|eur)",
        body,
        flags=re.I | re.S,
    )
    if anchored:
        price = parse_italian_money_to_int(anchored.group(0))
        if price:
            return price

    # Handles layouts where the amount is just before the label.
    reverse_anchored = re.search(
        r"(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d{5,7}(?:,\d{1,2})?)\s*(?:€|eur)"
        r".{0,120}?(?:prezzo\s+di\s+listino|prezzo\s+listino|listino)",
        body,
        flags=re.I | re.S,
    )
    if reverse_anchored:
        price = parse_italian_money_to_int(reverse_anchored.group(0))
        if price:
            return price

    return None


def full_url(url: str) -> str:
    return urllib.parse.urljoin(BASE, str(url or "").split("#")[0])


def path_of(url: str) -> str:
    return urllib.parse.urlparse(full_url(url)).path


def can_fetch(robots: urllib.robotparser.RobotFileParser, url: str) -> bool:
    try:
        return robots.can_fetch(UA, url)
    except Exception:
        return True


def make_id(url: str) -> str:
    return "motornet_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:14]


def brand_code_from_url(url: str) -> str | None:
    path = urllib.parse.urlparse(full_url(url)).path.rstrip("/")
    code = path.split("/")[-1].upper()
    return code if re.fullmatch(r"[A-Z0-9]{2,4}", code) else None


def normalise_fuel(raw: str) -> tuple[str, str]:
    text = clean(raw).lower()
    if "idrogen" in text:
        fuel = "elettrica_idrogeno"
    elif "elettr" in text:
        fuel = "elettrica"
    elif "gpl" in text and ("ibrid" in text or "hybrid" in text):
        fuel = "ibrida_gpl"
    elif "metano" in text and ("ibrid" in text or "hybrid" in text):
        fuel = "ibrida_metano"
    elif "diesel" in text and ("ibrid" in text or "hybrid" in text):
        fuel = "ibrida_diesel"
    elif "benzina" in text and ("ibrid" in text or "hybrid" in text):
        fuel = "ibrida_benzina"
    elif "gpl" in text:
        fuel = "gpl"
    elif "metano" in text:
        fuel = "metano"
    elif "diesel" in text or "gasolio" in text:
        fuel = "diesel"
    elif "benzina" in text:
        fuel = "benzina"
    elif "ibrid" in text or "hybrid" in text:
        fuel = "ibrida_benzina"
    else:
        fuel = "benzina"
    return fuel, FUEL_CODE_BY_LABEL.get(fuel, "B")


def category_for_fuel(fuel: str) -> str:
    return "electric" if fuel in {"elettrica", "elettrica_idrogeno"} else "thermal"


def collect_raw_values(page) -> list[str]:
    try:
        values = page.evaluate("""
            () => {
              const out = [];
              document.querySelectorAll('a[href], option[value], [data-href], [data-url], [data-value], [href], [value]').forEach(el => {
                ['href', 'value', 'data-href', 'data-url', 'data-value'].forEach(attr => {
                  const value = el.getAttribute(attr);
                  if (value) out.push(value);
                });
              });
              document.querySelectorAll('option, li, button, a, [role="option"], [role="menuitem"]').forEach(el => {
                const text = (el.innerText || el.textContent || '').trim();
                if (text) out.push(text);
              });
              out.push(document.documentElement.innerHTML || '');
              return out;
            }
        """)
    except Exception:
        values = []
    return [str(v).strip() for v in values if str(v or "").strip()]


def links_from_values(values: list[str], pattern: str) -> list[str]:
    links: list[str] = []
    rx = re.compile(pattern, re.I)

    for value in values:
        if re.fullmatch(r"[A-Z0-9]{2,4}", value):
            url = f"{BASE}/auto/scheda-modello/{value}"
            if rx.search(path_of(url)) and url not in links:
                links.append(url)
            continue

        for match in re.findall(r"/auto/scheda-modello(?:/modello/\d+(?:/allestimento/[A-Za-z0-9_-]+)?|/[A-Z0-9]{2,4})", value):
            url = full_url(match)
            if rx.search(path_of(url)) and url not in links:
                links.append(url)

        for match in re.findall(r"https://www\.motornet\.it/auto/scheda-modello(?:/modello/\d+(?:/allestimento/[A-Za-z0-9_-]+)?|/[A-Z0-9]{2,4})", value):
            url = full_url(match)
            if rx.search(path_of(url)) and url not in links:
                links.append(url)

        url = full_url(value)
        if rx.search(path_of(url)) and url not in links:
            links.append(url)

    return links


def extract_links(page, pattern: str) -> list[str]:
    return links_from_values(collect_raw_values(page), pattern)


def open_possible_dropdowns(page) -> None:
    selectors = [
        "text=Seleziona il modello",
        "text=Seleziona modello",
        "text=Seleziona",
        "[role='combobox']",
        "[aria-haspopup='listbox']",
        "button:has-text('Seleziona')",
        "input[placeholder*='modello' i]",
        "div[class*='control']",
        "div[class*='select']",
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=2500, force=True)
                page.wait_for_timeout(900)
        except Exception:
            pass


def discover_links_after_clicking_menus(page, pattern: str) -> list[str]:
    links = extract_links(page, pattern)
    if links:
        return links

    open_possible_dropdowns(page)
    links = extract_links(page, pattern)
    if links:
        return links

    captured: list[str] = []
    current = page.url
    option_selector = "[role='option'], [id*='option'], li, button, a"

    try:
        count = min(page.locator(option_selector).count(), 80)
    except Exception:
        count = 0

    for index in range(count):
        try:
            open_possible_dropdowns(page)
            loc = page.locator(option_selector).nth(index)
            text = clean(loc.inner_text(timeout=1200))
            if not text or text.lower() in {"seleziona", "scheda tecnica", "accessori", "confronta"}:
                continue

            before = page.url
            loc.click(timeout=2500, force=True)
            page.wait_for_timeout(1800)
            after = page.url

            for url in [after] + extract_links(page, pattern):
                if re.search(pattern, path_of(url), re.I) and url not in captured:
                    captured.append(full_url(url))

            if after != before:
                page.goto(current, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1200)
        except Exception:
            try:
                page.goto(current, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1000)
            except Exception:
                pass

    return captured


def rendered_text(page) -> str:
    try:
        return clean(page.locator("body").inner_text(timeout=5000))
    except Exception:
        return clean(page.content())


def rendered_title(page) -> str:
    data = page.evaluate("""
        () => {
          const h = document.querySelector('h1,h2,h3');
          return { title: document.title || '', heading: h ? h.innerText : '' };
        }
    """)
    return clean(data.get("heading") or data.get("title"))


def table_pairs(page) -> dict[str, str]:
    rows = page.evaluate("""
        () => {
          const rows = [];
          document.querySelectorAll('tr').forEach(tr => {
            const cells = Array.from(tr.children).map(x => (x.innerText || '').trim()).filter(Boolean);
            if (cells.length) rows.push(cells);
          });
          return rows;
        }
    """)
    pairs = {}
    for cells in rows:
        if len(cells) >= 2:
            for i in range(0, len(cells) - 1, 2):
                key = clean(cells[i])
                val = clean(cells[i + 1])
                if key and val and key not in pairs:
                    pairs[key] = val

    if pairs:
        return pairs

    nodes = page.evaluate("""
        () => Array.from(document.querySelectorAll('td,th,span,div,p'))
          .map(x => (x.innerText || '').trim())
          .filter(Boolean)
          .slice(0, 2500)
    """)
    compact = []
    for node in nodes:
        node = clean(node)
        if node and len(node) < 120 and (not compact or compact[-1] != node):
            compact.append(node)

    label_words = ["Alimentazione", "kW", "Cv", "CV", "Prezzo", "Listino", "Consumo", "Autonomia", "CO2", "Emissioni", "Cilindrata", "Cambio", "Batteria"]
    for i, node in enumerate(compact[:-1]):
        if any(word.lower() in node.lower() for word in label_words):
            pairs.setdefault(node, compact[i + 1])
    return pairs


def pair_value(pairs: dict[str, str], *needles: str) -> str | None:
    for key, value in pairs.items():
        key_l = key.lower()
        if all(n.lower() in key_l for n in needles):
            return value
    return None


def parse_kw_cv(value: str | None) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    nums = re.findall(r"\d+(?:[,.]\d+)?", value)
    if not nums:
        return None, None
    first = float(nums[0].replace(",", "."))
    second = float(nums[1].replace(",", ".")) if len(nums) > 1 else None
    return first, second


def extract_image_url(page) -> str | None:
    candidates = page.evaluate("""
        () => {
          const out = [];
          document.querySelectorAll('img').forEach(img => {
            ['src','data-src','data-original','data-lazy'].forEach(a => {
              if (img.getAttribute(a)) out.push(img.getAttribute(a));
            });
            if (img.getAttribute('srcset')) {
              img.getAttribute('srcset').split(',').forEach(p => out.push(p.trim().split(' ')[0]));
            }
          });
          document.querySelectorAll('meta[property="og:image"],meta[name="twitter:image"]').forEach(m => {
            if (m.getAttribute('content')) out.push(m.getAttribute('content'));
          });
          return out;
        }
    """)
    scored = []
    for candidate in candidates:
        url = full_url(candidate)
        parsed = urllib.parse.urlparse(url)
        path = urllib.parse.unquote(parsed.path).lower()
        host = parsed.netloc.lower()
        if IMAGE_ALLOWED_HOST not in host:
            continue
        if MODEL_IMAGE_PATH_MARKER not in path:
            continue
        if any(x in path for x in ["logo", "marchio", "placeholder", "default", "no-image"]):
            continue
        score = 10
        if path.endswith("_1.jpg") or path.endswith("_1.webp"):
            score += 5
        scored.append((score, url))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]


def image_ext(url: str, content_type: str) -> str:
    ct = (content_type or "").lower().split(";")[0].strip()
    if ct in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if ct == "image/png":
        return ".png"
    if ct == "image/webp":
        return ".webp"
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    return ".jpg" if suffix == ".jpeg" else (suffix if suffix in {".jpg", ".png", ".webp"} else ".jpg")


def download_image(session: requests.Session, url: str, car_id: str, image_dir: Path, timeout: int, max_bytes: int) -> dict | None:
    response = session.get(url, timeout=timeout, stream=True, headers={"User-Agent": UA})
    response.raise_for_status()
    ext = image_ext(url, response.headers.get("content-type", ""))
    image_dir.mkdir(parents=True, exist_ok=True)
    local = image_dir / f"{car_id}{ext}"
    size = 0
    with local.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                local.unlink(missing_ok=True)
                raise RuntimeError("image_too_large")
            handle.write(chunk)
    return {
        "image_source_url": url,
        "image_source_host": urllib.parse.urlparse(url).netloc.lower(),
        "image_local_path": str(local).replace("\\", "/"),
        "image_bytes": size,
        "image_downloaded_at": now(),
    }


def parse_detail(page, url: str, brand_hint: str | None = None) -> dict | None:
    pairs = table_pairs(page)
    text = rendered_text(page)
    title = rendered_title(page)

    fuel_raw = pair_value(pairs, "Alimentazione") or ""
    fuel, fuel_code = normalise_fuel(fuel_raw)

    kw_raw = pair_value(pairs, "kW")
    cv_raw = pair_value(pairs, "Cv") or pair_value(pairs, "CV")
    power_kw, power_kw_max = parse_kw_cv(kw_raw)
    power_cv, power_cv_max = parse_kw_cv(cv_raw)

    price = parse_price(text, pairs)
    consumption_kwh = parse_decimal(pair_value(pairs, "kWh", "100") or pair_value(pairs, "kWh/100"))
    consumption_l = parse_decimal(pair_value(pairs, "Consumo", "Combinato") or pair_value(pairs, "Consumo", "misto"))
    consumption_kg = None
    if fuel in {"metano", "ibrida_metano"}:
        consumption_kg = consumption_l
        consumption_l = None

    range_wltp = parse_int(pair_value(pairs, "Autonomia", "Elettrico", "Combinato") or pair_value(pairs, "Autonomia", "Combinato"))
    emissions = parse_int(pair_value(pairs, "CO2", "Combinato") or pair_value(pairs, "Emissioni", "WLTP") or pair_value(pairs, "Emissioni", "CO2"))
    battery = parse_decimal(pair_value(pairs, "Batteria") or pair_value(pairs, "Capacità", "batteria"))

    brand = clean(brand_hint or "")
    if not brand or brand.lower() in {"e listini del nuovo", "listini del nuovo", "listino del nuovo", "motornet", "motornet.it"}:
        m = re.search(r"\b([A-Z][A-Za-zÀ-ÿ-]+(?:\s+[A-Z][A-Za-zÀ-ÿ-]+)?)\b", title)
        brand = clean(m.group(1)) if m else "Motornet"

    version = clean(title)
    version = re.sub(r"Motornet\.it.*", "", version, flags=re.I).strip()
    version = re.sub(r"Scheda.*", "", version, flags=re.I).strip()
    version = version or clean(pair_value(pairs, "Versione") or pair_value(pairs, "Allestimento") or title)

    # Strip common Motornet heading noise from version/model.
    version = re.sub(r"^\s*(auto\s+)?e\s+listini\s+del\s+nuovo\s+", "", version, flags=re.I)
    version = re.sub(r"\s*-\s*$", "", version).strip()

    model = version
    if brand and model.lower().startswith(brand.lower()):
        model = clean(model[len(brand):])
    model = clean(model) or version or brand

    car_id = make_id(url)
    car = {
        "id": car_id,
        "brand": brand,
        "model": model,
        "version": version,
        "powertrain": version,
        "fuel": fuel,
        "fuel_code": fuel_code,
        "fuel_original": clean(fuel_raw),
        "category": category_for_fuel(fuel),
        "source_site": "motornet.it",
        "source_url": url,
        "motornet_detail_url": url,
        "scraped_at": now(),
        "price_source": "motornet_prezzo_di_listino",
        "consumption_source": "motornet_technical_sheet",
    }

    optional = {
        "price_eur": price,
        "power_kw": power_kw,
        "power_kw_max": power_kw_max,
        "power_cv": power_cv,
        "power_cv_max": power_cv_max,
        "consumption_kwh_100km": consumption_kwh,
        "consumption_l_100km": consumption_l,
        "consumption_kg_100km": consumption_kg,
        "battery_kwh": battery,
        "range_wltp_km": range_wltp,
        "emissions_g_km": emissions,
    }
    for key, value in optional.items():
        if value is not None:
            car[key] = value

    image_url = extract_image_url(page)
    if image_url:
        car["image_source_url"] = image_url
        car["image_source_host"] = urllib.parse.urlparse(image_url).netloc.lower()

    car["specs_raw"] = pairs
    return car if car["brand"] and car["model"] else None


def build_payload(cars, errors, args, requests_count, images_downloaded):
    return {
        "source": "motornet.it",
        "status": "ok" if cars else "empty",
        "scraped_at": now(),
        "schema": "cars_motornet_v1",
        "request_policy": {
            "delay_seconds": args.delay,
            "limit": args.limit,
            "requests_count": requests_count,
            "checkpoint_every": args.checkpoint_every,
            "download_images": args.download_images,
            "image_dir": args.image_dir,
        },
        "image_stats": {"downloaded": images_downloaded},
        "cars": cars,
        "errors": errors[-100:],
    }


def write_payload(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_checkpoint(count: int, image_dir: Path) -> None:
    subprocess.run(["git", "config", "user.name", "github-actions"], check=False)
    subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=False)
    subprocess.run(["git", "add", str(OUT), str(image_dir)], check=False)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", f"Checkpoint Motornet catalogue ({count} cars)"], check=False)
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
    subprocess.run(["git", "push"], check=False)


def brand_name_from_page(page, brand_url: str) -> str:
    code = brand_code_from_url(brand_url)
    fallback = BRAND_NAME_BY_CODE.get(code or "", code or "")

    brand_title = rendered_title(page)
    brand_name = clean(brand_title)
    brand_name = re.sub(r"(?i)\b(auto|modelli|listino|listini|del|nuovo|e)\b", " ", brand_name)
    brand_name = clean(brand_name)

    if (
        not brand_name
        or brand_name.lower() in {"motornet.it", "listino", "listini", "auto"}
        or "listin" in brand_name.lower()
        or brand_name.lower() == "e"
    ):
        brand_name = fallback

    # For known codes, prefer the canonical name. This avoids values like
    # 'e listini del nuovo' when Motornet's heading is noisy.
    if fallback:
        return fallback

    return brand_name or "Motornet"


def expand_model_links_to_details(page, model_links: list[str], args, robots, errors, requests_count: int) -> tuple[list[str], int]:
    detail_links: list[str] = []
    for model_url in model_links:
        if "/allestimento/" in model_url:
            if model_url not in detail_links:
                detail_links.append(model_url)
            continue

        if not can_fetch(robots, model_url):
            errors.append({"url": model_url, "error": "blocked_by_robots"})
            continue

        try:
            time.sleep(max(1, args.delay / 2))
            page.goto(model_url, wait_until="domcontentloaded", timeout=args.timeout)
            page.wait_for_timeout(1800)
            requests_count += 1
            found = discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/modello/\d+/allestimento/[^/]+$")
            print("    allestimenti:", len(found), model_url)
            for detail_url in found:
                if detail_url not in detail_links:
                    detail_links.append(detail_url)
        except Exception as exc:
            errors.append({"url": model_url, "error": f"model_expand: {exc}"})
    return detail_links, requests_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=650)
    parser.add_argument("--delay", type=float, default=8)
    parser.add_argument("--timeout", type=int, default=45000)
    parser.add_argument("--brand-codes", default="", help="CSV brand codes for test runs, e.g. ABA,ROL")
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--checkpoint-commit", default="true")
    parser.add_argument("--download-images", default="true")
    parser.add_argument("--image-dir", default="assets/cars/motornet")
    parser.add_argument("--max-image-mb", type=float, default=6)
    args = parser.parse_args()

    args.checkpoint_commit = str(args.checkpoint_commit).lower() in {"1", "true", "yes", "si", "sì", "on"}
    args.download_images = str(args.download_images).lower() in {"1", "true", "yes", "si", "sì", "on"}
    image_dir = Path(args.image_dir)
    max_image_bytes = int(args.max_image_mb * 1024 * 1024)

    robots = urllib.robotparser.RobotFileParser()
    robots.set_url(f"{BASE}/robots.txt")
    try:
        robots.read()
    except Exception as exc:
        print("WARN robots non leggibile:", exc)

    image_session = requests.Session()
    image_session.headers.update({"User-Agent": UA})

    cars, errors = [], []
    requests_count = images_downloaded = last_checkpoint = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, locale="it-IT")
        page = context.new_page()

        if args.brand_codes.strip():
            brand_urls = [f"{BASE}/auto/scheda-modello/{code.strip().upper()}" for code in args.brand_codes.split(",") if code.strip()]
        else:
            print("LIST", LIST_URL)
            if can_fetch(robots, LIST_URL):
                page.goto(LIST_URL, wait_until="domcontentloaded", timeout=args.timeout)
                page.wait_for_timeout(2500)
                requests_count += 1
                brand_urls = discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/[A-Z0-9]{2,4}$")
                if not brand_urls:
                    print("  automatic brand discovery returned 0 links; using known brand code fallback")
                    brand_urls = [f"{BASE}/auto/scheda-modello/{code}" for code in KNOWN_BRAND_CODES]
            else:
                brand_urls = []
                errors.append({"url": LIST_URL, "error": "blocked_by_robots"})

        print("brand links:", len(brand_urls))
        seen_details = set()

        for brand_url in brand_urls:
            if len(cars) >= args.limit:
                break
            if not can_fetch(robots, brand_url):
                errors.append({"url": brand_url, "error": "blocked_by_robots"})
                continue

            try:
                time.sleep(args.delay)
                print("BRAND", brand_url)
                page.goto(brand_url, wait_until="domcontentloaded", timeout=args.timeout)
                page.wait_for_timeout(2500)
                requests_count += 1
                brand_name = brand_name_from_page(page, brand_url)

                detail_links = discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/modello/\d+/allestimento/[^/]+$")
                model_links = discover_links_after_clicking_menus(page, r"^/auto/scheda-modello/modello/\d+$")
                if model_links:
                    expanded, requests_count = expand_model_links_to_details(page, model_links, args, robots, errors, requests_count)
                    for detail_url in expanded:
                        if detail_url not in detail_links:
                            detail_links.append(detail_url)

                print("  detail links:", len(detail_links))
            except Exception as exc:
                errors.append({"url": brand_url, "error": str(exc)})
                continue

            for detail_url in detail_links:
                if len(cars) >= args.limit:
                    break
                if detail_url in seen_details:
                    continue
                seen_details.add(detail_url)

                if not can_fetch(robots, detail_url):
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

                    car = parse_detail(page, detail_url, brand_name)
                    if not car:
                        continue

                    if args.download_images and car.get("image_source_url"):
                        try:
                            time.sleep(max(1, args.delay / 2))
                            image_data = download_image(image_session, car["image_source_url"], car["id"], image_dir, int(args.timeout / 1000), max_image_bytes)
                            if image_data:
                                car.update(image_data)
                                images_downloaded += 1
                        except Exception as exc:
                            car["image_error"] = str(exc)
                            errors.append({"url": car.get("image_source_url"), "error": f"image: {exc}"})

                    cars.append(car)
                    print(f"  + {car.get('brand')} {car.get('model')} [{car.get('fuel')}] price={car.get('price_eur')} kwh100={car.get('consumption_kwh_100km')} l100={car.get('consumption_l_100km')}")

                    if args.checkpoint_commit and args.checkpoint_every > 0 and len(cars) % args.checkpoint_every == 0 and len(cars) != last_checkpoint:
                        write_payload(build_payload(cars, errors, args, requests_count, images_downloaded))
                        git_checkpoint(len(cars), image_dir)
                        last_checkpoint = len(cars)

                except Exception as exc:
                    errors.append({"url": detail_url, "error": str(exc)})

        context.close()
        browser.close()

    payload = build_payload(cars, errors, args, requests_count, images_downloaded)
    write_payload(payload)
    print("Done cars=", len(cars), "errors=", len(errors), "requests=", requests_count, "images_downloaded=", images_downloaded, "status=", payload["status"])


if __name__ == "__main__":
    main()
