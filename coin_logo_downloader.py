"""Download Binance spot + USD-M/COIN-M logos, including Alpha-only assets.
Run from any directory. Missing/failed symbols are reported in icon_coverage.json.
"""
import asyncio
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image

ROOT = Path(__file__).resolve().parent
SAVE_DIR = ROOT / "binance"
SOURCES = {
    "futures_logos": "https://www.binance.com/bapi/apex/v1/public/apex/marketing/futures/asset/logo",
    "spot_logos": "https://www.binance.com/bapi/asset/v2/public/asset/asset/get-all-asset",
    "alpha_logos": "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list",
    "market_logos": "https://www.binance.com/bapi/composite/v1/public/marketing/symbol/list",
    "spot": "https://api.binance.com/api/v3/exchangeInfo",
    "usd_m": "https://fapi.binance.com/fapi/v1/exchangeInfo",
    "coin_m": "https://dapi.binance.com/dapi/v1/exchangeInfo",
}
# Explicit identities only; do not strip arbitrary digits (1INCH, 4, etc.).
INDEX_FALLBACKS = {"ALL", "BTCDOM"}
INDEX_ICON = "https://bin.bnbstatic.com/static/futures-header/default-icon.png"
ALIASES = {"LUNA2": "LUNA", "DODOX": "DODO", "XAU": "XAUT"}


def candidates(symbol, logos):
    names = [symbol]
    for prefix in ("1000000", "10000", "1000"):
        if symbol.startswith(prefix) and symbol[len(prefix):] in logos:
            names.append(symbol[len(prefix):])
            break
    if symbol in ALIASES:
        names.append(ALIASES[symbol])
    return list(dict.fromkeys(url for name in names for url in logos.get(name, [])))


def valid_icon(path):
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except (OSError, ValueError):
        return False


async def fetch_json(session, url):
    for attempt in range(3):
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("code") not in (None, "000000"):
                    raise ValueError(str(data.get("code")))
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            if attempt == 2:
                raise
            await asyncio.sleep(attempt + 1)


async def download_and_resize(session, symbol, urls, semaphore, source_records):
    path = SAVE_DIR / f"{symbol}.png"
    if valid_icon(path) and (not urls or source_records.get(symbol) == urls[0]):
        return "existing"
    async with semaphore:
        for url in urls:
            for attempt in range(2):
                try:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        raw = await response.read()
                    with Image.open(BytesIO(raw)) as original:
                        img = original.convert("RGBA")
                        img.thumbnail((64, 64), Image.Resampling.LANCZOS)
                        canvas = Image.new("RGBA", (64, 64))
                        canvas.paste(img, ((64-img.width)//2, (64-img.height)//2))
                        temp = path.with_suffix(".tmp")
                        canvas.save(temp, format="PNG", optimize=True)
                        temp.replace(path)
                    source_records[symbol] = url
                    print(f"[SAVE] {symbol}")
                    return "downloaded"
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
                    if attempt == 0:
                        await asyncio.sleep(0.3)
        return "existing" if valid_icon(path) else "missing"


async def main(logos_only=False):
    SAVE_DIR.mkdir(exist_ok=True)
    source_file = ROOT / "icon_sources.json"
    source_records = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else {}
    coverage_file = ROOT / 'icon_coverage.json'
    previous = json.loads(coverage_file.read_text(encoding='utf-8')) if coverage_file.exists() else {}
    selected = {name: url for name, url in SOURCES.items() if not logos_only or name.endswith('_logos')}
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=12)) as session:
        results = await asyncio.gather(*(fetch_json(session, url) for url in selected.values()), return_exceptions=True)
        payloads, source_errors = {}, {}
        for name, result in zip(selected, results):
            if isinstance(result, Exception):
                source_errors[name] = str(result)
                print(f"[SOURCE ERROR] {name}: {result}")
            else:
                payloads[name] = result
        logos = {}
        for source, key, image_key in [("futures_logos", "asset", "logo"), ("spot_logos", "assetCode", "logoUrl"), ("alpha_logos", "symbol", "iconUrl"), ("market_logos", "name", "logo")]:
            for asset in payloads.get(source, {}).get("data", []):
                symbol = str(asset.get(key, "")).strip().upper()
                url = asset.get(image_key)
                if symbol and url:
                    logos.setdefault(symbol, []).append(url)
        for symbol in INDEX_FALLBACKS:
            logos.setdefault(symbol, [INDEX_ICON])
        markets = {}
        for source in ("spot", "usd_m", "coin_m"):
            markets[source] = sorted({s["baseAsset"].upper() for s in payloads.get(source, {}).get("symbols", []) if s.get("status", s.get("contractStatus")) == "TRADING"})
        symbols = sorted(set(logos).union(*(set(v) for v in markets.values())).union(p.stem for p in SAVE_DIR.glob('*.png')))
        # Reject path separators/control chars, allow Binance Unicode symbols.
        symbols = [s for s in symbols if s and not re.search(r'[<>:"/\\|?*\x00-\x1f]', s) and '..' not in s]
        semaphore = asyncio.Semaphore(12)
        statuses = await asyncio.gather(*(download_and_resize(session, s, candidates(s, logos), semaphore, source_records) for s in symbols))
        missing = {s for s, status in zip(symbols, statuses) if status == "missing"}
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": SOURCES, "source_errors": source_errors,
            "requested_sources": list(selected),
            "market_coverage_checked": not logos_only and all(name in payloads for name in markets),
            "downloaded": statuses.count("downloaded"), "existing": statuses.count("existing"),
            "missing": sorted(missing),
            "index_fallbacks": sorted(INDEX_FALLBACKS),
            "markets": {name: {"total": len(values), "missing": sorted(set(values) & missing)} for name, values in markets.items()},
        }
        if logos_only:
            # Public logo catalogs are reachable by hosted CI. Do not claim an
            # exchange-wide audit when exchangeInfo was not requested there.
            report['markets'] = previous.get('markets', {})
            report['market_coverage_checked_at'] = previous.get('market_coverage_checked_at', previous.get('generated_at'))
        elif report['market_coverage_checked']:
            report['market_coverage_checked_at'] = report['generated_at']
        source_file.write_text(json.dumps(source_records, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (ROOT / "icon_coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: report[k] for k in ("downloaded", "existing", "source_errors", "markets")}, ensure_ascii=False))
        write_manifest(SAVE_DIR, ROOT / 'icon_manifest.json')
        return 1 if source_errors or any(v["missing"] for v in report["markets"].values()) else 0


def write_manifest(directory=SAVE_DIR, destination=ROOT / "icon_manifest.json"):
    """Publish content hashes for valid images, without copying them to clients."""
    icons = {}
    for path in sorted(directory.glob("*.png")):
        if len(path.stem) > 100 or '..' in path.stem or re.search(r'[<>:"/\\|?*\x00-\x1f]', path.stem):
            continue
        if valid_icon(path) and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
            icons[path.stem] = hashlib.sha256(path.read_bytes()).hexdigest()
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "icons": icons}, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n', encoding="utf-8")
    temporary.replace(destination)
    print(f"Manifest: {len(icons)} icons")
    return icons


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-only', action='store_true', help='Rebuild hashes from existing PNGs without network requests')
    parser.add_argument('--logos-only', action='store_true', help='Refresh public logo catalogs without claiming a fresh exchangeInfo coverage audit')
    args = parser.parse_args()
    if args.manifest_only:
        write_manifest()
    else:
        raise SystemExit(asyncio.run(main(logos_only=args.logos_only)))
