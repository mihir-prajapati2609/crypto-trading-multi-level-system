"""
Event Intelligence — News Agent

Scores events based on:
- Event category impact (listing = high impact, blog = low)
- Source reliability
- Headline sentiment strength
- Category-specific historical patterns
"""

import logging

from event_intelligence.agents.base_agent import BaseAgent
from event_intelligence.models import NewsEvent, AgentVote, EventCategory

logger = logging.getLogger(__name__)

# Expected impact by event category (0-100 scale)
CATEGORY_IMPACT = {
    EventCategory.LISTING: 85,
    EventCategory.DELISTING: 80,
    EventCategory.ETF: 90,
    EventCategory.HACK: 85,
    EventCategory.TOKEN_UNLOCK: 65,
    EventCategory.WHALE_MOVEMENT: 60,
    EventCategory.PROTOCOL_UPGRADE: 55,
    EventCategory.LAWSUIT: 75,
    EventCategory.MACRO: 70,
    EventCategory.SOCIAL: 50,
    EventCategory.PARTNERSHIP: 60,
    EventCategory.AIRDROP: 45,
    EventCategory.BURN: 55,
    EventCategory.FORK: 60,
    EventCategory.OTHER: 30,
}

# Expected direction by category
CATEGORY_DIRECTION = {
    EventCategory.LISTING: "bullish",
    EventCategory.DELISTING: "bearish",
    EventCategory.ETF: "bullish",
    EventCategory.HACK: "bearish",
    EventCategory.TOKEN_UNLOCK: "bearish",
    EventCategory.WHALE_MOVEMENT: "neutral",  # Depends on context
    EventCategory.PROTOCOL_UPGRADE: "bullish",
    EventCategory.LAWSUIT: "bearish",
    EventCategory.MACRO: "neutral",
    EventCategory.SOCIAL: "neutral",
    EventCategory.PARTNERSHIP: "bullish",
    EventCategory.AIRDROP: "bullish",
    EventCategory.BURN: "bullish",
    EventCategory.FORK: "neutral",
    EventCategory.OTHER: "neutral",
}

# Source reliability defaults (0-100)
SOURCE_RELIABILITY = {
    "binance_announcements": 98,
    "coinbase_blog": 95,
    "rss_CoinDesk": 88,
    "rss_Cointelegraph": 82,
    "rss_Decrypt": 85,
    "rss_The Block": 87,
    "coingecko_trending": 70,
    "coinmarketcap_trending": 68,
    "github_releases": 92,
    "fear_greed_index": 75,
    "google_trends": 60,
    "onchain_whale": 85,
}


class NewsAgent(BaseAgent):
    """Scores events based on news category, source, and headline analysis."""

    def __init__(self, weight: float = 0.25):
        super().__init__(name="news_agent", weight=weight)

    async def score(self, event: NewsEvent, market_context: dict) -> AgentVote:
        """Score based on category impact and source reliability."""

        # Category impact score
        category_score = CATEGORY_IMPACT.get(event.category, 30)

        # Source reliability
        source_score = self._get_source_reliability(event.source, market_context)

        # Sentiment strength (distance from neutral)
        sentiment_strength = abs(event.sentiment_score - 50) * 2  # 0-100
        sentiment_direction = "bullish" if event.sentiment_score > 55 else \
                              "bearish" if event.sentiment_score < 45 else "neutral"

        # Category-based direction override
        default_direction = CATEGORY_DIRECTION.get(event.category, "neutral")
        if default_direction != "neutral":
            direction = default_direction
        else:
            direction = sentiment_direction

        # Number of affected coins increases relevance
        coin_bonus = min(len(event.affected_coins) * 5, 15)

        # Final score: weighted combination
        score = (
            category_score * 0.40 +
            source_score * 0.25 +
            sentiment_strength * 0.20 +
            coin_bonus * 0.15
        )

        # Confidence based on how much info we have
        confidence = min(95, (
            (30 if event.category != EventCategory.OTHER else 10) +
            (25 if source_score > 70 else 10) +
            (20 if event.affected_coins else 5) +
            (20 if len(event.body) > 50 else 10)
        ))

        reasoning = (
            f"Category: {event.category.value} (impact={category_score}), "
            f"Source: {event.source} (reliability={source_score:.0f}%), "
            f"Sentiment: {event.sentiment_score:.0f}/100"
        )

        return self._create_vote(score, confidence, direction, reasoning)

    def _get_source_reliability(self, source: str, market_context: dict) -> float:
        """Get source reliability from DB history or defaults."""
        # Check if we have learned reliability from feedback
        source_stats = market_context.get("source_reliabilities", {})
        if source in source_stats:
            return source_stats[source]

        # Check default by prefix match
        for key, value in SOURCE_RELIABILITY.items():
            if source.startswith(key) or key in source:
                return value

        return 50.0  # Unknown source
