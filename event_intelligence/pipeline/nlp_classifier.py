"""
Event Intelligence — NLP Headline Classifier

Classifies news headlines into EventCategory using:
1. Rule-based fast path for obvious patterns
2. Keyword scoring for ambiguous cases
"""

import logging
import re
from typing import Optional

from event_intelligence.models import EventCategory

logger = logging.getLogger(__name__)


# Rule-based classification patterns (checked in order, first match wins)
CLASSIFICATION_RULES: list[tuple[list[str], EventCategory]] = [
    # Listings
    (["will list", "new listing", "lists ", "added to", "now available on binance",
      "now available on coinbase", "trading starts", "spot listing",
      "perpetual listing", "launches on"], EventCategory.LISTING),

    # Delistings
    (["delist", "remove trading", "removal of", "suspend trading",
      "trading suspension"], EventCategory.DELISTING),

    # ETF
    (["etf approval", "etf rejected", "etf filing", "spot etf", "bitcoin etf",
      "ethereum etf", "crypto etf"], EventCategory.ETF),

    # Hacks
    (["hack", "exploit", "breach", "stolen", "drained", "vulnerability",
      "security incident", "compromised", "rug pull", "rugpull"], EventCategory.HACK),

    # Token unlocks
    (["token unlock", "vesting", "cliff unlock", "tokens released",
      "unlock schedule", "supply unlock"], EventCategory.TOKEN_UNLOCK),

    # Whale movements
    (["whale", "large transfer", "whale alert", "whale movement",
      "accumulation", "whale buys", "whale sells"], EventCategory.WHALE_MOVEMENT),

    # Protocol upgrades
    (["upgrade", "hard fork", "mainnet launch", "protocol update",
      "network upgrade", "v2 launch", "migration", "testnet",
      "devnet", "release candidate"], EventCategory.PROTOCOL_UPGRADE),

    # Lawsuits / Regulatory
    (["sec ", "lawsuit", "regulatory", "regulation", "enforcement",
      "subpoena", "investigation", "compliance", "banned", "illegal",
      "sanction", "fine ", "penalty"], EventCategory.LAWSUIT),

    # Macro
    (["fed ", "federal reserve", "interest rate", "inflation",
      "cpi ", "gdp ", "employment", "fomc", "rate decision",
      "rate hike", "rate cut", "monetary policy", "treasury"], EventCategory.MACRO),

    # Social / Viral
    (["elon musk", "musk tweet", "viral", "trending", "meme",
      "influencer", "celebrity", "tweet"], EventCategory.SOCIAL),

    # Partnerships
    (["partnership", "partners with", "collaboration", "integration",
      "teams up", "joins forces", "strategic alliance"], EventCategory.PARTNERSHIP),

    # Airdrops
    (["airdrop", "free tokens", "token distribution", "claim",
      "snapshot"], EventCategory.AIRDROP),

    # Burns
    (["burn", "burning", "burned", "deflationary", "supply reduction",
      "token burn"], EventCategory.BURN),

    # Forks
    (["hard fork", "soft fork", "chain split", "forked"], EventCategory.FORK),
]

# Keyword weights for scoring when rules don't match
KEYWORD_SCORES: dict[EventCategory, dict[str, float]] = {
    EventCategory.LISTING: {
        "list": 0.6, "launch": 0.4, "add": 0.3, "trade": 0.2, "exchange": 0.3,
        "pair": 0.3, "spot": 0.2, "perpetual": 0.2,
    },
    EventCategory.HACK: {
        "security": 0.5, "attack": 0.4, "loss": 0.3, "million": 0.2,
        "vulnerability": 0.6, "malicious": 0.5, "phishing": 0.4,
    },
    EventCategory.MACRO: {
        "economy": 0.4, "market": 0.3, "global": 0.3, "bank": 0.3,
        "dollar": 0.3, "yield": 0.3, "bond": 0.3,
    },
}


class NLPClassifier:
    """Classifies crypto news headlines into event categories."""

    def classify(self, title: str, body: str = "") -> EventCategory:
        """
        Classify a headline into an EventCategory.

        Uses rule-based matching first, falls back to keyword scoring.
        """
        text = (title + " " + body).lower().strip()

        # Phase 1: Rule-based fast path
        for keywords, category in CLASSIFICATION_RULES:
            for kw in keywords:
                if kw in text:
                    return category

        # Phase 2: Keyword scoring fallback
        best_category = EventCategory.OTHER
        best_score = 0.0

        for category, keywords in KEYWORD_SCORES.items():
            score = 0.0
            for kw, weight in keywords.items():
                if kw in text:
                    score += weight
            if score > best_score and score >= 0.5:
                best_score = score
                best_category = category

        return best_category

    def get_classification_confidence(self, title: str, body: str = "") -> float:
        """
        Return confidence (0-1) of the classification.
        Rule-based matches get high confidence, keyword matches lower.
        """
        text = (title + " " + body).lower().strip()

        # Check rule-based matches
        for keywords, category in CLASSIFICATION_RULES:
            for kw in keywords:
                if kw in text:
                    return 0.95  # High confidence for direct matches

        # Check keyword scoring
        best_score = 0.0
        for category, keywords in KEYWORD_SCORES.items():
            score = sum(w for kw, w in keywords.items() if kw in text)
            best_score = max(best_score, score)

        if best_score >= 1.0:
            return 0.8
        elif best_score >= 0.5:
            return 0.6
        else:
            return 0.3  # Low confidence — OTHER category
