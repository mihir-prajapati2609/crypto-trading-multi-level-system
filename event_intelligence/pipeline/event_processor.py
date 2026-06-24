"""
Event Intelligence — Central Event Processor

Orchestrates the NLP pipeline:
1. Receives raw NewsEvent from collectors
2. Deduplicates across sources
3. Classifies category via NLP
4. Extracts coins/entities
5. Scores sentiment
6. Dispatches to multi-agent scoring
"""

import asyncio
import logging
import time
from typing import Callable, Optional

from event_intelligence.models import NewsEvent, EventScore
from event_intelligence.pipeline.nlp_classifier import NLPClassifier
from event_intelligence.pipeline.sentiment_analyzer import SentimentAnalyzer
from event_intelligence.pipeline.entity_extractor import EntityExtractor
from event_intelligence.database import EventDatabase

logger = logging.getLogger(__name__)


class EventProcessor:
    """Central pipeline that processes raw events through NLP stages."""

    def __init__(self, db: EventDatabase):
        self.db = db
        self.classifier = NLPClassifier()
        self.sentiment = SentimentAnalyzer()
        self.extractor = EntityExtractor()

        # Callback for scoring (set by engine)
        self._score_callback: Optional[Callable] = None

        # Rate limiting
        self._events_this_minute: int = 0
        self._minute_start: float = time.time()
        self._max_per_minute: int = 100

        # Stats
        self.total_processed: int = 0
        self.total_duplicates: int = 0

    def set_score_callback(self, callback: Callable):
        """Set the callback function for scoring processed events."""
        self._score_callback = callback

    async def process_events(self, events: list[NewsEvent]) -> list[NewsEvent]:
        """
        Process a batch of raw events through the NLP pipeline.
        Returns only new, fully-processed events.
        """
        processed = []

        for event in events:
            # Rate limiting
            now = time.time()
            if now - self._minute_start > 60:
                self._events_this_minute = 0
                self._minute_start = now
            if self._events_this_minute >= self._max_per_minute:
                logger.warning("Event rate limit reached, skipping events")
                break
            self._events_this_minute += 1

            try:
                # Check for cross-source duplicates in DB
                if event.content_hash and await self.db.event_hash_exists(event.content_hash):
                    event.is_duplicate = True
                    self.total_duplicates += 1
                    continue

                # Stage 1: Classify category
                if event.category.value == "other":
                    event.category = self.classifier.classify(event.title, event.body)

                # Stage 2: Extract entities
                full_text = f"{event.title} {event.body}"
                entities = self.extractor.extract_all(full_text)
                if not event.affected_coins and entities["coins"]:
                    event.affected_coins = entities["coins"]

                # Stage 3: Sentiment analysis
                event.sentiment_score = self.sentiment.analyze(event.title, event.body)
                event.sentiment = self.sentiment.score_to_sentiment(event.sentiment_score)

                # Save to DB
                await self.db.save_event(event)
                self.total_processed += 1

                processed.append(event)

                logger.info(
                    f"Processed event: [{event.category.value}] {event.title[:80]} "
                    f"| Sentiment: {event.sentiment_score:.0f} "
                    f"| Coins: {event.affected_coins}"
                )

            except Exception as e:
                logger.error(f"Error processing event '{event.title[:50]}': {e}")

        # Dispatch processed events for scoring
        if processed and self._score_callback:
            try:
                await self._score_callback(processed)
            except Exception as e:
                logger.error(f"Error in score callback: {e}")

        return processed
