import os
import sys
import asyncio
import aiohttp
import re
from PIL import Image
from io import BytesIO
import platform

# Console encoding configuration
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

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
        print(f"[SKIP] {symbol} already exists")
        return
    try:
        async with session.get(logo_url) as resp:
            if resp.status != 200:
                return
            img_bytes = await resp.read()
            img = Image.open(BytesIO(img_bytes)).convert("RGBA")
            img = img.resize((64, 64))
            img.save(save_path)
            print(f"[SAVE] {symbol} saved")
    except Exception as e:
        print(f"[ERROR] Error saving {symbol}: {e}")

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

        # Spot coinleri eşleştirme için map'e al
        spot_map = {asset["assetCode"].upper(): asset.get("logoUrl") for asset in spot_assets if asset.get("logoUrl")}

        # Spot + Futures coinleri birleştir
        all_symbols = {}
        
        # 1. Spot coinleri ekle
        for asset in spot_assets:
            code = asset["assetCode"]
            if asset.get("logoUrl"):
                all_symbols[code] = asset["logoUrl"]

        # 2. Futures coinleri ekle ve logolarını bul/eşleştir
        for f in futures_assets:
            if f in all_symbols:
                continue
            
            logo_url = None
            f_upper = f.upper()
            
            # Eşleştirme kuralları
            if f_upper in spot_map:
                logo_url = spot_map[f_upper]
            else:
                stripped = re.sub(r'^\d+', '', f_upper)
                if stripped and stripped in spot_map:
                    logo_url = spot_map[stripped]
                elif (f_upper + "B") in spot_map:
                    logo_url = spot_map[f_upper + "B"]
                elif f_upper.endswith("B") and f_upper[:-1] in spot_map:
                    logo_url = spot_map[f_upper[:-1]]
                else:
                    # Bulunamayan coinler için CDN fallback
                    logo_url = f"https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/{f.lower()}.png"
            
            all_symbols[f] = logo_url

        print(f"Toplam {len(all_symbols)} coin, indiriliyor...")

        # Asenkron indirme
        tasks = []
        for symbol, logo_url in all_symbols.items():
            if logo_url:
                tasks.append(download_and_resize(session, symbol, logo_url))
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
