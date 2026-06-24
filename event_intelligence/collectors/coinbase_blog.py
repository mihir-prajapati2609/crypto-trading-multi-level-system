"""
Event Intelligence — Coinbase Blog Collector

Monitors Coinbase blog/announcements for new listing events.
"""

import logging
import time
from typing import Optional

import aiohttp

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent, EventCategory

logger = logging.getLogger(__name__)

COINBASE_BLOG_RSS = "https://www.coinbase.com/blog/rss.xml"


class CoinbaseBlogCollector(BaseCollector):
    """Collects events from Coinbase blog and asset listings."""

    def __init__(self, poll_interval: int = 120):
        super().__init__(
            source_name="coinbase_blog",
            poll_interval=poll_interval,
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "CryptoEventBot/1.0"},
            )

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch events from Coinbase blog RSS."""
        events = []
        try:
            await self._ensure_session()
            import feedparser

            async with self._session.get(COINBASE_BLOG_RSS) as resp:
                if resp.status != 200:
                    return events
                text = await resp.text()

            feed = feedparser.parse(text)
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                body = entry.get("summary", "")
                if body:
                    import re
                    body = re.sub(r"<[^>]+>", " ", body).strip()[:500]

                link = entry.get("link", "")
                published = entry.get("published_parsed")
                import calendar
                ts = calendar.timegm(published) if published else time.time()

                # Categorize
                title_lower = title.lower()
                if any(kw in title_lower for kw in ["listing", "adds", "launches", "now available"]):
                    category = EventCategory.LISTING
                elif "airdrop" in title_lower:
                    category = EventCategory.AIRDROP
                else:
                    category = EventCategory.OTHER

                event = NewsEvent(
                    source="coinbase_blog",
                    title=title,
                    body=body,
                    url=link,
                    timestamp=ts,
                    category=category,
                )
                event.content_hash = self._compute_hash(title)
                events.append(event)

        except Exception as e:
            logger.debug(f"Error fetching Coinbase blog: {e}")

        return events

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
