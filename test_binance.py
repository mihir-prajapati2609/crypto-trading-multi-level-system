import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    ex = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True
    })
    try:
        print("Fetching markets...")
        await ex.load_markets()
        print("Fetching orderbook...")
        ob = await ex.fetch_order_book('BTC/USDT')
        print("Success! OB:", len(ob['bids']), "bids")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Detailed Error:", repr(e))
    finally:
        await ex.close()

asyncio.run(main())
