"""
Event Intelligence — Risk Agent

Evaluates risk factors:
- Market-wide conditions (Fear & Greed, BTC trend)
- Liquidity assessment
- Correlation with recent failed signals
- Drawdown proximity
"""

import logging

from event_intelligence.agents.base_agent import BaseAgent
from event_intelligence.models import NewsEvent, AgentVote, EventCategory

logger = logging.getLogger(__name__)


class RiskAgent(BaseAgent):
    """Evaluates risk conditions and can reduce or reject signals."""

    def __init__(self, weight: float = 0.15):
        super().__init__(name="risk_agent", weight=weight)

    async def score(self, event: NewsEvent, market_context: dict) -> AgentVote:
        """
        Score from a risk perspective.
        Higher score = lower risk (safe to trade).
        Lower score = higher risk (should reduce position or skip).
        """

        risk_score = 70.0  # Start moderately safe
        direction = "neutral"
        risk_factors = []

        # Factor 1: Fear & Greed Index
        fng_value = market_context.get("fear_greed_value", 50)
        if fng_value <= 20:
            risk_score -= 15
            risk_factors.append(f"Extreme Fear ({fng_value})")
        elif fng_value <= 35:
            risk_score -= 5
            risk_factors.append(f"Fear ({fng_value})")
        elif fng_value >= 80:
            risk_score -= 10  # Extreme greed is also risky (bubble territory)
            risk_factors.append(f"Extreme Greed ({fng_value})")
        elif fng_value >= 65:
            risk_score += 5

        # Factor 2: BTC trend (if BTC is crashing, risky for all alts)
        btc_change = market_context.get("btc_change_24h", 0)
        if btc_change < -5:
            risk_score -= 15
            risk_factors.append(f"BTC down {btc_change:.1f}%")
        elif btc_change < -2:
            risk_score -= 5
            risk_factors.append(f"BTC declining {btc_change:.1f}%")
        elif btc_change > 3:
            risk_score += 5

        # Factor 3: Recent trade performance
        recent_win_rate = market_context.get("recent_win_rate", 50)
        if recent_win_rate < 30:
            risk_score -= 15
            risk_factors.append(f"Low win rate ({recent_win_rate:.0f}%)")
        elif recent_win_rate < 40:
            risk_score -= 5

        # Factor 4: Drawdown proximity
        current_drawdown = market_context.get("current_drawdown_pct", 0)
        max_drawdown = market_context.get("max_drawdown_pct", 10)
        if current_drawdown > max_drawdown * 0.8:
            risk_score -= 20
            risk_factors.append(f"Near max drawdown ({current_drawdown:.1f}%/{max_drawdown:.1f}%)")
        elif current_drawdown > max_drawdown * 0.5:
            risk_score -= 10

        # Factor 5: Daily loss proximity
        daily_loss = market_context.get("daily_loss_pct", 0)
        max_daily = market_context.get("max_daily_loss_pct", 3)
        if daily_loss > max_daily * 0.8:
            risk_score -= 20
            risk_factors.append(f"Near daily loss limit ({daily_loss:.1f}%/{max_daily:.1f}%)")

        # Factor 6: Open positions
        open_trades = market_context.get("open_trades", 0)
        max_trades = market_context.get("max_open_trades", 5)
        if open_trades >= max_trades:
            risk_score = 0  # Can't trade
            risk_factors.append(f"Max positions reached ({open_trades}/{max_trades})")
        elif open_trades >= max_trades - 1:
            risk_score -= 10
            risk_factors.append(f"Almost full ({open_trades}/{max_trades})")

        # Factor 7: Event type risk
        high_risk_events = {EventCategory.HACK, EventCategory.DELISTING, EventCategory.LAWSUIT}
        if event.category in high_risk_events:
            # These events need extra caution
            risk_score -= 5
            risk_factors.append(f"High-risk event type: {event.category.value}")

        # Determine direction based on risk assessment
        if risk_score >= 60:
            direction = "bullish" if event.sentiment_score > 50 else "bearish"
        else:
            direction = "neutral"  # Too risky to take a position

        risk_score = max(0, min(100, risk_score))
        confidence = min(90, 50 + len(risk_factors) * 10)

        reasoning = (
            f"Risk score: {risk_score:.0f}/100, "
            f"Factors: {', '.join(risk_factors) if risk_factors else 'None'}"
        )

        return self._create_vote(risk_score, confidence, direction, reasoning)
