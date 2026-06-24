"""
Event Intelligence — RSS Feed Collector

Monitors crypto news RSS feeds from CoinDesk, CoinTelegraph, Decrypt, The Block.
"""

import logging
from typing import Optional

import aiohttp
import feedparser

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    """Collects news events from crypto RSS feeds."""

    def __init__(self, feed_urls: list[str], poll_interval: int = 60):
        super().__init__(source_name="rss", poll_interval=poll_interval)
        self.feed_urls = feed_urls
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "CryptoEventBot/1.0"},
            )

    async def _fetch_feed(self, url: str) -> list[NewsEvent]:
        """Fetch and parse a single RSS feed."""
        events = []
        try:
            await self._ensure_session()
            async with self._session.get(url) as response:
                if response.status != 200:
                    logger.debug(f"RSS feed {url} returned {response.status}")
                    return events
                text = await response.text()

            feed = feedparser.parse(text)
            source_name = feed.feed.get("title", url)[:30]

            for entry in feed.entries[:20]:  # Last 20 entries
                title = entry.get("title", "").strip()
                if not title:
                    continue

                body = entry.get("summary", entry.get("description", ""))
                # Strip HTML tags from body
                if body:
                    import re
                    body = re.sub(r"<[^>]+>", " ", body).strip()
                    body = re.sub(r"\s+", " ", body)[:500]

                link = entry.get("link", "")
                published = entry.get("published_parsed")
                import time, calendar
                ts = calendar.timegm(published) if published else time.time()

                event = NewsEvent(
                    source=f"rss_{source_name}",
                    title=title,
                    body=body,
                    url=link,
                    raw_data={"feed_url": url, "feed_title": source_name},
                    timestamp=ts,
                )
                event.content_hash = self._compute_hash(title)
                events.append(event)

        except Exception as e:
            logger.debug(f"Error fetching RSS feed {url}: {e}")

        return events

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch events from all configured RSS feeds."""
        all_events = []
        for url in self.feed_urls:
            events = await self._fetch_feed(url)
            all_events.extend(events)
        return all_events

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
