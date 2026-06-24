"""
Event Intelligence — CoinMarketCap Collector

Scrapes CoinMarketCap for trending/most visited coins and news.
"""

import logging
import time
from typing import Optional

import aiohttp

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent, EventCategory

logger = logging.getLogger(__name__)

CMC_TRENDING_URL = "https://api.coinmarketcap.com/data-api/v3/topsearch/trending"


class CoinMarketCapCollector(BaseCollector):
    """Collects trending coin data from CoinMarketCap."""

    def __init__(self, poll_interval: int = 120):
        super().__init__(
            source_name="coinmarketcap",
            poll_interval=poll_interval,
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            )

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch trending coins from CMC."""
        events = []
        try:
            await self._ensure_session()
            async with self._session.get(CMC_TRENDING_URL) as resp:
                if resp.status != 200:
                    return events
                data = await resp.json()

            trending = data.get("data", {}).get("trendingList", [])
            for item in trending[:10]:
                name = item.get("name", "")
                symbol = item.get("symbol", "").upper()
                if not symbol:
                    continue

                slug = item.get("slug", "")
                price_change = item.get("priceChange", {})
                change_24h = price_change.get("priceChange24h", 0)

                title = f"📊 {symbol} trending on CoinMarketCap"
                if abs(change_24h) > 5:
                    title += f" — {change_24h:+.1f}% 24h"

                event = NewsEvent(
                    source="coinmarketcap_trending",
                    title=title,
                    body=f"{name} ({symbol}) is trending on CoinMarketCap.",
                    url=f"https://coinmarketcap.com/currencies/{slug}/" if slug else "",
                    raw_data={
                        "symbol": symbol,
                        "slug": slug,
                        "price_change_24h": change_24h,
                    },
                    timestamp=time.time(),
                    category=EventCategory.SOCIAL,
                    affected_coins=[symbol],
                )
                event.content_hash = self._compute_hash(
                    f"cmc_trending_{symbol}_{int(time.time() // 3600)}"
                )
                events.append(event)

        except Exception as e:
            logger.debug(f"Error fetching CMC trending: {e}")

        return events

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
