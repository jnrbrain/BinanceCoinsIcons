"""
Forex & Commodities Icon Downloader for BinanceCoinsIcons repo.

Usage:
    python download_forex_icons.py

Icons are saved to the BinanceCoinsIcons/binance/ directory.

Naming convention:
  - Forex pairs: forex_EURUSD.png, forex_GBPUSD.png, etc.
  - Commodities: GOLD.png, SILVER.png, OIL.png, NATGAS.png, COPPER.png

Sources:
  - Forex: HatScripts/circle-flags (high-quality circular country flags)
    Composite of base + quote currency flags side by side.
  - Commodities: Real financial asset icons from public CDNs.
"""

import os
import sys
import asyncio
import aiohttp
from io import BytesIO
import platform

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("PIL not found. Install: pip install Pillow")
    sys.exit(1)

try:
    import cairosvg
    HAS_CAIROSVG = True
except ImportError:
    HAS_CAIROSVG = False

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from typing import Optional

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Resolve save directory
BINANCE_ICONS_DIR = None
candidates = [
    os.path.join(SCRIPT_DIR, "binance"),  # If run from BinanceCoinsIcons root
    os.path.join(SCRIPT_DIR, "..", "..", "BinanceCoinsIcons", "binance"),
    r"D:\Github\BinanceCoinsIcons\binance",
]
for c in candidates:
    if os.path.isdir(c):
        BINANCE_ICONS_DIR = os.path.abspath(c)
        break
if not BINANCE_ICONS_DIR:
    BINANCE_ICONS_DIR = os.path.join(SCRIPT_DIR, "binance")

os.makedirs(BINANCE_ICONS_DIR, exist_ok=True)

ICON_SIZE = 64  # px

# ── Forex Pairs ───────────────────────────────────────────────────────────────
# HatScripts circle-flags: https://hatscripts.github.io/circle-flags/flags/{code}.svg
# These are high-quality circular SVG flags used by major finance apps.

CIRCLE_FLAGS_BASE = "https://hatscripts.github.io/circle-flags/flags"

# Currency code → ISO 3166-1 alpha-2 country code (for flag)
CURRENCY_TO_FLAG = {
    'EUR': 'eu',   # European Union
    'USD': 'us',   # United States
    'GBP': 'gb',   # United Kingdom
    'JPY': 'jp',   # Japan
    'AUD': 'au',   # Australia
    'CHF': 'ch',   # Switzerland
    'CAD': 'ca',   # Canada
    'NZD': 'nz',   # New Zealand
}

FOREX_PAIRS = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCHF', 'USDCAD',
    'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY', 'AUDJPY', 'EURAUD',
]

# ── Commodities ───────────────────────────────────────────────────────────────
# Real commodity icons from public free sources

COMMODITY_ICONS = {
    'GOLD': "https://cdn-icons-png.flaticon.com/128/2150/2150150.png",      # Gold bars
    'SILVER': "https://cdn-icons-png.flaticon.com/128/2150/2150190.png",    # Silver/platinum bar
    'OIL': "https://cdn-icons-png.flaticon.com/128/3656/3656860.png",       # Oil barrel
    'NATGAS': "https://cdn-icons-png.flaticon.com/128/1537/1537767.png",    # Gas flame
    'COPPER': "https://cdn-icons-png.flaticon.com/128/5766/5766225.png",    # Copper wire/material
}

# Fallback commodity icons if primary fails
COMMODITY_FALLBACK = {
    'GOLD': "https://img.icons8.com/fluency/128/gold-bars.png",
    'SILVER': "https://img.icons8.com/fluency/128/silver-bars.png",
    'OIL': "https://img.icons8.com/fluency/128/oil-industry.png",
    'NATGAS': "https://img.icons8.com/fluency/128/gas-industry.png",
    'COPPER': "https://img.icons8.com/fluency/128/copper.png",
}


async def download_bytes(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    """Download from URL, return bytes or None on failure."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            return await resp.read()
    except Exception as e:
        print(f"    [WARN] Download failed: {url} — {e}")
        return None


def svg_to_png(svg_bytes: bytes, size: int = 128) -> Optional[bytes]:
    """Convert SVG bytes to PNG bytes at the given size."""
    if HAS_CAIROSVG:
        try:
            return cairosvg.svg2png(bytestring=svg_bytes,
                                     output_width=size, output_height=size)
        except Exception:
            pass
    # Fallback: try using PIL with svg2rlg if available
    return None


def create_circular_image(img_bytes: bytes, size: int) -> Image.Image:
    """Create a circular cropped image."""
    img = Image.open(BytesIO(img_bytes)).convert('RGBA')
    img = img.resize((size, size), Image.LANCZOS)

    # Create circular mask
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)

    # Apply mask
    result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    return result


def create_forex_composite(left_img: Image.Image, right_img: Image.Image) -> Image.Image:
    """Create a composite forex pair icon with two overlapping circular flags.
    
    Left flag (base currency) slightly overlaps right flag (quote currency).
    Professional finance app style.
    """
    canvas_size = ICON_SIZE
    canvas = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))

    # Each flag is ~70% of total width for nice overlap
    flag_size = int(canvas_size * 0.68)

    left_flag = left_img.resize((flag_size, flag_size), Image.LANCZOS)
    right_flag = right_img.resize((flag_size, flag_size), Image.LANCZOS)

    # Position: right flag behind (bottom-right), left flag in front (top-left)
    right_x = canvas_size - flag_size
    right_y = canvas_size - flag_size
    left_x = 0
    left_y = 0

    # Paste right first (behind), then left (in front)
    canvas.paste(right_flag, (right_x, right_y), right_flag)
    canvas.paste(left_flag, (left_x, left_y), left_flag)

    return canvas


async def download_flag_png(session: aiohttp.ClientSession, country_code: str) -> Optional[Image.Image]:
    """Download a circular flag from HatScripts circle-flags.
    
    First tries SVG (if cairosvg available), then falls back to PNG from flagcdn.
    """
    # Try SVG first (best quality)
    if HAS_CAIROSVG:
        svg_url = f"{CIRCLE_FLAGS_BASE}/{country_code}.svg"
        svg_bytes = await download_bytes(session, svg_url)
        if svg_bytes:
            png_bytes = svg_to_png(svg_bytes, 128)
            if png_bytes:
                return create_circular_image(png_bytes, ICON_SIZE)

    # Fallback: flagcdn PNG (rectangular, we'll crop to circle)
    png_url = f"https://flagcdn.com/w160/{country_code}.png"
    png_bytes = await download_bytes(session, png_url)
    if png_bytes:
        return create_circular_image(png_bytes, ICON_SIZE)

    return None


async def download_forex_icons(session: aiohttp.ClientSession):
    """Download and create composite forex pair icons using real circular flags."""
    print(f"\n{'='*50}")
    print(f"  FOREX PAIRS ({len(FOREX_PAIRS)} pairs)")
    print(f"  Source: HatScripts/circle-flags + flagcdn.com")
    print(f"{'='*50}\n")

    # Pre-download all unique currency flags
    currencies = set()
    for pair in FOREX_PAIRS:
        currencies.add(pair[:3])
        currencies.add(pair[3:])

    print(f"  Downloading {len(currencies)} currency flags...")
    flag_cache = {}  # type: dict[str, Optional[Image.Image]]
    for currency in sorted(currencies):
        code = CURRENCY_TO_FLAG.get(currency)
        if not code:
            print(f"    [SKIP] No flag mapping for {currency}")
            flag_cache[currency] = None
            continue
        flag_cache[currency] = await download_flag_png(session, code)
        status = "OK" if flag_cache[currency] else "FAIL"
        print(f"    [{status}] {currency} ({code})")

    print()

    # Create composite forex pair icons
    for pair in FOREX_PAIRS:
        save_path = os.path.join(BINANCE_ICONS_DIR, f"forex_{pair}.png")

        if os.path.exists(save_path):
            print(f"  [SKIP] forex_{pair} already exists")
            continue

        base_currency = pair[:3]
        quote_currency = pair[3:]

        left_flag = flag_cache.get(base_currency)
        right_flag = flag_cache.get(quote_currency)

        if not left_flag or not right_flag:
            print(f"  [FAIL] forex_{pair} — missing flag(s)")
            continue

        icon = create_forex_composite(left_flag, right_flag)
        icon.save(save_path)
        print(f"  [SAVE] forex_{pair}.png")


async def download_commodity_icons(session: aiohttp.ClientSession):
    """Download realistic commodity icons."""
    print(f"\n{'='*50}")
    print(f"  COMMODITIES ({len(COMMODITY_ICONS)} items)")
    print(f"  Source: flaticon.com / icons8.com")
    print(f"{'='*50}\n")

    for symbol, url in COMMODITY_ICONS.items():
        save_path = os.path.join(BINANCE_ICONS_DIR, f"{symbol}.png")

        if os.path.exists(save_path):
            print(f"  [SKIP] {symbol} already exists")
            continue

        img_bytes = await download_bytes(session, url)

        # Try fallback if primary fails
        if not img_bytes:
            fallback_url = COMMODITY_FALLBACK.get(symbol)
            if fallback_url:
                print(f"    Trying fallback for {symbol}...")
                img_bytes = await download_bytes(session, fallback_url)

        if not img_bytes:
            print(f"  [FAIL] {symbol} — could not download from any source")
            continue

        try:
            img = Image.open(BytesIO(img_bytes)).convert('RGBA')
            img = img.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
            img.save(save_path)
            print(f"  [SAVE] {symbol}.png")
        except Exception as e:
            print(f"  [ERROR] {symbol}: {e}")


async def main():
    print(f"\n{'─'*50}")
    print(f"  Forex & Commodities Icon Downloader")
    print(f"  Save: {os.path.abspath(BINANCE_ICONS_DIR)}")
    print(f"{'─'*50}")

    if HAS_CAIROSVG:
        print(f"  ✓ cairosvg available — SVG flags will be used")
    else:
        print(f"  ⚠ cairosvg not installed — using PNG fallback")
        print(f"    Install for best quality: pip install cairosvg")

    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        await download_forex_icons(session)
        await download_commodity_icons(session)

    print(f"\n{'─'*50}")
    print(f"  ✅ Done! Push BinanceCoinsIcons repo for app to pick up icons.")
    print(f"{'─'*50}\n")


if __name__ == "__main__":
    asyncio.run(main())
