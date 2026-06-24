"""
Event Intelligence — Data Models

All data structures used by the event intelligence system.
Completely independent of the main arbitrage data models.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================
# Enums
# ============================================================

class EventCategory(str, Enum):
    """Classification of news events by type."""
    LISTING = "listing"                 # Exchange listing
    DELISTING = "delisting"             # Exchange delisting
    ETF = "etf"                         # ETF approval/rejection
    HACK = "hack"                       # Exchange/protocol hack
    TOKEN_UNLOCK = "token_unlock"       # Large token unlock
    WHALE_MOVEMENT = "whale_movement"   # Whale accumulation/distribution
    PROTOCOL_UPGRADE = "protocol_upgrade"  # Developer upgrade announcement
    LAWSUIT = "lawsuit"                 # Regulatory action / SEC lawsuit
    MACRO = "macro"                     # Fed rate, inflation, GDP
    SOCIAL = "social"                   # Elon tweet, influencer pump
    PARTNERSHIP = "partnership"         # Major partnership announcement
    AIRDROP = "airdrop"                 # Airdrop announcement
    BURN = "burn"                       # Token burn event
    FORK = "fork"                       # Chain fork
    OTHER = "other"


class EventSentiment(str, Enum):
    """Overall sentiment direction."""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


class TradeAction(str, Enum):
    """Trade action from the decision engine."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    SKIP = "skip"  # Confidence too low


class EventTradeStatus(str, Enum):
    """Status of an event-driven trade."""
    PENDING = "pending"
    OPEN = "open"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    MANUAL_CLOSE = "manual_close"
    EXPIRED = "expired"
    FAILED = "failed"


class VolumeLevel(str, Enum):
    """Qualitative volume assessment."""
    VERY_LOW = "very_low"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    VERY_HIGH = "very_high"
    EXTREME = "extreme"


class WhaleActivity(str, Enum):
    """Whale activity direction."""
    STRONG_ACCUMULATION = "strong_accumulation"
    ACCUMULATION = "accumulation"
    NEUTRAL = "neutral"
    DISTRIBUTION = "distribution"
    STRONG_DISTRIBUTION = "strong_distribution"


class SocialTrend(str, Enum):
    """Social media trend status."""
    EXPLODING = "exploding"
    TRENDING = "trending"
    RISING = "rising"
    STABLE = "stable"
    DECLINING = "declining"
    DEAD = "dead"


# ============================================================
# Core Event Models
# ============================================================

@dataclass
class NewsEvent:
    """A raw event collected from any data source."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    source: str = ""                    # e.g., "rss_coindesk", "binance_announcements"
    title: str = ""
    body: str = ""
    url: str = ""
    raw_data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # Populated by NLP pipeline
    category: EventCategory = EventCategory.OTHER
    affected_coins: list[str] = field(default_factory=list)  # e.g., ["BTC", "ETH"]
    sentiment_score: float = 50.0       # 0-100, 50=neutral
    sentiment: EventSentiment = EventSentiment.NEUTRAL

    # Deduplication
    content_hash: str = ""
    is_duplicate: bool = False


@dataclass
class AgentVote:
    """An individual agent's scoring contribution."""
    agent_name: str = ""
    score: float = 50.0                 # 0-100
    confidence: float = 50.0            # 0-100
    direction: str = "neutral"          # bullish / bearish / neutral
    reasoning: str = ""
    weight: float = 0.2                 # Agent weight in ensemble
    timestamp: float = field(default_factory=time.time)


@dataclass
class EventScore:
    """
    Full multi-signal score card for an event.
    This is the structured output the user described.
    """
    event_id: str = ""
    coin: str = ""                          # Primary affected coin

    # Individual signal scores (0-100)
    news_sentiment: float = 50.0
    source_reliability: float = 50.0        # % reliability of source
    historical_impact: float = 50.0         # % based on similar past events
    current_volume: VolumeLevel = VolumeLevel.NORMAL
    whale_activity: WhaleActivity = WhaleActivity.NEUTRAL
    social_trend: SocialTrend = SocialTrend.STABLE

    # AI composite
    ai_confidence: float = 50.0             # Final AI confidence 0-100%
    trade_action: TradeAction = TradeAction.SKIP

    # Agent votes
    agent_votes: list[AgentVote] = field(default_factory=list)

    # Meta
    category: EventCategory = EventCategory.OTHER
    timestamp: float = field(default_factory=time.time)


@dataclass
class EventTradeSignal:
    """A trade signal generated by the decision engine."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_id: str = ""
    score_id: str = ""
    coin: str = ""
    symbol: str = ""                    # Full trading pair, e.g., "BTC/USDT"
    action: TradeAction = TradeAction.SKIP
    confidence: float = 0.0

    # Sizing
    position_size_pct: float = 3.0      # % of capital
    position_size_usd: float = 0.0

    # Levels
    entry_price: float = 0.0
    take_profit_price: float = 0.0
    stop_loss_price: float = 0.0
    trailing_stop_enabled: bool = True

    timestamp: float = field(default_factory=time.time)


# ============================================================
# Trade Tracking Models
# ============================================================

@dataclass
class EventTrade:
    """A trade triggered by an event signal."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    signal_id: str = ""
    event_id: str = ""
    coin: str = ""
    symbol: str = ""

    # Entry
    entry_price: float = 0.0
    entry_time: float = 0.0
    position_size_usd: float = 0.0
    side: str = "buy"                   # "buy" or "sell"

    # Exit
    exit_price: float = 0.0
    exit_time: float = 0.0
    exit_reason: EventTradeStatus = EventTradeStatus.PENDING

    # Levels
    take_profit_price: float = 0.0
    stop_loss_price: float = 0.0
    trailing_stop_price: float = 0.0
    highest_price: float = 0.0         # Highest price since entry (for trailing)

    # P&L
    gross_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    net_pnl_usd: float = 0.0
    net_pnl_pct: float = 0.0

    # State
    status: EventTradeStatus = EventTradeStatus.PENDING
    is_paper: bool = True
    ai_confidence: float = 0.0
    error_message: str = ""
    timestamp: float = field(default_factory=time.time)


# ============================================================
# Historical & Feedback Models
# ============================================================

@dataclass
class HistoricalImpact:
    """
    Price impact data at various time intervals after an event.
    Used to train the impact prediction model.
    """
    event_id: str = ""
    coin: str = ""
    category: EventCategory = EventCategory.OTHER

    # Pre-event
    price_before: float = 0.0
    volume_before: float = 0.0
    market_cap_before: float = 0.0

    # Post-event price changes (percentage)
    change_1m: Optional[float] = None
    change_5m: Optional[float] = None
    change_30m: Optional[float] = None
    change_1h: Optional[float] = None
    change_24h: Optional[float] = None

    # Context
    sentiment_score: float = 50.0
    source_reliability: float = 50.0
    pre_event_volume_level: VolumeLevel = VolumeLevel.NORMAL

    timestamp: float = field(default_factory=time.time)


@dataclass
class SourceReliability:
    """Tracks reliability of each data source over time."""
    source_name: str = ""
    total_events: int = 0
    accurate_predictions: int = 0
    reliability_score: float = 50.0     # 0-100%
    avg_impact_accuracy: float = 50.0
    last_updated: float = field(default_factory=time.time)


@dataclass
class AgentPerformance:
    """Tracks individual agent accuracy over time."""
    agent_name: str = ""
    total_votes: int = 0
    correct_direction: int = 0
    avg_score_accuracy: float = 50.0
    current_weight: float = 0.2
    last_calibration: float = field(default_factory=time.time)


# ============================================================
# Engine State Model
# ============================================================

@dataclass
class EventEngineState:
    """Overall state of the event intelligence engine for dashboard."""
    is_running: bool = False
    mode: str = "observe"
    total_events_processed: int = 0
    events_last_hour: int = 0
    active_signals: int = 0
    open_trades: int = 0
    total_trades: int = 0
    event_pnl_today: float = 0.0
    event_pnl_total: float = 0.0
    win_rate: float = 0.0
    avg_confidence: float = 0.0
    sources_active: int = 0
    sources_total: int = 9
    last_event_time: Optional[float] = None
    recent_events: list[dict] = field(default_factory=list)
    recent_scores: list[dict] = field(default_factory=list)
    recent_trades: list[dict] = field(default_factory=list)
    agent_performance: list[dict] = field(default_factory=list)
    fear_greed_index: int = 50
    fear_greed_label: str = "Neutral"
