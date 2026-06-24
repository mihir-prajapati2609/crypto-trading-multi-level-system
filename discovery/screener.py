import logging
import asyncio
from typing import List, Dict, Any, Set
import ccxt.async_support as ccxt
from config.settings import get_settings

logger = logging.getLogger(__name__)

class CoinScreener:
    """Scans exchanges for optimal pairs."""
    
    def __init__(self):
        self.settings = get_settings().discovery

    async def scan_all_pairs(self, exchanges: List[ccxt.Exchange]) -> List[str]:
        """
        Finds pairs that are listed on all provided exchanges,
        with sufficient volume.
        """
        if not exchanges:
            return []
            
        exchange_markets: Dict[str, Set[str]] = {}
        market_data: Dict[str, Dict[str, Any]] = {}
        
        try:
            for ex in exchanges:
                markets = await ex.load_markets()
                
                # Filter to USDT pairs
                usdt_markets = {sym for sym in markets if sym.endswith('/USDT')}
                exchange_markets[ex.id] = usdt_markets
                
                # Fetch tickers to get volumes
                tickers = await ex.fetch_tickers()
                market_data[ex.id] = tickers

            # Find intersection of all exchanges
            common_pairs = set.intersection(*exchange_markets.values()) if exchange_markets else set()
            
            # Filter by volume
            valid_pairs = []
            for sym in common_pairs:
                has_volume = True
                for ex in exchanges:
                    ticker = market_data[ex.id].get(sym, {})
                    vol = float(ticker.get('quoteVolume', 0))
                    
                    if vol < self.settings.min_daily_volume_usdt or vol > self.settings.max_daily_volume_usdt:
                        has_volume = False
                        break
                        
                if has_volume:
                    valid_pairs.append(sym)
                    
            logger.info(f"Screener found {len(valid_pairs)} common valid pairs.")
            return valid_pairs
            
        except Exception as e:
            logger.error(f"Error in CoinScreener: {e}")
            return []
