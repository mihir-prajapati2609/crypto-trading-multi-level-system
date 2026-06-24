"""
Event Intelligence — Binance Announcements Collector

Monitors Binance announcements for listing, delisting, and maintenance events.
This is the most time-critical collector (new listings can spike within seconds).
"""

import logging
import time
from typing import Optional

import aiohttp

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent, EventCategory

logger = logging.getLogger(__name__)

# Binance announcement API endpoint
BINANCE_ANNOUNCE_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"


class BinanceAnnouncementCollector(BaseCollector):
    """Collects listing/delisting events from Binance announcements."""

    def __init__(self, poll_interval: int = 30):
        super().__init__(
            source_name="binance_announcements",
            poll_interval=poll_interval,
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Content-Type": "application/json",
                },
            )

    def _categorize_announcement(self, title: str) -> EventCategory:
        """Categorize a Binance announcement by its title."""
        title_lower = title.lower()

        if any(kw in title_lower for kw in ["will list", "lists", "new listing", "adds"]):
            return EventCategory.LISTING
        elif any(kw in title_lower for kw in ["delist", "remove", "removal"]):
            return EventCategory.DELISTING
        elif any(kw in title_lower for kw in ["airdrop", "distribution"]):
            return EventCategory.AIRDROP
        elif any(kw in title_lower for kw in ["fork", "hard fork"]):
            return EventCategory.FORK
        elif any(kw in title_lower for kw in ["upgrade", "migration", "mainnet"]):
            return EventCategory.PROTOCOL_UPGRADE
        elif any(kw in title_lower for kw in ["burn", "burning"]):
            return EventCategory.BURN
        else:
            return EventCategory.OTHER

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch recent Binance announcements."""
        events = []
        try:
            await self._ensure_session()

            # Query the Binance announcement catalog
            payload = {
                "type": 1,
                "catalogId": 48,  # New Cryptocurrency Listing
                "pageNo": 1,
                "pageSize": 20,
            }

            async with self._session.post(BINANCE_ANNOUNCE_URL, json=payload) as resp:
                if resp.status != 200:
                    logger.debug(f"Binance announcements returned {resp.status}")
                    return events
                data = await resp.json()

            articles = data.get("data", {}).get("catalogs", [{}])
            if articles:
                article_list = articles[0].get("articles", [])
            else:
                article_list = []

            for article in article_list:
                title = article.get("title", "").strip()
                if not title:
                    continue

                release_date = article.get("releaseDate", 0)
                ts = release_date / 1000 if release_date > 1e12 else release_date
                if ts == 0:
                    ts = time.time()

                code = article.get("code", "")
                url = f"https://www.binance.com/en/support/announcement/{code}" if code else ""

                category = self._categorize_announcement(title)

                event = NewsEvent(
                    source="binance_announcements",
                    title=title,
                    url=url,
                    raw_data={"article_code": code, "catalog_id": 48},
                    timestamp=ts,
                    category=category,
                )
                event.content_hash = self._compute_hash(title)
                events.append(event)

            # Also check delisting catalog
            payload["catalogId"] = 161  # Delisting
            try:
                async with self._session.post(BINANCE_ANNOUNCE_URL, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        articles = data.get("data", {}).get("catalogs", [{}])
                        if articles:
                            for article in articles[0].get("articles", [])[:10]:
                                title = article.get("title", "").strip()
                                if not title:
                                    continue
                                release_date = article.get("releaseDate", 0)
                                ts = release_date / 1000 if release_date > 1e12 else release_date
                                code = article.get("code", "")
                                url = f"https://www.binance.com/en/support/announcement/{code}" if code else ""
                                event = NewsEvent(
                                    source="binance_announcements",
                                    title=title,
                                    url=url,
                                    raw_data={"article_code": code, "catalog_id": 161},
                                    timestamp=ts if ts else time.time(),
                                    category=EventCategory.DELISTING,
                                )
                                event.content_hash = self._compute_hash(title)
                                events.append(event)
            except Exception:
                pass  # Delisting catalog is optional

        except Exception as e:
            logger.debug(f"Error fetching Binance announcements: {e}")

        return events

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
