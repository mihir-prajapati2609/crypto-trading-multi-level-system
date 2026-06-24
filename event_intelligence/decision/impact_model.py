"""
Event Intelligence — ML Impact Prediction Model

LightGBM-based model for predicting event impact:
- Trained on historical event → price impact data
- Features: category, sentiment, volume, source reliability, whale activity
- Predicts: probability of positive move, expected magnitude
"""

import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from event_intelligence.models import EventScore, EventCategory

logger = logging.getLogger(__name__)


class ImpactModel:
    """ML model for predicting event impact on price."""

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir
        self._model = None
        self._is_trained = False
        self._feature_names = [
            "category_encoded", "sentiment_score", "source_reliability",
            "historical_impact", "volume_encoded", "whale_encoded",
            "social_encoded", "hour_of_day", "day_of_week",
            "num_affected_coins",
        ]
        self._category_encoding = {
            cat.value: i for i, cat in enumerate(EventCategory)
        }

    def _encode_features(self, score_data: dict) -> list[float]:
        """Encode a score card into numeric features."""
        # Volume encoding
        volume_map = {"very_low": 0, "low": 1, "normal": 2, "high": 3,
                       "very_high": 4, "extreme": 5}
        # Whale encoding
        whale_map = {"strong_distribution": 0, "distribution": 1, "neutral": 2,
                     "accumulation": 3, "strong_accumulation": 4}
        # Social encoding
        social_map = {"dead": 0, "declining": 1, "stable": 2, "rising": 3,
                      "trending": 4, "exploding": 5}

        import datetime
        now = datetime.datetime.now()

        features = [
            self._category_encoding.get(score_data.get("category", "other"), 14),
            score_data.get("news_sentiment", 50),
            score_data.get("source_reliability", 50),
            score_data.get("historical_impact", 50),
            volume_map.get(score_data.get("current_volume", "normal"), 2),
            whale_map.get(score_data.get("whale_activity", "neutral"), 2),
            social_map.get(score_data.get("social_trend", "stable"), 2),
            now.hour,
            now.weekday(),
            score_data.get("num_affected_coins", 1),
        ]
        return features

    def predict(self, score_data: dict) -> dict:
        """
        Predict impact for a scored event.

        Returns:
            dict with 'probability_positive', 'expected_magnitude', 'confidence'
        """
        if not self._is_trained or self._model is None:
            # Fallback: rule-based prediction when model isn't trained
            return self._rule_based_prediction(score_data)

        try:
            features = np.array([self._encode_features(score_data)])
            prob = self._model.predict_proba(features)[0]
            prediction = {
                "probability_positive": float(prob[1]) if len(prob) > 1 else 0.5,
                "expected_magnitude": float(abs(prob[1] - 0.5) * 10),  # Rough estimate
                "confidence": float(max(prob) * 100),
            }
            return prediction
        except Exception as e:
            logger.error(f"Model prediction error: {e}")
            return self._rule_based_prediction(score_data)

    def _rule_based_prediction(self, score_data: dict) -> dict:
        """Fallback rule-based prediction when ML model isn't trained."""
        sentiment = score_data.get("news_sentiment", 50)
        source_rel = score_data.get("source_reliability", 50)
        historical = score_data.get("historical_impact", 50)

        # Simple heuristic
        avg_score = (sentiment + source_rel + historical) / 3
        prob_positive = avg_score / 100

        # Adjust by category
        category = score_data.get("category", "other")
        bearish_cats = {"delisting", "hack", "lawsuit", "token_unlock"}
        bullish_cats = {"listing", "etf", "partnership", "airdrop", "burn"}

        if category in bearish_cats:
            prob_positive = 1 - prob_positive

        magnitude = abs(prob_positive - 0.5) * 10
        confidence = min(80, (abs(prob_positive - 0.5) * 200))

        return {
            "probability_positive": prob_positive,
            "expected_magnitude": magnitude,
            "confidence": confidence,
        }

    async def train(self, training_data: list[dict]) -> dict:
        """
        Train the model on historical impact data.

        Args:
            training_data: List of dicts with features + 'was_positive' label.

        Returns:
            Dict with training metrics.
        """
        if len(training_data) < 20:
            logger.info(f"Not enough training data ({len(training_data)} samples, need 20)")
            return {"status": "skipped", "reason": "insufficient_data"}

        try:
            from lightgbm import LGBMClassifier
            from sklearn.model_selection import cross_val_score

            X = np.array([self._encode_features(d) for d in training_data])
            y = np.array([1 if d.get("was_positive", True) else 0 for d in training_data])

            model = LGBMClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                verbose=-1,
            )

            # Cross-validation
            if len(training_data) >= 30:
                cv_scores = cross_val_score(model, X, y, cv=min(5, len(training_data) // 5))
                avg_accuracy = float(cv_scores.mean())
            else:
                avg_accuracy = 0.0

            # Full train
            model.fit(X, y)
            self._model = model
            self._is_trained = True

            metrics = {
                "status": "trained",
                "samples": len(training_data),
                "cv_accuracy": avg_accuracy,
                "timestamp": time.time(),
            }
            logger.info(f"Impact model trained: {metrics}")
            return metrics

        except ImportError:
            logger.warning("LightGBM not available — using rule-based prediction")
            return {"status": "skipped", "reason": "lightgbm_not_installed"}
        except Exception as e:
            logger.error(f"Model training error: {e}")
            return {"status": "error", "reason": str(e)}
