"""
Event Intelligence — Feedback Loop

After each trade closes:
1. Records actual price impact
2. Compares prediction vs reality
3. Updates source reliability scores
4. Triggers agent weight recalibration
"""

import logging
import time
from typing import Optional

from event_intelligence.models import (
    EventTrade, HistoricalImpact, SourceReliability,
    AgentPerformance, EventCategory,
)
from event_intelligence.database import EventDatabase
from event_intelligence.config import EventIntelligenceConfig

logger = logging.getLogger(__name__)


class FeedbackLoop:
    """Processes trade results to improve future predictions."""

    def __init__(self, db: EventDatabase, config: EventIntelligenceConfig):
        self.db = db
        self.config = config
        self._trades_since_last_retrain: int = 0
        self._retrain_threshold: int = 10  # Retrain after 10 closed trades

    async def process_closed_trade(self, trade: EventTrade):
        """
        Process a closed trade for feedback.
        Records impact data and updates reliability scores.
        """
        try:
            # 1. Record historical impact
            was_profitable = trade.net_pnl_usd > 0
            
            # Get the event's score from DB
            scores = await self.db.get_recent_scores(limit=100)
            event_score = None
            for s in scores:
                if s.get("event_id") == trade.event_id:
                    event_score = s
                    break

            if event_score:
                impact = HistoricalImpact(
                    event_id=trade.event_id,
                    coin=trade.coin,
                    category=EventCategory(event_score.get("category", "other")),
                    price_before=trade.entry_price,
                    sentiment_score=event_score.get("news_sentiment", 50),
                    source_reliability=event_score.get("source_reliability", 50),
                )

                # Calculate actual price change
                if trade.entry_price > 0:
                    change_pct = ((trade.exit_price - trade.entry_price) / trade.entry_price) * 100
                    # Record in the appropriate time bucket based on hold time
                    hold_minutes = (trade.exit_time - trade.entry_time) / 60
                    if hold_minutes <= 2:
                        impact.change_1m = change_pct
                    elif hold_minutes <= 10:
                        impact.change_5m = change_pct
                    elif hold_minutes <= 45:
                        impact.change_30m = change_pct
                    elif hold_minutes <= 120:
                        impact.change_1h = change_pct
                    else:
                        impact.change_24h = change_pct

                await self.db.save_historical_impact(impact)

            # 2. Update source reliability
            if event_score:
                await self._update_source_reliability(
                    trade.event_id, was_profitable
                )

            # 3. Track for model retraining
            self._trades_since_last_retrain += 1

            logger.info(
                f"📊 Feedback recorded for trade {trade.id}: "
                f"{'✅ Profitable' if was_profitable else '❌ Loss'} "
                f"(${trade.net_pnl_usd:+.4f})"
            )

        except Exception as e:
            logger.error(f"Error processing feedback: {e}")

    async def _update_source_reliability(self, event_id: str,
                                          was_accurate: bool):
        """Update source reliability based on trade outcome."""
        try:
            events = await self.db.get_recent_events(limit=200)
            event = None
            for e in events:
                if e.get("id") == event_id:
                    event = e
                    break

            if not event:
                return

            source_name = event.get("source", "unknown")
            existing = await self.db.get_source_reliability(source_name)

            if existing:
                total = existing["total_events"] + 1
                accurate = existing["accurate_predictions"] + (1 if was_accurate else 0)
                reliability = (accurate / total) * 100 if total > 0 else 50
            else:
                total = 1
                accurate = 1 if was_accurate else 0
                reliability = 100 if was_accurate else 0

            await self.db.update_source_reliability(SourceReliability(
                source_name=source_name,
                total_events=total,
                accurate_predictions=accurate,
                reliability_score=reliability,
                avg_impact_accuracy=reliability,
                last_updated=time.time(),
            ))

        except Exception as e:
            logger.error(f"Error updating source reliability: {e}")

    @property
    def needs_retrain(self) -> bool:
        """Check if we have enough new data to retrain the model."""
        return self._trades_since_last_retrain >= self._retrain_threshold

    def reset_retrain_counter(self):
        """Reset the retrain counter after model retraining."""
        self._trades_since_last_retrain = 0
