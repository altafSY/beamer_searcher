"""BMW i4 eDrive35 CPO inventory monitor.

Polls a list of BMW dealer sites (DealerOn or Dealer.com platforms), filters
for the target spec, and fires an SMS notification for each newly-seen VIN.
"""

import argparse
import base64
import json
import logging
import re
import sys
import time
from pathlib import Path

import requests

from dealers import DEALERS
from notify import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("check")

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "seen_vins.json"

# Filter targets (with deliberate buffers above the user's stated caps).
MAX_PRICE = 39_000
MAX_MILEAGE = 33_000
TARGET_TRIM_FRAGMENT = "edrive35"
EXCLUDED_COLOR_FRAGMENT = "white"
HARMAN_FRAGMENTS = ("harman", "kardon")  # both must appear (case-insensitive); used as a flag, not a filter

# Known BMW packages we look for in DealerOn comment blobs. Order doesn't matter.
DEALERON_KNOWN_PACKAGES = (
    "Driving Assistance Pro",
    "Driving Assistance Package",
    "Connected Package Pro",
    "Parking Assistance Package",
    "Premium Package",
    "Convenience Package",
    "Executive Package",
    "M Sport Package",
    "Shadowline",
)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

DEALERON_TAGGING_RE = re.compile(
    r'<script[^>]*id="dealeron_tagging_data"[^>]*>(\{.*?\})</script>',
    re.DOTALL,
)


# ---------- Platform detection ----------

def detect_platform(host: str) -> str | None:
    """Returns 'dealeron', 'dealercom', or None."""
    try:
        r = requests.get(f"https://{host}/", headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        log.warning("detect_platform %s: %s", host, e)
        return None
    if r.status_code >= 400:
        log.warning("detect_platform %s: HTTP %s", host, r.status_code)
        return None
    body = r.text.lower()
    if "dealeron" in body:
        return "dealeron"
    if "dealer.com" in body or "cdn.dealer.com" in body:
        return "dealercom"
    return None


# ---------- DealerOn ----------

def _dealeron_ids(host: str) -> tuple[str, str] | None:
    url = f"https://{host}/searchused.aspx?pt=1&Model=i4"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("dealeron discover %s: %s", host, e)
        return None
    m = DEALERON_TAGGING_RE.search(r.text)
    if not m:
        return None
    try:
        t = json.loads(m.group(1))
        return str(t["dealerId"]), str(t["pageId"])
    except (json.JSONDecodeError, KeyError):
        return None


def _dealeron_decode_price(b64: str) -> int | None:
    if not b64:
        return None
    try:
        decoded = base64.b64decode(b64).decode("utf-8", errors="ignore")
    except Exception:
        return None
    fields = {k.strip(): v.strip() for k, _, v in (c.partition(":") for c in decoded.split(";")) if k}
    for key in ("Internet Price", "Selling Price", "Sale Price", "MSRP"):
        if key in fields:
            try:
                return int(float(fields[key]))
            except ValueError:
                continue
    return None


def fetch_dealeron(host: str) -> list[dict]:
    ids = _dealeron_ids(host)
    if not ids:
        log.warning("dealeron %s: no IDs", host)
        return []
    dealer_id, page_id = ids
    url = (
        f"https://{host}/api/vhcliaa/vehicle-pages/cosmos/srp/vehicles/"
        f"{dealer_id}/{page_id}?host={host}&Model=i4&pn=96"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        log.error("dealeron fetch %s: %s", host, e)
        return []

    out = []
    for entry in data.get("DisplayCards", []):
        if entry.get("IsAdCard"):
            continue
        c = entry.get("VehicleCard") or {}
        vin = c.get("VehicleVin")
        if not vin:
            continue
        comments = c.get("VehicleCommentsEncoded") or ""
        features = c.get("Features") or []
        out.append({
            "vin": vin,
            "year": c.get("VehicleYear"),
            "trim": c.get("VehicleTrim") or "",
            "cpo": bool(c.get("VehicleCpo")),
            "color": c.get("ExteriorColorLabel") or "",
            "mileage": _parse_int(c.get("Mileage")),
            "price": _dealeron_decode_price(c.get("VehiclePriceLibrary") or ""),
            "url": c.get("VehicleDetailUrl") or "",
            "has_harman": _has_harman(comments),
            "packages": _extract_dealeron_packages(comments),
            "extra_count": _count_extras(features, comments),
        })
    return out


# ---------- Dealer.com ----------

def _dealercom_inventory(host: str) -> list[dict]:
    """Raw CPO inventory listing for i4."""
    url = (
        f"https://{host}/apis/widget/INVENTORY_LISTING_DEFAULT_AUTO_CERTIFIED_USED:"
        f"inventory-data-bus1/getInventory?model=i4&pageSize=96"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json().get("inventory") or []
    except (requests.RequestException, ValueError) as e:
        log.error("dealercom fetch %s: %s", host, e)
        return []


def _dealercom_vdp_has_harman(host: str, link: str) -> bool:
    """Fetch the VDP and look for 'harman' / 'kardon' substrings."""
    if not link:
        return False
    if not link.startswith("http"):
        link = f"https://{host}{link}"
    try:
        r = requests.get(link, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("dealercom VDP %s: %s", link, e)
        return False
    return _has_harman(r.text)


def fetch_dealercom(host: str) -> list[dict]:
    inv = _dealercom_inventory(host)
    out = []
    for item in inv:
        vin = item.get("vin")
        if not vin:
            continue
        # Build attribute lookup
        attrs = {a.get("name"): a for a in (item.get("attributes") or [])}
        color = (attrs.get("exteriorColor") or {}).get("value") or ""
        odometer_raw = (attrs.get("odometer") or {}).get("value") or ""
        mileage = _parse_int(odometer_raw)

        pricing = item.get("pricing") or {}
        price_str = pricing.get("retailPrice") or ""
        price = _parse_int(price_str)

        link = item.get("link") or ""
        if link and not link.startswith("http"):
            full_url = f"https://{host}{link}"
        else:
            full_url = link

        raw_packages = item.get("packages") or []
        packages = _clean_dealercom_packages(raw_packages)
        option_codes = item.get("optionCodes") or []

        # has_harman is unknown without VDP fetch; we set it lazily in main loop.
        out.append({
            "vin": vin,
            "year": item.get("year"),
            "trim": item.get("trim") or "",
            "cpo": bool(item.get("certified")),
            "color": color,
            "mileage": mileage,
            "price": price,
            "url": full_url,
            "_vdp_link": link,
            "_needs_vdp_check": True,
            "has_harman": False,  # filled in main loop after cheap filters pass
            "packages": packages,
            "extra_count": len(raw_packages) + len(option_codes),
        })
    return out


# ---------- Shared helpers ----------

def _parse_int(s) -> int | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None


def _has_harman(text: str) -> bool:
    t = (text or "").lower()
    return all(frag in t for frag in HARMAN_FRAGMENTS)


def _extract_dealeron_packages(comments: str) -> list[str]:
    if not comments:
        return []
    c = comments.lower()
    return [pkg for pkg in DEALERON_KNOWN_PACKAGES if pkg.lower() in c]


def _clean_dealercom_packages(raw: list) -> list[str]:
    """Dealer.com lumps wheel options into 'packages'; trim noisy entries for SMS display."""
    out = []
    for p in raw or []:
        if not isinstance(p, str):
            continue
        if p.lower().startswith(("wheels:", "tires:")):
            continue
        out.append(p)
    return out


def _count_extras(features, comments: str) -> int:
    base = len(features) if isinstance(features, list) else 0
    c = (comments or "").lower()
    known = (
        "m sport", "premium package", "driving assistance pro", "parking assistance",
        "connected package pro", "convenience package", "executive package", "shadowline",
    )
    return base + sum(1 for p in known if p in c)


def passes_cheap_filters(v: dict) -> bool:
    """All filters that can be applied without a VDP fetch."""
    if TARGET_TRIM_FRAGMENT not in (v.get("trim") or "").lower():
        return False
    if not v.get("cpo"):
        return False
    if EXCLUDED_COLOR_FRAGMENT in (v.get("color") or "").lower():
        return False
    mi = v.get("mileage")
    if mi is None or mi > MAX_MILEAGE:
        return False
    pr = v.get("price")
    if pr is None or pr > MAX_PRICE:
        return False
    return True


# ---------- State ----------

def load_seen() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text()).get("seen", []))
    except Exception as e:
        log.warning("seen_vins.json unreadable, starting empty: %s", e)
        return set()


def save_seen(seen: set[str]) -> None:
    STATE_FILE.write_text(json.dumps({"seen": sorted(seen)}, indent=2) + "\n")


# ---------- Main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Find matches and print them but send no notifications, don't update state.")
    ap.add_argument("--seed", action="store_true",
                    help="Add all current matches to the seen list WITHOUT notifying. Run once at first setup.")
    args = ap.parse_args()

    seen = load_seen()
    log.info("Loaded %d previously-seen VINs.", len(seen))

    all_matches: list[dict] = []
    for dealer in DEALERS:
        name = dealer["name"]
        host = dealer["host"]
        log.info("--- %s (%s) ---", name, host)

        platform = dealer.get("platform") or detect_platform(host)
        if platform == "dealeron":
            vehicles = fetch_dealeron(host)
        elif platform == "dealercom":
            vehicles = fetch_dealercom(host)
        else:
            log.warning("%s: unsupported platform '%s', skipping", host, platform)
            continue

        log.info("%s: %d i4 candidates", platform, len(vehicles))

        for v in vehicles:
            if not passes_cheap_filters(v):
                continue
            # Harman/Kardon is reported as a flag (not a filter). For Dealer.com
            # we need the VDP to check it.
            if v.get("_needs_vdp_check") and not v.get("has_harman"):
                v["has_harman"] = _dealercom_vdp_has_harman(host, v.get("_vdp_link", ""))
            match = {
                "vin": v["vin"],
                "dealer": name,
                "year": v["year"],
                "trim": v["trim"],
                "price": v["price"],
                "mileage": v["mileage"],
                "color": v["color"],
                "url": v["url"],
                "has_harman": bool(v.get("has_harman")),
                "packages": v.get("packages") or [],
                "extra_count": v["extra_count"],
            }
            all_matches.append(match)
            log.info("MATCH %s %s %sk@$%s H/K=%s %s",
                     match["vin"], match["color"], match["mileage"] // 1000,
                     f"{match['price']:,}",
                     "Y" if match["has_harman"] else "N",
                     "<-- already notified" if match["vin"] in seen else "(NEW)")
        time.sleep(0.5)

    all_matches.sort(key=lambda m: m["extra_count"], reverse=True)
    new = [m for m in all_matches if m["vin"] not in seen]
    log.info("=== %d total matches, %d new ===", len(all_matches), len(new))

    if args.dry_run:
        for m in all_matches:
            print(json.dumps(m, indent=2))
        return 0

    if args.seed:
        for m in all_matches:
            seen.add(m["vin"])
        save_seen(seen)
        log.info("Seeded %d VINs as already-known (no notifications sent).", len(all_matches))
        return 0

    for m in new:
        notify(m)
        seen.add(m["vin"])
        time.sleep(1)

    save_seen(seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
