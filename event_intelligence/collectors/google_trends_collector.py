"""
Event Intelligence — Google Trends Collector

Monitors Google Trends for crypto-related search spikes.
Uses direct Google Trends API via aiohttp (no pytrends dependency for reliability).
"""

import logging
import time
from typing import Optional

import aiohttp

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent, EventCategory

logger = logging.getLogger(__name__)

# Google Trends daily search trends API (public)
GTRENDS_DAILY_URL = "https://trends.google.com/trends/api/dailytrends"


class GoogleTrendsCollector(BaseCollector):
    """Monitors Google Trends for crypto-related search spikes."""

    CRYPTO_KEYWORDS = {
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp", "ripple",
        "dogecoin", "doge", "shiba", "pepe", "cardano", "ada", "polkadot",
        "avalanche", "avax", "polygon", "matic", "chainlink", "link",
        "crypto", "cryptocurrency", "binance", "coinbase", "defi", "nft",
        "altcoin", "memecoin", "stablecoin", "usdt", "usdc",
        "bitcoin etf", "crypto regulation", "sec crypto",
    }

    def __init__(self, poll_interval: int = 600):
        super().__init__(
            source_name="google_trends",
            poll_interval=poll_interval,
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch daily trending searches and filter for crypto-related ones."""
        events = []
        try:
            await self._ensure_session()

            params = {
                "hl": "en-US",
                "tz": "-330",
                "geo": "US",
                "ns": "15",
            }

            async with self._session.get(GTRENDS_DAILY_URL, params=params) as resp:
                if resp.status != 200:
                    logger.debug(f"Google Trends returned {resp.status}")
                    return events
                text = await resp.text()

            # Google Trends returns JSON with a security prefix
            import json
            if text.startswith(")]}',"):
                text = text[5:]
            data = json.loads(text)

            trending_days = data.get("default", {}).get("trendingSearchesDays", [])
            for day in trending_days[:1]:  # Today only
                searches = day.get("trendingSearches", [])
                for search in searches:
                    query = search.get("title", {}).get("query", "").lower()
                    traffic = search.get("formattedTraffic", "0")

                    # Check if this is crypto-related
                    is_crypto = any(kw in query for kw in self.CRYPTO_KEYWORDS)
                    if not is_crypto:
                        # Check related queries too
                        related = search.get("relatedQueries", [])
                        for rq in related:
                            if any(kw in rq.get("query", "").lower() for kw in self.CRYPTO_KEYWORDS):
                                is_crypto = True
                                break

                    if not is_crypto:
                        continue

                    title = f"📈 Google Trends spike: \"{query}\" — {traffic} searches"

                    # Try to extract coin symbols
                    coins = []
                    coin_map = {
                        "bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH",
                        "eth": "ETH", "solana": "SOL", "sol": "SOL",
                        "xrp": "XRP", "ripple": "XRP", "dogecoin": "DOGE",
                        "doge": "DOGE", "pepe": "PEPE", "cardano": "ADA",
                    }
                    for kw, sym in coin_map.items():
                        if kw in query:
                            coins.append(sym)

                    event = NewsEvent(
                        source="google_trends",
                        title=title,
                        body=f"Google search trend spike for '{query}' with {traffic} searches.",
                        url=f"https://trends.google.com/trends/explore?q={query.replace(' ', '+')}",
                        raw_data={"query": query, "traffic": traffic},
                        timestamp=time.time(),
                        category=EventCategory.SOCIAL,
                        affected_coins=coins if coins else ["BTC"],
                    )
                    event.content_hash = self._compute_hash(
                        f"gtrend_{query}_{int(time.time() // 3600)}"
                    )
                    events.append(event)

        except Exception as e:
            logger.debug(f"Error fetching Google Trends: {e}")

        return events

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
