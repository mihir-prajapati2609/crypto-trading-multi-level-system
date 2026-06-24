import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
import traceback

load_dotenv()

async def main():
    ex = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True
    })
    try:
        markets = await ex.load_markets()
        usdt_markets = {sym for sym in markets if sym.endswith('/USDT')}
        print("Loading tickers for", len(usdt_markets), "markets...")
        tickers = await ex.fetch_tickers(list(usdt_markets))
        print("Success! Tickers:", len(tickers))
    except Exception as e:
        traceback.print_exc()
        print("Detailed Error:", repr(e))
    finally:
        await ex.close()

asyncio.run(main())
