import logging
import asyncio
from typing import List
from data.models import CoinScore
from config.settings import get_settings

logger = logging.getLogger(__name__)

class WatchlistManager:
    """Manages the active coin watchlist."""
    
    def __init__(self):
        self.settings = get_settings().discovery
        self.watchlist: List[str] = []
        self._lock = asyncio.Lock()

    async def update(self, scores: List[CoinScore]):
        """Updates watchlist based on top scores."""
        async with self._lock:
            self.watchlist = [s.symbol for s in scores[:self.settings.watchlist_size]]
            logger.info(f"Watchlist updated with {len(self.watchlist)} coins.")

    async def get_watchlist(self) -> List[str]:
        async with self._lock:
            return list(self.watchlist)

    async def add_priority(self, symbol: str):
        async with self._lock:
            if symbol not in self.watchlist:
                self.watchlist.insert(0, symbol)
                if len(self.watchlist) > self.settings.watchlist_size + 5:
                    self.watchlist.pop()

    async def remove(self, symbol: str):
        async with self._lock:
            if symbol in self.watchlist:
                self.watchlist.remove(symbol)
