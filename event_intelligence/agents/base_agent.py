"""
Event Intelligence — Base Agent

Abstract base class for all scoring agents.
Each agent independently evaluates an event and provides a vote.
"""

import abc
import logging
from typing import Any, Optional

from event_intelligence.models import NewsEvent, AgentVote

logger = logging.getLogger(__name__)


class BaseAgent(abc.ABC):
    """Abstract base class for event scoring agents."""

    def __init__(self, name: str, weight: float = 0.2):
        self._name = name
        self._weight = weight
        self._total_votes: int = 0
        self._correct_votes: int = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def weight(self) -> float:
        return self._weight

    @weight.setter
    def weight(self, value: float):
        self._weight = max(0.0, min(1.0, value))

    @abc.abstractmethod
    async def score(self, event: NewsEvent, market_context: dict) -> AgentVote:
        """
        Score an event and return a vote.

        Args:
            event: The processed NewsEvent to score.
            market_context: Dict with current market data (prices, volumes, etc.)

        Returns:
            AgentVote with score (0-100), confidence, direction, and reasoning.
        """
        pass

    def _create_vote(self, score: float, confidence: float,
                     direction: str, reasoning: str) -> AgentVote:
        """Helper to create a vote with this agent's metadata."""
        self._total_votes += 1
        return AgentVote(
            agent_name=self._name,
            score=max(0, min(100, score)),
            confidence=max(0, min(100, confidence)),
            direction=direction,
            reasoning=reasoning,
            weight=self._weight,
        )

    def record_accuracy(self, was_correct: bool):
        """Record whether this agent's vote was correct (for calibration)."""
        if was_correct:
            self._correct_votes += 1

    @property
    def accuracy(self) -> float:
        """Current accuracy rate."""
        if self._total_votes == 0:
            return 50.0
        return (self._correct_votes / self._total_votes) * 100
