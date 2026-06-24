"""
AI Event Intelligence Engine

An independent, self-contained news-driven trading system that collects data
from 13+ sources, scores events with AI agents, and generates high-confidence
trade signals. Operates completely independently of the arbitrage system.
"""

from event_intelligence.engine import EventIntelligenceEngine

__all__ = ["EventIntelligenceEngine"]
