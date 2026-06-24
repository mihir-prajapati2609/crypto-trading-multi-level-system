"""
Event Intelligence — Sentiment Agent

Scores based on:
- NLP sentiment from multiple sources
- Social media buzz (trending status)
- Sentiment momentum (improving or declining)
"""

import logging

from event_intelligence.agents.base_agent import BaseAgent
from event_intelligence.models import NewsEvent, AgentVote, EventCategory

logger = logging.getLogger(__name__)


class SentimentAgent(BaseAgent):
    """Scores events based on overall sentiment signals."""

    def __init__(self, weight: float = 0.20):
        super().__init__(name="sentiment_agent", weight=weight)
        self._sentiment_history: dict[str, list[float]] = {}  # coin -> recent sentiments

    async def score(self, event: NewsEvent, market_context: dict) -> AgentVote:
        """Score based on sentiment analysis and momentum."""

        # Raw sentiment score from NLP pipeline
        sentiment_score = event.sentiment_score

        # Determine sentiment direction
        if sentiment_score >= 70:
            direction = "bullish"
        elif sentiment_score <= 30:
            direction = "bearish"
        else:
            direction = "neutral"

        # Calculate sentiment momentum (is sentiment improving or declining?)
        momentum_score = 50.0
        for coin in event.affected_coins:
            if coin in self._sentiment_history:
                history = self._sentiment_history[coin]
                if len(history) >= 2:
                    recent_avg = sum(history[-3:]) / len(history[-3:])
                    older_avg = sum(history[:-3]) / max(len(history[:-3]), 1) if len(history) > 3 else recent_avg
                    momentum = recent_avg - older_avg
                    momentum_score = 50 + momentum  # Center around 50

            # Update history
            if coin not in self._sentiment_history:
                self._sentiment_history[coin] = []
            self._sentiment_history[coin].append(sentiment_score)
            # Keep last 20
            self._sentiment_history[coin] = self._sentiment_history[coin][-20:]

        # Social trend bonus
        social_bonus = 0
        is_trending = any(
            kw in event.source for kw in ["trending", "google_trends", "social"]
        )
        if is_trending:
            social_bonus = 15

        # Strong sentiment bonus (very polarized = more actionable)
        polarization = abs(sentiment_score - 50) / 50  # 0 to 1
        polarization_bonus = polarization * 20

        # Final score
        score = (
            sentiment_score * 0.45 +
            momentum_score * 0.20 +
            polarization_bonus * 0.20 +
            social_bonus * 0.15
        )

        # Confidence: high sentiment polarity = higher confidence
        confidence = min(95, 40 + polarization * 50)

        reasoning = (
            f"Sentiment: {sentiment_score:.0f}/100, "
            f"Momentum: {momentum_score:.0f}, "
            f"Polarization: {polarization:.2f}, "
            f"Trending: {'Yes' if is_trending else 'No'}"
        )

        return self._create_vote(score, confidence, direction, reasoning)
