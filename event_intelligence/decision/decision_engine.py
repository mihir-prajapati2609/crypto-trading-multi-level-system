"""
Event Intelligence — Central Decision Engine

Aggregates all agent votes into a final score card and trade signal.
This is the brain of the event intelligence system.
"""

import logging
import time
from typing import Optional

from event_intelligence.models import (
    NewsEvent, EventScore, EventTradeSignal, AgentVote,
    TradeAction, VolumeLevel, WhaleActivity, SocialTrend,
    EventCategory,
)
from event_intelligence.agents.news_agent import NewsAgent
from event_intelligence.agents.sentiment_agent import SentimentAgent
from event_intelligence.agents.whale_agent import WhaleAgent
from event_intelligence.agents.technical_agent import TechnicalAgent
from event_intelligence.agents.risk_agent import RiskAgent
from event_intelligence.decision.historical_analyzer import HistoricalAnalyzer
from event_intelligence.decision.impact_model import ImpactModel
from event_intelligence.database import EventDatabase
from event_intelligence.config import EventIntelligenceConfig

logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Central decision engine that orchestrates multi-agent scoring
    and generates final trade signals.
    """

    def __init__(self, db: EventDatabase, config: EventIntelligenceConfig):
        self.db = db
        self.config = config

        # Initialize agents
        self.agents = [
            NewsAgent(weight=config.scoring.news_agent_weight),
            SentimentAgent(weight=config.scoring.sentiment_agent_weight),
            WhaleAgent(weight=config.scoring.whale_agent_weight),
            TechnicalAgent(weight=config.scoring.technical_agent_weight),
            RiskAgent(weight=config.scoring.risk_agent_weight),
        ]

        # ML components
        self.historical_analyzer = HistoricalAnalyzer(db)
        self.impact_model = ImpactModel()

        # Market context (updated externally)
        self._market_context: dict = {
            "tickers": {},
            "fear_greed_value": 50,
            "btc_change_24h": 0,
            "recent_win_rate": 50,
            "current_drawdown_pct": 0,
            "max_drawdown_pct": config.risk.max_drawdown_pct,
            "daily_loss_pct": 0,
            "max_daily_loss_pct": config.risk.max_daily_loss_pct,
            "open_trades": 0,
            "max_open_trades": config.risk.max_open_trades,
            "source_reliabilities": {},
            "recent_whale_events": [],
        }

    def update_market_context(self, updates: dict):
        """Update market context data (called by engine)."""
        self._market_context.update(updates)

    async def score_event(self, event: NewsEvent) -> EventScore:
        """
        Run all agents on an event and produce a final score card.

        This is the core scoring pipeline:
        1. Each agent votes independently
        2. Votes are aggregated with weights
        3. Historical impact is queried
        4. ML model provides additional prediction
        5. Final confidence and trade action are determined
        """

        # Collect agent votes
        votes: list[AgentVote] = []
        for agent in self.agents:
            try:
                vote = await agent.score(event, self._market_context)
                votes.append(vote)
            except Exception as e:
                logger.error(f"Agent {agent.name} failed: {e}")
                # Agent failure → neutral vote with low confidence
                votes.append(AgentVote(
                    agent_name=agent.name,
                    score=50, confidence=10, direction="neutral",
                    reasoning=f"Error: {str(e)[:50]}",
                    weight=agent.weight,
                ))

        # Weighted aggregate score
        total_weight = sum(v.weight for v in votes)
        if total_weight == 0:
            total_weight = 1.0

        weighted_score = sum(v.score * v.weight for v in votes) / total_weight
        weighted_confidence = sum(v.confidence * v.weight for v in votes) / total_weight

        # Determine consensus direction
        direction_scores = {"bullish": 0, "bearish": 0, "neutral": 0}
        for v in votes:
            direction_scores[v.direction] += v.weight * v.confidence

        consensus_direction = max(direction_scores, key=direction_scores.get)

        # Get historical impact score
        historical_score = await self.historical_analyzer.get_historical_score(
            event.category.value
        )

        # ML model prediction
        model_input = {
            "category": event.category.value,
            "news_sentiment": event.sentiment_score,
            "source_reliability": self._get_source_reliability_for_event(event),
            "historical_impact": historical_score,
            "current_volume": self._assess_volume(event).value,
            "whale_activity": self._assess_whale(event).value,
            "social_trend": self._assess_social(event).value,
            "num_affected_coins": len(event.affected_coins),
        }
        ml_prediction = self.impact_model.predict(model_input)

        # Final AI confidence (blend agent consensus + ML + historical)
        ai_confidence = (
            weighted_confidence * 0.40 +
            ml_prediction.get("confidence", 50) * 0.30 +
            historical_score * 0.30
        )

        # Determine trade action
        trade_action = self._determine_trade_action(
            ai_confidence, consensus_direction, weighted_score
        )

        # Build score card
        score = EventScore(
            event_id=event.id,
            coin=event.affected_coins[0] if event.affected_coins else "UNKNOWN",
            news_sentiment=event.sentiment_score,
            source_reliability=self._get_source_reliability_for_event(event),
            historical_impact=historical_score,
            current_volume=self._assess_volume(event),
            whale_activity=self._assess_whale(event),
            social_trend=self._assess_social(event),
            ai_confidence=round(ai_confidence, 1),
            trade_action=trade_action,
            agent_votes=votes,
            category=event.category,
        )

        # Save to DB
        await self.db.save_score(score)

        logger.info(
            f"📊 Score Card: {score.coin} | "
            f"Confidence: {score.ai_confidence:.0f}% | "
            f"Action: {score.trade_action.value} | "
            f"Sentiment: {score.news_sentiment:.0f} | "
            f"Category: {score.category.value}"
        )

        return score

    async def score_events(self, events: list[NewsEvent]) -> list[EventScore]:
        """Score a batch of events."""
        scores = []
        for event in events:
            if event.affected_coins:  # Only score if we know which coin
                score = await self.score_event(event)
                scores.append(score)
        return scores

    def _determine_trade_action(self, confidence: float, direction: str,
                                 score: float) -> TradeAction:
        """Determine trade action from confidence and direction."""
        if confidence < 50:
            return TradeAction.SKIP

        if confidence >= self.config.scoring.min_confidence_to_trade:
            if direction == "bullish" and score >= 70:
                return TradeAction.STRONG_BUY
            elif direction == "bullish":
                return TradeAction.BUY
            elif direction == "bearish" and score <= 30:
                return TradeAction.STRONG_SELL
            elif direction == "bearish":
                return TradeAction.SELL
        elif confidence >= self.config.scoring.min_confidence_to_alert:
            if direction == "bullish":
                return TradeAction.BUY
            elif direction == "bearish":
                return TradeAction.SELL

        return TradeAction.HOLD

    def _get_source_reliability_for_event(self, event: NewsEvent) -> float:
        """Get source reliability score for this event's source."""
        reliabilities = self._market_context.get("source_reliabilities", {})
        if event.source in reliabilities:
            return reliabilities[event.source]
        # Defaults by source type
        defaults = {
            "binance": 98, "coinbase": 95, "github": 92,
            "rss": 80, "coingecko": 70, "coinmarketcap": 68,
            "fear_greed": 75, "google_trends": 60, "onchain": 85,
        }
        for key, val in defaults.items():
            if key in event.source:
                return val
        return 50.0

    def _assess_volume(self, event: NewsEvent) -> VolumeLevel:
        """Assess current volume level from market context."""
        tickers = self._market_context.get("tickers", {})
        for coin in event.affected_coins:
            ticker = tickers.get(coin, {})
            vol_ratio = ticker.get("volume_ratio", 1.0)
            if vol_ratio > 3:
                return VolumeLevel.EXTREME
            elif vol_ratio > 2:
                return VolumeLevel.VERY_HIGH
            elif vol_ratio > 1.5:
                return VolumeLevel.HIGH
            elif vol_ratio < 0.5:
                return VolumeLevel.LOW
        return VolumeLevel.NORMAL

    def _assess_whale(self, event: NewsEvent) -> WhaleActivity:
        """Assess whale activity from market context."""
        recent_whale = self._market_context.get("recent_whale_events", [])
        if not recent_whale:
            return WhaleActivity.NEUTRAL

        bullish = sum(1 for w in recent_whale if w.get("direction") == "bullish")
        bearish = sum(1 for w in recent_whale if w.get("direction") == "bearish")

        if bullish > bearish + 2:
            return WhaleActivity.STRONG_ACCUMULATION
        elif bullish > bearish:
            return WhaleActivity.ACCUMULATION
        elif bearish > bullish + 2:
            return WhaleActivity.STRONG_DISTRIBUTION
        elif bearish > bullish:
            return WhaleActivity.DISTRIBUTION
        return WhaleActivity.NEUTRAL

    def _assess_social(self, event: NewsEvent) -> SocialTrend:
        """Assess social trend from event source and context."""
        if "trending" in event.source or "google_trends" in event.source:
            if event.sentiment_score > 70:
                return SocialTrend.EXPLODING
            return SocialTrend.TRENDING
        elif "social" in event.source:
            return SocialTrend.RISING
        return SocialTrend.STABLE
