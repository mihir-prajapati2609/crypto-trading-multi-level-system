"""
Event Intelligence — Risk Manager

Independent risk management for event-driven trades.
Enforces position sizing, drawdown limits, and trade count caps.
"""

import logging
import time
from typing import Tuple

from event_intelligence.config import EventRiskConfig
from event_intelligence.models import (
    EventScore, EventTradeSignal, EventTrade, TradeAction,
    EventTradeStatus,
)

logger = logging.getLogger(__name__)


class EventRiskManager:
    """Risk management for event-driven trades."""

    def __init__(self, config: EventRiskConfig, capital: float = 300.0):
        self.config = config
        self.capital = capital
        self.initial_capital = capital

        # State
        self.open_trades: list[EventTrade] = []
        self.daily_pnl: float = 0.0
        self.total_pnl: float = 0.0
        self.is_paused: bool = False
        self._last_loss_time: float = 0
        self._consecutive_losses: int = 0

    def check_trade_allowed(self, score: EventScore) -> Tuple[bool, str]:
        """
        Check if a new trade is allowed based on risk rules.

        Returns:
            (allowed: bool, reason: str)
        """
        # Kill switch
        if self.is_paused:
            return False, "Trading paused (kill switch)"

        # Confidence threshold
        if score.ai_confidence < self.config.position_size_pct:
            # This intentionally uses a different threshold check
            pass

        from event_intelligence.config import get_event_config
        min_conf = get_event_config().scoring.min_confidence_to_trade
        if score.ai_confidence < min_conf:
            return False, f"Confidence {score.ai_confidence:.0f}% < minimum {min_conf:.0f}%"

        # Max open trades
        if len(self.open_trades) >= self.config.max_open_trades:
            return False, f"Max open trades reached ({len(self.open_trades)}/{self.config.max_open_trades})"

        # Daily loss limit
        daily_loss_limit = self.capital * (self.config.max_daily_loss_pct / 100)
        if self.daily_pnl < -daily_loss_limit:
            return False, f"Daily loss limit reached (${self.daily_pnl:.2f} < ${-daily_loss_limit:.2f})"

        # Max drawdown
        drawdown_pct = ((self.initial_capital - self.capital) / self.initial_capital) * 100
        if drawdown_pct > self.config.max_drawdown_pct:
            return False, f"Max drawdown exceeded ({drawdown_pct:.1f}% > {self.config.max_drawdown_pct:.1f}%)"

        # Cooldown after loss
        if self._last_loss_time > 0:
            elapsed = time.time() - self._last_loss_time
            if elapsed < self.config.cooldown_after_loss_seconds:
                remaining = self.config.cooldown_after_loss_seconds - elapsed
                return False, f"Cooldown active ({remaining:.0f}s remaining)"

        # Don't trade the same coin if already in a position
        for trade in self.open_trades:
            if trade.coin == score.coin:
                return False, f"Already in position for {score.coin}"

        # Only trade BUY/SELL actions
        if score.trade_action in (TradeAction.SKIP, TradeAction.HOLD):
            return False, f"No actionable signal ({score.trade_action.value})"

        return True, "Approved"

    def calculate_position_size(self, score: EventScore) -> float:
        """Calculate position size in USD based on confidence and risk params."""
        base_size = self.capital * (self.config.position_size_pct / 100)

        # Scale by confidence: 90% → 100% of base, 95% → 125%, 100% → 150%
        confidence_mult = 0.5 + (score.ai_confidence / 100)  # 0.5 to 1.5
        confidence_mult = min(confidence_mult, 1.5)

        size = base_size * confidence_mult

        # Never exceed available capital
        available = self.capital - sum(t.position_size_usd for t in self.open_trades)
        size = min(size, available * 0.5)  # Max 50% of remaining

        return max(0, round(size, 2))

    def create_signal(self, score: EventScore, current_price: float) -> EventTradeSignal:
        """Create a trade signal with TP/SL levels."""
        position_size = self.calculate_position_size(score)

        is_buy = score.trade_action in (TradeAction.BUY, TradeAction.STRONG_BUY)

        if is_buy:
            take_profit = current_price * (1 + self.config.take_profit_pct / 100)
            stop_loss = current_price * (1 - self.config.stop_loss_pct / 100)
        else:
            take_profit = current_price * (1 - self.config.take_profit_pct / 100)
            stop_loss = current_price * (1 + self.config.stop_loss_pct / 100)

        signal = EventTradeSignal(
            event_id=score.event_id,
            coin=score.coin,
            symbol=f"{score.coin}/USDT",
            action=score.trade_action,
            confidence=score.ai_confidence,
            position_size_pct=self.config.position_size_pct,
            position_size_usd=position_size,
            entry_price=current_price,
            take_profit_price=take_profit,
            stop_loss_price=stop_loss,
            trailing_stop_enabled=self.config.trailing_stop_enabled,
        )

        return signal

    def record_trade_open(self, trade: EventTrade):
        """Record a newly opened trade."""
        self.open_trades.append(trade)

    def record_trade_close(self, trade: EventTrade):
        """Record a closed trade and update risk state."""
        # Remove from open trades
        self.open_trades = [t for t in self.open_trades if t.id != trade.id]

        # Update P&L
        self.daily_pnl += trade.net_pnl_usd
        self.total_pnl += trade.net_pnl_usd
        self.capital += trade.net_pnl_usd

        # Track losses
        if trade.net_pnl_usd < 0:
            self._consecutive_losses += 1
            self._last_loss_time = time.time()
            if self._consecutive_losses >= 3:
                logger.warning(
                    f"3 consecutive losses — extending cooldown"
                )
        else:
            self._consecutive_losses = 0

    def reset_daily(self):
        """Reset daily P&L (called at midnight UTC)."""
        self.daily_pnl = 0.0

    @property
    def current_drawdown_pct(self) -> float:
        """Current drawdown from initial capital."""
        if self.initial_capital <= 0:
            return 0.0
        return max(0, ((self.initial_capital - self.capital) / self.initial_capital) * 100)

    @property
    def status_summary(self) -> dict:
        """Get risk status summary for dashboard."""
        return {
            "capital": self.capital,
            "daily_pnl": self.daily_pnl,
            "total_pnl": self.total_pnl,
            "drawdown_pct": self.current_drawdown_pct,
            "open_trades": len(self.open_trades),
            "max_open_trades": self.config.max_open_trades,
            "is_paused": self.is_paused,
            "consecutive_losses": self._consecutive_losses,
        }
