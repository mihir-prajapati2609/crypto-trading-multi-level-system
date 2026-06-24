import logging
import json
import os
from typing import List, Dict, Any
import ccxt.async_support as ccxt
from utils.notifications import NotificationManager

logger = logging.getLogger(__name__)

class NewListingDetector:
    """Detects newly listed coins on exchanges."""
    
    def __init__(self, cache_file="data/known_markets.json", notifier: NotificationManager = None):
        self.cache_file = cache_file
        self.notifier = notifier
        self.known_markets = self._load_cache()

    def _load_cache(self) -> Dict[str, List[str]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.known_markets, f)
        except Exception as e:
            logger.error(f"Error saving market cache: {e}")

    async def check_for_new_listings(self, exchanges: List[ccxt.Exchange]) -> List[str]:
        new_listings = []
        try:
            for ex in exchanges:
                markets = await ex.load_markets(True) # Force reload
                current_symbols = list(markets.keys())
                
                known_for_ex = self.known_markets.get(ex.id, [])
                
                if known_for_ex:
                    new_syms = set(current_symbols) - set(known_for_ex)
                    for sym in new_syms:
                        if sym.endswith('/USDT'):
                            new_listings.append(f"{sym} on {ex.id}")
                            if self.notifier:
                                await self.notifier.send_new_listing(sym, ex.id)
                                
                self.known_markets[ex.id] = current_symbols
                
            if new_listings:
                self._save_cache()
                
            return new_listings
            
        except Exception as e:
            logger.error(f"Error checking new listings: {e}")
            return []
