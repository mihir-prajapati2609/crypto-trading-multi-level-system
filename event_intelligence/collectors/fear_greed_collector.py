"""
Event Intelligence — Fear & Greed Index Collector

Fetches the Crypto Fear & Greed Index from Alternative.me.
This is a market-wide sentiment indicator, not coin-specific.
"""

import logging
import time
from typing import Optional

import aiohttp

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent, EventCategory

logger = logging.getLogger(__name__)

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1&format=json"


class FearGreedCollector(BaseCollector):
    """Collects the Crypto Fear & Greed Index."""

    def __init__(self, poll_interval: int = 300):
        super().__init__(
            source_name="fear_greed",
            poll_interval=poll_interval,
        )
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_value: Optional[int] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            )

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch the current Fear & Greed Index."""
        events = []
        try:
            await self._ensure_session()
            async with self._session.get(FEAR_GREED_URL) as resp:
                if resp.status != 200:
                    return events
                data = await resp.json()

            fng_data = data.get("data", [{}])[0]
            value = int(fng_data.get("value", 50))
            label = fng_data.get("value_classification", "Neutral")
            ts_str = fng_data.get("timestamp", "")
            ts = int(ts_str) if ts_str else time.time()

            # Only generate event if value changed significantly
            if self._last_value is not None and abs(value - self._last_value) < 5:
                return events

            self._last_value = value

            # Determine if this is noteworthy
            if value <= 20:
                title = f"😱 Extreme Fear! Fear & Greed Index: {value} ({label})"
            elif value <= 35:
                title = f"😰 Fear: Fear & Greed Index: {value} ({label})"
            elif value >= 80:
                title = f"🤑 Extreme Greed! Fear & Greed Index: {value} ({label})"
            elif value >= 65:
                title = f"😊 Greed: Fear & Greed Index: {value} ({label})"
            else:
                title = f"📊 Fear & Greed Index: {value} ({label})"

            event = NewsEvent(
                source="fear_greed_index",
                title=title,
                body=f"The Crypto Fear & Greed Index is at {value}/100 ({label}).",
                url="https://alternative.me/crypto/fear-and-greed-index/",
                raw_data={"value": value, "label": label},
                timestamp=ts,
                category=EventCategory.MACRO,
                affected_coins=["BTC"],  # Market-wide, represented by BTC
            )
            # Hash by date so we don't re-report the same day
            event.content_hash = self._compute_hash(
                f"fng_{value}_{int(time.time() // 3600)}"
            )
            events.append(event)

        except Exception as e:
            logger.debug(f"Error fetching Fear & Greed Index: {e}")

        return events

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
