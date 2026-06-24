"""
Event Intelligence — Historical Impact Analyzer

Analyzes historical event impacts to build statistical profiles:
- Price changes at 1m, 5m, 30m, 1h, 24h after events
- Category-specific impact profiles
- Learns patterns like "Binance listings → median +X% in first hour"
"""

import logging
import time
from typing import Optional

from event_intelligence.database import EventDatabase
from event_intelligence.models import EventCategory, HistoricalImpact

logger = logging.getLogger(__name__)


class HistoricalAnalyzer:
    """Analyzes historical event impacts for prediction."""

    def __init__(self, db: EventDatabase):
        self.db = db
        self._category_profiles: dict[str, dict] = {}
        self._last_rebuild: float = 0
        self._rebuild_interval: float = 3600  # Rebuild profiles every hour

    async def rebuild_profiles(self):
        """Rebuild statistical profiles from historical data."""
        try:
            all_impacts = await self.db.get_all_impacts()
            if not all_impacts:
                logger.debug("No historical impact data yet for profiling")
                return

            # Group by category
            category_data: dict[str, list[dict]] = {}
            for impact in all_impacts:
                cat = impact.get("category", "other")
                if cat not in category_data:
                    category_data[cat] = []
                category_data[cat].append(impact)

            # Build profiles
            for cat, impacts in category_data.items():
                profile = self._compute_profile(impacts)
                self._category_profiles[cat] = profile

            self._last_rebuild = time.time()
            logger.info(
                f"Rebuilt {len(self._category_profiles)} historical impact profiles "
                f"from {len(all_impacts)} data points"
            )

        except Exception as e:
            logger.error(f"Error rebuilding profiles: {e}")

    def _compute_profile(self, impacts: list[dict]) -> dict:
        """Compute statistical profile from a list of impacts."""
        changes = {
            "1m": [], "5m": [], "30m": [], "1h": [], "24h": [],
        }

        for imp in impacts:
            for key, field in [("1m", "change_1m"), ("5m", "change_5m"),
                               ("30m", "change_30m"), ("1h", "change_1h"),
                               ("24h", "change_24h")]:
                val = imp.get(field)
                if val is not None:
                    changes[key].append(val)

        profile = {
            "sample_count": len(impacts),
        }

        for interval, vals in changes.items():
            if vals:
                sorted_vals = sorted(vals)
                n = len(sorted_vals)
                profile[f"median_{interval}"] = sorted_vals[n // 2]
                profile[f"mean_{interval}"] = sum(vals) / n
                profile[f"max_{interval}"] = max(vals)
                profile[f"min_{interval}"] = min(vals)
                profile[f"positive_rate_{interval}"] = sum(1 for v in vals if v > 0) / n
                profile[f"count_{interval}"] = n
            else:
                profile[f"median_{interval}"] = 0
                profile[f"mean_{interval}"] = 0
                profile[f"count_{interval}"] = 0

        return profile

    async def get_expected_impact(self, category: str) -> dict:
        """Get the expected impact profile for an event category."""
        # Rebuild if stale
        if time.time() - self._last_rebuild > self._rebuild_interval:
            await self.rebuild_profiles()

        return self._category_profiles.get(category, {
            "sample_count": 0,
            "median_1h": 0,
            "mean_1h": 0,
            "positive_rate_1h": 0.5,
        })

    async def get_historical_score(self, category: str) -> float:
        """
        Get a 0-100 score representing historical impact strength.
        Based on how reliably this category produces tradeable moves.
        """
        profile = await self.get_expected_impact(category)
        sample_count = profile.get("sample_count", 0)

        if sample_count < 5:
            return 50.0  # Not enough data

        # Score based on:
        # 1. Positive rate (reliability of direction prediction)
        pos_rate = profile.get("positive_rate_1h", 0.5)
        direction_score = abs(pos_rate - 0.5) * 200  # 0-100

        # 2. Median magnitude (bigger moves = more tradeable)
        median_1h = abs(profile.get("median_1h", 0))
        magnitude_score = min(median_1h * 20, 100)  # 5% move → 100

        # 3. Sample confidence
        confidence_mult = min(sample_count / 50, 1.0)  # 50+ samples → full confidence

        score = (direction_score * 0.5 + magnitude_score * 0.5) * confidence_mult
        return max(0, min(100, score))
