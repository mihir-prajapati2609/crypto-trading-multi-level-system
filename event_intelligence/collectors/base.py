"""
Event Intelligence — Base Collector

Abstract base class for all data source collectors.
Provides deduplication, rate limiting, and error handling.
"""

import abc
import asyncio
import hashlib
import logging
import time
from typing import Optional

from event_intelligence.models import NewsEvent

logger = logging.getLogger(__name__)


class BaseCollector(abc.ABC):
    """Abstract base class for event data collectors."""

    def __init__(self, source_name: str, poll_interval: int = 60):
        self.source_name = source_name
        self.poll_interval = poll_interval
        self._seen_hashes: set[str] = set()
        self._max_seen_cache = 10000
        self._last_poll: float = 0
        self._consecutive_errors: int = 0
        self._max_backoff: int = 600  # 10 minutes max backoff
        self._is_running = False

    @abc.abstractmethod
    async def _fetch_events(self) -> list[NewsEvent]:
        """
        Fetch raw events from the data source.
        Subclasses must implement this method.
        Returns a list of NewsEvent objects.
        """
        pass

    def _compute_hash(self, text: str) -> str:
        """Compute a content hash for deduplication."""
        return hashlib.sha256(text.strip().lower().encode()).hexdigest()[:16]

    def _is_duplicate(self, event: NewsEvent) -> bool:
        """Check if this event was already seen."""
        if not event.content_hash:
            event.content_hash = self._compute_hash(event.title + event.source)
        if event.content_hash in self._seen_hashes:
            return True
        self._seen_hashes.add(event.content_hash)
        # Prevent memory leak — trim cache
        if len(self._seen_hashes) > self._max_seen_cache:
            # Remove oldest half
            to_keep = list(self._seen_hashes)[self._max_seen_cache // 2:]
            self._seen_hashes = set(to_keep)
        return False

    def _get_backoff_delay(self) -> float:
        """Calculate exponential backoff delay."""
        if self._consecutive_errors == 0:
            return self.poll_interval
        delay = min(
            self.poll_interval * (2 ** self._consecutive_errors),
            self._max_backoff,
        )
        return delay

    async def collect(self) -> list[NewsEvent]:
        """
        Collect events with deduplication and error handling.
        Returns only new, non-duplicate events.
        """
        try:
            raw_events = await self._fetch_events()
            self._consecutive_errors = 0

            new_events = []
            for event in raw_events:
                event.source = self.source_name
                if not self._is_duplicate(event):
                    new_events.append(event)
                else:
                    event.is_duplicate = True

            if new_events:
                logger.info(
                    f"[{self.source_name}] Collected {len(new_events)} new events "
                    f"(filtered {len(raw_events) - len(new_events)} duplicates)"
                )
            return new_events

        except Exception as e:
            self._consecutive_errors += 1
            backoff = self._get_backoff_delay()
            logger.warning(
                f"[{self.source_name}] Error collecting events "
                f"(attempt {self._consecutive_errors}, backoff {backoff:.0f}s): {e}"
            )
            return []

    async def run_loop(self, event_callback) -> None:
        """
        Continuously poll and deliver events via callback.
        
        Args:
            event_callback: async function(list[NewsEvent]) called with new events.
        """
        self._is_running = True
        logger.info(f"[{self.source_name}] Collector started (interval: {self.poll_interval}s)")

        while self._is_running:
            try:
                events = await self.collect()
                if events:
                    await event_callback(events)
                self._last_poll = time.time()

                delay = self._get_backoff_delay()
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.source_name}] Loop error: {e}")
                await asyncio.sleep(30)

        logger.info(f"[{self.source_name}] Collector stopped")

    def stop(self):
        """Signal the collector to stop."""
        self._is_running = False
