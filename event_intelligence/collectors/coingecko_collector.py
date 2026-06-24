"""
Event Intelligence — CoinGecko Collector

Uses CoinGecko free API for trending coins, price spikes, and volume anomalies.
"""

import logging
import time
from typing import Optional

import aiohttp

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent, EventCategory

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class CoinGeckoCollector(BaseCollector):
    """Collects trending/volume events from CoinGecko."""

    def __init__(self, api_key: str = "", poll_interval: int = 60):
        super().__init__(
            source_name="coingecko",
            poll_interval=poll_interval,
        )
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            headers = {"User-Agent": "CryptoEventBot/1.0", "Accept": "application/json"}
            if self.api_key:
                headers["x-cg-demo-api-key"] = self.api_key
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers=headers,
            )

    async def _fetch_trending(self) -> list[NewsEvent]:
        """Fetch trending coins from CoinGecko."""
        events = []
        try:
            await self._ensure_session()
            async with self._session.get(f"{COINGECKO_BASE}/search/trending") as resp:
                if resp.status != 200:
                    return events
                data = await resp.json()

            coins = data.get("coins", [])
            for item in coins[:10]:
                coin = item.get("item", {})
                name = coin.get("name", "")
                symbol = coin.get("symbol", "").upper()
                if not symbol:
                    continue

                score = coin.get("score", 0)
                market_cap_rank = coin.get("market_cap_rank", 999)
                price_change_24h = coin.get("data", {}).get(
                    "price_change_percentage_24h", {}
                )
                change_usd = price_change_24h.get("usd", 0) if isinstance(price_change_24h, dict) else 0

                title = f"🔥 {symbol} trending on CoinGecko (rank #{score + 1})"
                if abs(change_usd) > 10:
                    title += f" — {change_usd:+.1f}% in 24h"

                event = NewsEvent(
                    source="coingecko_trending",
                    title=title,
                    body=f"{name} ({symbol}) is trending. Market cap rank: #{market_cap_rank}",
                    url=f"https://www.coingecko.com/en/coins/{coin.get('id', '')}",
                    raw_data={
                        "coin_id": coin.get("id", ""),
                        "symbol": symbol,
                        "market_cap_rank": market_cap_rank,
                        "price_change_24h_usd": change_usd,
                    },
                    timestamp=time.time(),
                    category=EventCategory.SOCIAL,
                    affected_coins=[symbol],
                )
                event.content_hash = self._compute_hash(f"trending_{symbol}_{int(time.time() // 3600)}")
                events.append(event)

        except Exception as e:
            logger.debug(f"Error fetching CoinGecko trending: {e}")

        return events

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch all CoinGecko events."""
        return await self._fetch_trending()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
