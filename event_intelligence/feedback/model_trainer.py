"""
Event Intelligence — Model Trainer

Periodic model retraining:
- Retrains LightGBM impact model on new feedback data
- Updates agent weights based on accuracy
- Logs performance metrics
"""

import logging
import time
from typing import Optional

from event_intelligence.database import EventDatabase
from event_intelligence.decision.impact_model import ImpactModel
from event_intelligence.decision.historical_analyzer import HistoricalAnalyzer
from event_intelligence.models import AgentPerformance

logger = logging.getLogger(__name__)


class ModelTrainer:
    """Handles periodic model retraining from accumulated feedback data."""

    def __init__(self, db: EventDatabase, impact_model: ImpactModel,
                 historical_analyzer: HistoricalAnalyzer):
        self.db = db
        self.impact_model = impact_model
        self.historical_analyzer = historical_analyzer
        self._last_train_time: float = 0

    async def retrain_impact_model(self) -> dict:
        """
        Retrain the impact prediction model from historical data.

        Returns:
            Dict with training metrics.
        """
        try:
            impacts = await self.db.get_all_impacts()
            if len(impacts) < 20:
                logger.info(f"Not enough impact data to retrain ({len(impacts)}/20)")
                return {"status": "skipped", "reason": "insufficient_data"}

            # Prepare training data
            training_data = []
            for imp in impacts:
                # Determine if the event was positive
                changes = [
                    imp.get("change_1m"), imp.get("change_5m"),
                    imp.get("change_30m"), imp.get("change_1h"),
                    imp.get("change_24h"),
                ]
                non_null_changes = [c for c in changes if c is not None]
                if not non_null_changes:
                    continue

                was_positive = sum(1 for c in non_null_changes if c > 0) > len(non_null_changes) / 2

                training_data.append({
                    "category": imp.get("category", "other"),
                    "news_sentiment": imp.get("sentiment_score", 50),
                    "source_reliability": imp.get("source_reliability", 50),
                    "historical_impact": 50,  # Use neutral for training
                    "current_volume": imp.get("pre_event_volume", "normal"),
                    "whale_activity": "neutral",
                    "social_trend": "stable",
                    "num_affected_coins": 1,
                    "was_positive": was_positive,
                })

            metrics = await self.impact_model.train(training_data)
            self._last_train_time = time.time()

            # Rebuild historical profiles too
            await self.historical_analyzer.rebuild_profiles()

            return metrics

        except Exception as e:
            logger.error(f"Error retraining model: {e}")
            return {"status": "error", "reason": str(e)}

    async def calibrate_agent_weights(self, agents: list) -> dict:
        """
        Recalibrate agent weights based on historical accuracy.

        Agents that are more accurate get higher weights.
        """
        try:
            performances = await self.db.get_all_agent_performance()
            if not performances:
                return {"status": "skipped", "reason": "no_performance_data"}

            # Calculate accuracy-based weights
            total_accuracy = 0
            agent_accuracies = {}
            for perf in performances:
                acc = perf.get("avg_score_accuracy", 50)
                agent_accuracies[perf["agent_name"]] = acc
                total_accuracy += acc

            if total_accuracy == 0:
                return {"status": "skipped", "reason": "zero_accuracy"}

            # Normalize weights
            for agent in agents:
                if agent.name in agent_accuracies:
                    new_weight = agent_accuracies[agent.name] / total_accuracy
                    # Smooth adjustment (don't change too drastically)
                    agent.weight = agent.weight * 0.7 + new_weight * 0.3
                    agent.weight = max(0.05, min(0.50, agent.weight))

                    # Save to DB
                    await self.db.update_agent_performance(AgentPerformance(
                        agent_name=agent.name,
                        total_votes=agent._total_votes,
                        correct_direction=agent._correct_votes,
                        avg_score_accuracy=agent.accuracy,
                        current_weight=agent.weight,
                        last_calibration=time.time(),
                    ))

            logger.info(
                f"Agent weights recalibrated: " +
                ", ".join(f"{a.name}={a.weight:.3f}" for a in agents)
            )

            return {
                "status": "calibrated",
                "weights": {a.name: a.weight for a in agents},
            }

        except Exception as e:
            logger.error(f"Error calibrating agent weights: {e}")
            return {"status": "error", "reason": str(e)}
