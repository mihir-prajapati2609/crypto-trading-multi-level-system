import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
import ccxt.async_support as ccxt

from config.settings import get_settings
from data.models import OrderBookSnapshot, OrderBookLevel, TickerData, FundingRateData, BalanceSnapshot
from config.constants import ORDER_BOOK_DEPTH, WS_RECONNECT_DELAY_SECONDS

logger = logging.getLogger(__name__)

class PriceFeed:
    """Manages exchange connections and data polling."""
    
    def __init__(self):
        self.settings = get_settings()
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self._order_books: Dict[str, Dict[str, OrderBookSnapshot]] = {}
        self._tickers: Dict[str, Dict[str, TickerData]] = {}
        self._funding_rates: Dict[str, Dict[str, FundingRateData]] = {}
        self._ohlcv: Dict[str, Dict[str, Dict[str, list]]] = {}
        self.is_running = False
        self._tasks: List[asyncio.Task] = []

    async def initialize(self):
        """Initialize ccxt exchange instances."""
        for ex_name, config in self.settings.exchanges.items():
            ex_class = getattr(ccxt, ex_name)
            
            def create_exchange_instance(use_keys=True):
                params = {
                    'enableRateLimit': True,
                    'options': {
                        'adjustForTimeDifference': True,
                    }
                }
                if use_keys and config.api_key and config.api_secret:
                    params['apiKey'] = config.api_key
                    params['secret'] = config.api_secret
                    if config.passphrase:
                        params['password'] = config.passphrase
                return ex_class(params)

            exchange = create_exchange_instance(use_keys=True)
            if config.sandbox:
                exchange.set_sandbox_mode(True)
                
            logger.info(f"Loading markets for {ex_name} and syncing clock...")
            try:
                if hasattr(exchange, 'load_time_difference'):
                    await exchange.load_time_difference()
            except Exception as e:
                logger.warning(f"Could not load time difference for {ex_name}: {e}")
                
            try:
                try:
                    await exchange.load_markets()
                except ccxt.AuthenticationError as e:
                    logger.warning(f"Authentication failed for {ex_name} with configured keys: {e}. Falling back to public (no-keys) mode.")
                    await exchange.close()
                    exchange = create_exchange_instance(use_keys=False)
                    if config.sandbox:
                        exchange.set_sandbox_mode(True)
                    await exchange.load_markets()
                
                self.exchanges[ex_name] = exchange
                self._order_books[ex_name] = {}
                self._tickers[ex_name] = {}
                self._funding_rates[ex_name] = {}
                self._ohlcv[ex_name] = {}
            except Exception as e:
                logger.error(f"Failed to load markets for exchange {ex_name}: {e}. Disabling this exchange.")
                try:
                    await exchange.close()
                except Exception:
                    pass
            
    async def close(self):
        """Close exchange connections."""
        self.is_running = False
        for task in self._tasks:
            task.cancel()
        for ex in self.exchanges.values():
            await ex.close()

    async def start(self, symbols: List[str]):
        """Starts polling loops for market data."""
        if not self.exchanges:
            await self.initialize()
            
        self.is_running = True
        
        for ex_name in self.exchanges:
            # We'll spawn separate tasks to poll tickers and order books
            self._tasks.append(asyncio.create_task(self._poll_tickers(ex_name, symbols)))
            self._tasks.append(asyncio.create_task(self._poll_order_books(ex_name, symbols)))
            self._tasks.append(asyncio.create_task(self._poll_funding_rates(ex_name, symbols)))
            self._tasks.append(asyncio.create_task(self._poll_ohlcv(ex_name)))
            
    async def _poll_tickers(self, ex_name: str, symbols: List[str]):
        exchange = self.exchanges[ex_name]
        while self.is_running:
            try:
                # fetch_tickers without arguments to avoid URI length issues
                tickers = await exchange.fetch_tickers()
                for sym in symbols:
                    if sym in tickers:
                        t = tickers[sym]
                        self._tickers[ex_name][sym] = TickerData(
                            exchange=ex_name,
                            symbol=sym,
                            last_price=float(t.get('last') or 0.0),
                            bid=float(t.get('bid') or 0.0),
                            ask=float(t.get('ask') or 0.0),
                            base_volume=float(t.get('baseVolume') or 0.0),
                            quote_volume=float(t.get('quoteVolume') or 0.0),
                            change_pct=float(t.get('percentage') or 0.0)
                        )
                await asyncio.sleep(1) # Polling interval
            except Exception as e:
                logger.error(f"Error polling tickers from {ex_name}: {e}")
                await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)

    async def _poll_order_books(self, ex_name: str, symbols: List[str]):
        exchange = self.exchanges[ex_name]
        while self.is_running:
            for sym in symbols:
                try:
                    ob = await exchange.fetch_order_book(sym, limit=ORDER_BOOK_DEPTH)
                    bids = [OrderBookLevel(price=float(p), quantity=float(q)) for p, q in ob['bids']]
                    asks = [OrderBookLevel(price=float(p), quantity=float(q)) for p, q in ob['asks']]
                    self._order_books[ex_name][sym] = OrderBookSnapshot(
                        exchange=ex_name,
                        symbol=sym,
                        bids=bids,
                        asks=asks,
                        timestamp=time.time()
                    )
                except Exception as e:
                    logger.error(f"Error fetching order book for {sym} on {ex_name}: {e}")
            await asyncio.sleep(0.5)

    async def _poll_funding_rates(self, ex_name: str, symbols: List[str]):
        exchange = self.exchanges[ex_name]
        if not exchange.has.get('fetchFundingRates'):
            return
            
        while self.is_running:
            try:
                rates = await exchange.fetch_funding_rates(symbols)
                for sym, info in rates.items():
                    self._funding_rates[ex_name][sym] = FundingRateData(
                        exchange=ex_name,
                        symbol=sym,
                        funding_rate=float(info.get('fundingRate', 0)),
                        next_funding_time=float(info.get('fundingTimestamp', 0)) / 1000.0,
                    )
                await asyncio.sleep(60) # Funding rates change slowly
            except Exception as e:
                logger.error(f"Error fetching funding rates from {ex_name}: {e}")
                await asyncio.sleep(60)

    async def _poll_ohlcv(self, ex_name: str):
        exchange = self.exchanges[ex_name]
        if not exchange.has.get('fetchOHLCV'):
            return
            
        target_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        timeframes = ["15m", "4h"]
        
        while self.is_running:
            for sym in target_symbols:
                for tf in timeframes:
                    try:
                        ohlcv = await exchange.fetch_ohlcv(sym, timeframe=tf, limit=100)
                        if sym not in self._ohlcv[ex_name]:
                            self._ohlcv[ex_name][sym] = {}
                        self._ohlcv[ex_name][sym][tf] = ohlcv
                    except Exception as e:
                        logger.error(f"Error fetching OHLCV for {sym} {tf} on {ex_name}: {e}")
            await asyncio.sleep(60)


    def get_order_book(self, exchange: str, symbol: str) -> Optional[OrderBookSnapshot]:
        return self._order_books.get(exchange, {}).get(symbol)

    def get_ticker(self, exchange: str, symbol: str) -> Optional[TickerData]:
        return self._tickers.get(exchange, {}).get(symbol)
        
    def get_all_tickers(self, exchange: str) -> Dict[str, TickerData]:
        return self._tickers.get(exchange, {})\

    def get_funding_rate(self, exchange: str, symbol: str) -> Optional[FundingRateData]:
        return self._funding_rates.get(exchange, {}).get(symbol)

    async def fetch_real_balance(self, exchange_name: str = "binance") -> Optional[BalanceSnapshot]:
        """
        Fetches the real account balance from the exchange (read-only).
        Returns a BalanceSnapshot with USDT and other asset values.
        """
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return None
        try:
            raw = await exchange.fetch_balance()
            total_info = raw.get("total", {})
            free_info  = raw.get("free", {})
            used_info  = raw.get("used", {})

            # Summarize in USD: use USDT directly, and approximate BTC/ETH via last ticker
            usdt_total = float(total_info.get("USDT", 0.0))
            usdt_free  = float(free_info.get("USDT", 0.0))
            usdt_used  = float(used_info.get("USDT", 0.0))

            # Add BTC and ETH value if held
            for coin, sym in [("BTC", "BTC/USDT"), ("ETH", "ETH/USDT"), ("BNB", "BNB/USDT")]:
                qty = float(total_info.get(coin, 0.0))
                if qty > 0:
                    ticker = self._tickers.get(exchange_name, {}).get(sym)
                    price = ticker.last_price if ticker else 0.0
                    usdt_total += qty * price

            assets = {k: float(v) for k, v in total_info.items() if float(v or 0) > 0}

            snapshot = BalanceSnapshot(
                exchange=exchange_name,
                total_usd=round(usdt_total, 2),
                free_usd=round(usdt_free, 2),
                used_usd=round(usdt_used, 2),
                assets=assets,
            )
            logger.info(f"[Balance] {exchange_name}: total=${usdt_total:.2f} free=${usdt_free:.2f}")
            return snapshot
        except Exception as e:
            logger.warning(f"Could not fetch real balance from {exchange_name}: {e}")
            return None

