"""
Event Intelligence — Technical Agent

Scores based on:
- Current price level relative to recent range
- Volume confirmation
- Basic technical indicator readings (RSI, momentum)
- Order book depth
"""

import logging

from event_intelligence.agents.base_agent import BaseAgent
from event_intelligence.models import NewsEvent, AgentVote, VolumeLevel

logger = logging.getLogger(__name__)


class TechnicalAgent(BaseAgent):
    """Scores events using technical analysis context."""

    def __init__(self, weight: float = 0.20):
        super().__init__(name="technical_agent", weight=weight)

    async def score(self, event: NewsEvent, market_context: dict) -> AgentVote:
        """Score based on technical analysis of affected coins."""

        score = 50.0
        direction = "neutral"
        volume_level = VolumeLevel.NORMAL
        confidence = 40.0  # Base confidence

        for coin in event.affected_coins:
            ticker_data = market_context.get("tickers", {}).get(coin, {})
            if not ticker_data:
                continue

            # Volume analysis
            volume_24h = ticker_data.get("quote_volume", 0)
            avg_volume = ticker_data.get("avg_volume_7d", volume_24h)
            if avg_volume > 0:
                volume_ratio = volume_24h / avg_volume
                if volume_ratio > 3.0:
                    volume_level = VolumeLevel.EXTREME
                    score += 15
                elif volume_ratio > 2.0:
                    volume_level = VolumeLevel.VERY_HIGH
                    score += 10
                elif volume_ratio > 1.5:
                    volume_level = VolumeLevel.HIGH
                    score += 5
                elif volume_ratio < 0.5:
                    volume_level = VolumeLevel.LOW
                    score -= 5

            # Price change momentum
            change_24h = ticker_data.get("change_pct", 0)
            if change_24h > 10:
                score += 10
                direction = "bullish"
            elif change_24h > 5:
                score += 5
                direction = "bullish"
            elif change_24h < -10:
                score -= 10
                direction = "bearish"
            elif change_24h < -5:
                score -= 5
                direction = "bearish"

            # RSI context (if available)
            rsi = ticker_data.get("rsi_14", 50)
            if rsi > 70:
                # Overbought — bullish event might still push higher,
                # but risk is elevated
                score -= 5
            elif rsi < 30:
                # Oversold — bullish event could trigger strong bounce
                if event.sentiment_score > 55:
                    score += 10
                    direction = "bullish"

            confidence = min(85, confidence + 20)  # Have data → higher confidence
            break  # Use first available coin data

        # If sentiment and technicals agree, boost score
        if event.sentiment_score > 60 and direction == "bullish":
            score += 5
        elif event.sentiment_score < 40 and direction == "bearish":
            score -= 5

        score = max(0, min(100, score))

        reasoning = (
            f"Volume: {volume_level.value}, "
            f"Direction: {direction}, "
            f"Has price data: {'Yes' if confidence > 50 else 'No'}"
        )

        return self._create_vote(score, confidence, direction, reasoning)
