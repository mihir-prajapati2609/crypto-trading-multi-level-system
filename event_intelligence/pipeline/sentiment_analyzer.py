"""
Event Intelligence — Sentiment Analyzer

Multi-method sentiment scoring for crypto news:
1. VADER sentiment (general purpose)
2. Custom crypto-domain lexicon (domain-specific boost)
3. Weighted ensemble
"""

import logging
import re
from typing import Optional

from event_intelligence.models import EventSentiment

logger = logging.getLogger(__name__)


# Crypto-specific sentiment lexicon
# Words with domain-specific meaning that general sentiment tools miss
CRYPTO_BULLISH_WORDS = {
    # Very bullish (weight 3)
    "moon": 3, "mooning": 3, "moonshot": 3, "bullish": 3, "breakout": 3,
    "ath": 3, "all-time high": 3, "parabolic": 3, "skyrocket": 3,
    "surge": 3, "soar": 3, "pump": 2, "rally": 3,

    # Bullish (weight 2)
    "listing": 2, "listed": 2, "approval": 2, "approved": 2,
    "accumulation": 2, "accumulating": 2, "buy": 2, "buying": 2,
    "upgrade": 2, "partnership": 2, "integration": 2, "adoption": 2,
    "launch": 2, "launches": 2, "innovative": 2, "milestone": 2,

    # Mildly bullish (weight 1)
    "growth": 1, "gain": 1, "gains": 1, "positive": 1, "strong": 1,
    "higher": 1, "up": 1, "increase": 1, "green": 1, "recovery": 1,
    "support": 1, "demand": 1, "trending": 1, "popular": 1,
    "institutional": 1, "whale": 1,
}

CRYPTO_BEARISH_WORDS = {
    # Very bearish (weight -3)
    "hack": -3, "hacked": -3, "exploit": -3, "rug": -3, "rugpull": -3,
    "scam": -3, "fraud": -3, "crash": -3, "collapse": -3,
    "bankruptcy": -3, "insolvent": -3, "stolen": -3,

    # Bearish (weight -2)
    "delisting": -2, "delisted": -2, "banned": -2, "ban": -2,
    "lawsuit": -2, "sec": -2, "investigation": -2, "dump": -2,
    "dumping": -2, "sell-off": -2, "selloff": -2, "bearish": -2,
    "unlock": -2, "vulnerability": -2, "breach": -2, "fine": -2,

    # Mildly bearish (weight -1)
    "decline": -1, "drop": -1, "fall": -1, "falling": -1, "down": -1,
    "red": -1, "loss": -1, "losses": -1, "weak": -1, "lower": -1,
    "resistance": -1, "fear": -1, "concern": -1, "risk": -1,
    "regulation": -1, "warning": -1, "caution": -1,
}


class SentimentAnalyzer:
    """Analyzes sentiment of crypto news text using multiple methods."""

    def __init__(self):
        self._vader = None

    def _get_vader(self):
        """Lazy-load VADER sentiment analyzer."""
        if self._vader is None:
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
                self._vader = SentimentIntensityAnalyzer()
            except ImportError:
                logger.warning("vaderSentiment not installed — using crypto lexicon only")
        return self._vader

    def _vader_score(self, text: str) -> float:
        """
        Get VADER compound sentiment score normalized to 0-100.
        VADER compound is -1 to 1, we map to 0-100.
        """
        vader = self._get_vader()
        if vader is None:
            return 50.0  # Neutral fallback

        scores = vader.polarity_scores(text)
        compound = scores["compound"]  # -1 to 1
        return (compound + 1) * 50  # Map to 0-100

    def _crypto_lexicon_score(self, text: str) -> float:
        """
        Score text using the crypto-domain sentiment lexicon.
        Returns 0-100 (50 = neutral).
        """
        words = re.findall(r'\b[\w-]+\b', text.lower())
        total_score = 0.0
        word_count = 0

        for word in words:
            if word in CRYPTO_BULLISH_WORDS:
                total_score += CRYPTO_BULLISH_WORDS[word]
                word_count += 1
            elif word in CRYPTO_BEARISH_WORDS:
                total_score += CRYPTO_BEARISH_WORDS[word]
                word_count += 1

        # Also check multi-word phrases
        text_lower = text.lower()
        for phrase, weight in CRYPTO_BULLISH_WORDS.items():
            if " " in phrase and phrase in text_lower:
                total_score += weight
                word_count += 1
        for phrase, weight in CRYPTO_BEARISH_WORDS.items():
            if " " in phrase and phrase in text_lower:
                total_score += weight
                word_count += 1

        if word_count == 0:
            return 50.0

        # Normalize: max possible score per word is ~3, scale accordingly
        avg_score = total_score / max(word_count, 1)
        # Map from [-3, 3] to [0, 100]
        normalized = ((avg_score + 3) / 6) * 100
        return max(0, min(100, normalized))

    def analyze(self, title: str, body: str = "") -> float:
        """
        Analyze sentiment of news text.
        Returns score 0-100 (0=very bearish, 50=neutral, 100=very bullish).
        """
        text = f"{title}. {body}".strip()

        vader_score = self._vader_score(text)
        crypto_score = self._crypto_lexicon_score(text)

        # Weighted ensemble: crypto lexicon gets more weight for domain relevance
        # VADER: 40%, Crypto Lexicon: 60%
        final_score = (vader_score * 0.4) + (crypto_score * 0.6)

        return round(max(0, min(100, final_score)), 1)

    def score_to_sentiment(self, score: float) -> EventSentiment:
        """Convert a numeric score to a sentiment label."""
        if score >= 80:
            return EventSentiment.VERY_BULLISH
        elif score >= 65:
            return EventSentiment.BULLISH
        elif score >= 40:
            return EventSentiment.NEUTRAL
        elif score >= 25:
            return EventSentiment.BEARISH
        else:
            return EventSentiment.VERY_BEARISH
