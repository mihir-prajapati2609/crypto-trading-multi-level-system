"""
Crypto Arbitrage Bot — Data Models

Defines all data structures used across the system.
Uses dataclasses for serialization-friendly models.
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

class TradeStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    FILLED = "filled"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StrategyType(str, Enum):
    TRIANGULAR = "triangular"
    CROSS_EXCHANGE = "cross_exchange"
    FUNDING_RATE = "funding_rate"
    AI_MOMENTUM = "ai_momentum"
    MOMENTUM_ROTATION = "momentum_rotation"
    RSI_MEAN_REVERSION = "rsi_mean_reversion"


class SignalAction(str, Enum):
    LONG = "long"       # Buy underpriced
    SHORT = "short"     # Sell overpriced
    EXIT = "exit"       # Close position
    HOLD = "hold"       # No action


class RegimeState(str, Enum):
    CALM = "calm"           # Low vol, tight spreads
    ACTIVE = "active"       # Normal/high vol, good opportunities
    CHAOTIC = "chaotic"     # Extreme vol, pause trading


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


# ============================================================
# Market Data Models
# ============================================================

@dataclass
class OrderBookLevel:
    """A single price/quantity level in the order book."""
    price: float
    quantity: float


@dataclass
class OrderBookSnapshot:
    """Snapshot of an order book at a point in time."""
    exchange: str
    symbol: str
    bids: list[OrderBookLevel]  # Sorted highest to lowest
    asks: list[OrderBookLevel]  # Sorted lowest to highest
    timestamp: float = field(default_factory=time.time)

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else float("inf")

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid

    @property
    def spread_pct(self) -> float:
        if self.mid_price == 0:
            return 0.0
        return (self.spread / self.mid_price) * 100

    def depth_at_level(self, levels: int = 5) -> tuple[float, float]:
        """Total bid/ask volume at top N levels."""
        bid_vol = sum(b.quantity for b in self.bids[:levels])
        ask_vol = sum(a.quantity for a in self.asks[:levels])
        return bid_vol, ask_vol


@dataclass
class TickerData:
    """Real-time ticker data for a trading pair."""
    exchange: str
    symbol: str
    last_price: float
    bid: float
    ask: float
    base_volume: float     # 24h volume in base currency
    quote_volume: float    # 24h volume in quote currency
    change_pct: float      # 24h price change %
    timestamp: float = field(default_factory=time.time)


@dataclass
class FundingRateData:
    """Funding rate information for perpetual futures."""
    exchange: str
    symbol: str
    funding_rate: float        # Current funding rate
    next_funding_time: float   # Unix timestamp of next funding
    predicted_rate: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


# ============================================================
# Intelligence Models
# ============================================================

@dataclass
class SpreadData:
    """Spread data between two exchanges or implied cross-rate."""
    symbol: str
    spread: float           # Absolute spread
    spread_pct: float       # Spread as percentage
    z_score: float = 0.0    # Z-score of current spread
    half_life_minutes: float = 0.0  # OU half-life
    is_cointegrated: bool = False   # Engle-Granger result
    coint_pvalue: float = 1.0       # Cointegration p-value
    timestamp: float = field(default_factory=time.time)


@dataclass
class Signal:
    """Trading signal from the intelligence layer."""
    action: SignalAction
    strategy: StrategyType
    symbol: str
    confidence: float          # 0.0 to 1.0
    z_score: float = 0.0
    predicted_vol: float = 0.0
    regime: RegimeState = RegimeState.ACTIVE
    regime_multiplier: float = 1.0
    obi_direction: float = 0.0  # -1 to 1, predicted price direction
    is_anomaly: bool = False
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# ============================================================
# Trading Models
# ============================================================

@dataclass
class Opportunity:
    """A detected arbitrage opportunity."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    strategy: StrategyType = StrategyType.CROSS_EXCHANGE
    symbol: str = ""
    exchanges: list[str] = field(default_factory=list)

    # Price info
    buy_price: float = 0.0
    sell_price: float = 0.0
    buy_exchange: str = ""
    sell_exchange: str = ""

    # Profit calculation
    gross_profit_pct: float = 0.0
    total_fees_pct: float = 0.0
    net_profit_pct: float = 0.0
    estimated_profit_usd: float = 0.0

    # Intelligence signals
    z_score: float = 0.0
    confidence: float = 0.0
    regime: RegimeState = RegimeState.ACTIVE

    # Sizing
    suggested_amount_usd: float = 0.0

    # State
    was_executed: bool = False
    skip_reason: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class TradeOrder:
    """A single order (one leg of a trade)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    exchange: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.LIMIT
    price: float = 0.0
    quantity: float = 0.0
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    fee: float = 0.0
    fee_currency: str = ""
    status: TradeStatus = TradeStatus.PENDING
    exchange_order_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class Trade:
    """A complete trade (may have multiple legs/orders)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    strategy: StrategyType = StrategyType.CROSS_EXCHANGE
    symbol: str = ""
    orders: list[TradeOrder] = field(default_factory=list)
    opportunity_id: str = ""

    # P&L
    gross_profit_usd: float = 0.0
    total_fees_usd: float = 0.0
    net_profit_usd: float = 0.0
    net_profit_pct: float = 0.0

    # State
    status: TradeStatus = TradeStatus.PENDING
    error_message: str = ""
    is_paper: bool = True
    timestamp: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


# ============================================================
# Coin Discovery Models
# ============================================================

@dataclass
class CoinScore:
    """Scoring data for a coin evaluated by the Discovery Engine."""
    symbol: str                        # e.g., "SOL/USDT"
    base_currency: str = ""            # e.g., "SOL"
    exchanges: list[str] = field(default_factory=list)

    # Individual scores (0.0 to 1.0)
    trend_strength_score: float = 0.0
    volume_increase_score: float = 0.0
    liquidity_score: float = 0.0
    volatility_score: float = 0.0
    breakout_probability: float = 0.0
    risk_score: float = 0.0

    # Extended multi-factor scores for momentum rotation (0.0 to 1.0)
    funding_rate_score: float = 0.0
    open_interest_score: float = 0.0
    news_sentiment_score: float = 0.0
    momentum_rank_score: float = 0.0  # Weighted composite for rotation ranking

    # Composite
    composite_score: float = 0.0
    rank: int = 0

    # Raw data
    avg_spread_pct: float = 0.0
    avg_daily_volume_usd: float = 0.0
    listing_age_days: int = 0
    is_cointegrated: bool = False

    timestamp: float = field(default_factory=time.time)


# ============================================================
# Analytics Models
# ============================================================

@dataclass
class DailyPnL:
    """Daily profit & loss summary."""
    date: str                    # YYYY-MM-DD
    gross_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        return (self.win_count / total * 100) if total > 0 else 0.0


@dataclass
class BalanceSnapshot:
    """Snapshot of account balances."""
    exchange: str
    total_usd: float = 0.0
    free_usd: float = 0.0
    used_usd: float = 0.0
    assets: dict[str, float] = field(default_factory=dict)  # {currency: amount}
    timestamp: float = field(default_factory=time.time)


@dataclass
class SystemStatus:
    """Overall system status for dashboard."""
    is_running: bool = False
    trading_mode: str = "paper"
    active_strategy_count: int = 0
    current_regime: RegimeState = RegimeState.ACTIVE
    current_garch_vol: float = 0.0
    anomaly_detected: bool = False
    total_balance_usd: float = 0.0
    daily_pnl: float = 0.0
    daily_trade_count: int = 0
    watchlist_size: int = 0
    uptime_seconds: float = 0.0
    last_trade_time: Optional[float] = None
    errors: list[str] = field(default_factory=list)
