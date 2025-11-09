import os
import asyncio
import aiohttp
from PIL import Image
from io import BytesIO
import platform

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Binance API
SPOT_URL = "https://www.binance.com/bapi/asset/v2/public/asset/asset/get-all-asset"
FUTURES_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"

SAVE_DIR = "binance"
os.makedirs(SAVE_DIR, exist_ok=True)

async def fetch_json(session, url):
    async with session.get(url) as resp:
        if resp.status != 200:
            print(f"Failed to get {url}: {resp.status}")
            return None
        return await resp.json()

async def download_and_resize(session, symbol, logo_url):
    save_path = f"{SAVE_DIR}/{symbol}.png"
    if os.path.exists(save_path):
        print(f"⚡ {symbol} already exists, skipping")
        return
    try:
        async with session.get(logo_url) as resp:
            if resp.status != 200:
                return
            img_bytes = await resp.read()
            img = Image.open(BytesIO(img_bytes)).convert("RGBA")
            img = img.resize((64, 64))
            img.save(save_path)
            print(f"✅ {symbol} saved")
    except Exception as e:
        print(f"⚠️ Error saving {symbol}: {e}")

async def main():
    # Windows uyumluluğu
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # TCP connector ile eşzamanlı bağlantı limiti
    connector = aiohttp.TCPConnector(limit=50)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Spot coinler
        spot_data = await fetch_json(session, SPOT_URL)
        spot_assets = spot_data.get("data", []) if spot_data else []

        # Futures coinler
        futures_data = await fetch_json(session, FUTURES_URL)
        futures_assets = []
        if futures_data:
            for s in futures_data.get("symbols", []):
                base = s.get("baseAsset")
                if base not in futures_assets:
                    futures_assets.append(base)

        # Spot + Futures coinleri birleştir
        all_symbols = {asset["assetCode"]: asset.get("logoUrl") for asset in spot_assets}
        for f in futures_assets:
            if f not in all_symbols:
                all_symbols[f] = None  # logo yoksa boş geç

        print(f"Toplam {len(all_symbols)} coin, indiriliyor...")

        # Asenkron indirme
        tasks = []
        for symbol, logo_url in all_symbols.items():
            if logo_url:
                tasks.append(download_and_resize(session, symbol, logo_url))
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
