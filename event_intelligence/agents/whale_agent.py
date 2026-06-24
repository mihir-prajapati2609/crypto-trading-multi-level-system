"""
Event Intelligence — Whale Agent

Scores based on:
- On-chain whale wallet movements
- Exchange inflow/outflow patterns
- Accumulation vs distribution signals
"""

import logging

from event_intelligence.agents.base_agent import BaseAgent
from event_intelligence.models import (
    NewsEvent, AgentVote, EventCategory, WhaleActivity,
)

logger = logging.getLogger(__name__)


class WhaleAgent(BaseAgent):
    """Scores events based on whale and on-chain activity."""

    def __init__(self, weight: float = 0.20):
        super().__init__(name="whale_agent", weight=weight)
        self._whale_events_cache: list[dict] = []

    async def score(self, event: NewsEvent, market_context: dict) -> AgentVote:
        """Score based on whale activity context."""

        score = 50.0
        direction = "neutral"
        whale_activity = WhaleActivity.NEUTRAL

        # Direct whale event
        if event.category == EventCategory.WHALE_MOVEMENT:
            raw = event.raw_data
            value_eth = raw.get("value_eth", 0)
            direction_text = raw.get("direction", "")

            # Large deposit to exchange = bearish (likely selling)
            if "potential sell" in direction_text:
                score = 30.0
                direction = "bearish"
                whale_activity = WhaleActivity.DISTRIBUTION
            # Withdrawal from exchange = bullish (accumulating)
            elif "potential buy" in direction_text or "hold" in direction_text:
                score = 75.0
                direction = "bullish"
                whale_activity = WhaleActivity.ACCUMULATION
            else:
                score = 50.0

            # Scale by size
            if value_eth > 1000:
                score = score + (10 if direction == "bullish" else -10)
            if value_eth > 5000:
                score = score + (10 if direction == "bullish" else -10)

        else:
            # For non-whale events, check recent whale context
            recent_whale = market_context.get("recent_whale_events", [])
            if recent_whale:
                bullish_count = sum(
                    1 for w in recent_whale
                    if w.get("direction") == "bullish"
                )
                bearish_count = sum(
                    1 for w in recent_whale
                    if w.get("direction") == "bearish"
                )
                if bullish_count > bearish_count:
                    score = 60 + min(bullish_count * 5, 20)
                    direction = "bullish"
                    whale_activity = WhaleActivity.ACCUMULATION
                elif bearish_count > bullish_count:
                    score = 40 - min(bearish_count * 5, 20)
                    direction = "bearish"
                    whale_activity = WhaleActivity.DISTRIBUTION
                else:
                    score = 50
            else:
                # No whale data — low confidence neutral
                score = 50
                direction = "neutral"

        score = max(0, min(100, score))

        # Confidence depends on whether we have whale data
        has_whale_data = (
            event.category == EventCategory.WHALE_MOVEMENT or
            bool(market_context.get("recent_whale_events"))
        )
        confidence = 70 if has_whale_data else 30

        reasoning = (
            f"Whale activity: {whale_activity.value}, "
            f"Direction: {direction}, "
            f"Has on-chain data: {'Yes' if has_whale_data else 'No'}"
        )

        return self._create_vote(score, confidence, direction, reasoning)
