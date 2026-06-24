"""
Event Intelligence — Position Manager

Manages open event-driven positions:
- Monitors TP/SL/trailing stop
- Updates highest price for trailing stops
- Auto-closes positions when conditions are met
"""

import logging
import time
from typing import Optional

from event_intelligence.models import (
    EventTrade, EventTradeStatus, TradeAction,
)
from event_intelligence.config import EventRiskConfig

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages open event-driven positions and exit conditions."""

    def __init__(self, config: EventRiskConfig):
        self.config = config

    def check_exit_conditions(self, trade: EventTrade,
                              current_price: float) -> Optional[EventTradeStatus]:
        """
        Check if an open trade should be closed.

        Returns:
            EventTradeStatus if should close, None if should stay open.
        """
        if trade.status != EventTradeStatus.OPEN:
            return None

        is_long = trade.side == "buy"

        # Update highest price for trailing stop
        if is_long:
            trade.highest_price = max(trade.highest_price, current_price)
        else:
            # For shorts, track lowest price
            if trade.highest_price == 0:
                trade.highest_price = current_price
            trade.highest_price = min(trade.highest_price, current_price)

        # Check Take Profit
        if is_long and current_price >= trade.take_profit_price:
            return EventTradeStatus.TAKE_PROFIT
        elif not is_long and current_price <= trade.take_profit_price:
            return EventTradeStatus.TAKE_PROFIT

        # Check Stop Loss
        if is_long and current_price <= trade.stop_loss_price:
            return EventTradeStatus.STOP_LOSS
        elif not is_long and current_price >= trade.stop_loss_price:
            return EventTradeStatus.STOP_LOSS

        # Check Trailing Stop
        if self.config.trailing_stop_enabled:
            trailing_exit = self._check_trailing_stop(trade, current_price)
            if trailing_exit:
                return EventTradeStatus.TRAILING_STOP

        # Check max hold time (24h default)
        hold_time = time.time() - trade.entry_time
        if hold_time > 86400:  # 24 hours
            return EventTradeStatus.EXPIRED

        return None

    def _check_trailing_stop(self, trade: EventTrade,
                             current_price: float) -> bool:
        """Check if trailing stop has been triggered."""
        is_long = trade.side == "buy"
        activation_pct = self.config.trailing_stop_activation_pct
        callback_pct = self.config.trailing_stop_callback_pct

        if is_long:
            # Profit from entry
            profit_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
            if profit_pct < activation_pct:
                return False  # Haven't reached activation threshold

            # Calculate trailing stop level
            trail_price = trade.highest_price * (1 - callback_pct / 100)
            trade.trailing_stop_price = trail_price

            if current_price <= trail_price:
                return True
        else:
            # Short position
            profit_pct = ((trade.entry_price - current_price) / trade.entry_price) * 100
            if profit_pct < activation_pct:
                return False

            trail_price = trade.highest_price * (1 + callback_pct / 100)
            trade.trailing_stop_price = trail_price

            if current_price >= trail_price:
                return True

        return False

    def calculate_pnl(self, trade: EventTrade, exit_price: float) -> dict:
        """Calculate P&L for a trade at a given exit price."""
        is_long = trade.side == "buy"
        qty = trade.position_size_usd / trade.entry_price

        if is_long:
            gross_pnl = (exit_price - trade.entry_price) * qty
        else:
            gross_pnl = (trade.entry_price - exit_price) * qty

        # Fees: 0.1% per side = 0.2% round trip
        fees = trade.position_size_usd * 0.002
        net_pnl = gross_pnl - fees
        net_pnl_pct = (net_pnl / trade.position_size_usd) * 100

        return {
            "gross_pnl_usd": round(gross_pnl, 4),
            "fees_usd": round(fees, 4),
            "net_pnl_usd": round(net_pnl, 4),
            "net_pnl_pct": round(net_pnl_pct, 4),
        }

    def close_trade(self, trade: EventTrade, current_price: float,
                    reason: EventTradeStatus) -> EventTrade:
        """Close a trade and calculate final P&L."""
        pnl = self.calculate_pnl(trade, current_price)

        trade.exit_price = current_price
        trade.exit_time = time.time()
        trade.exit_reason = reason
        trade.status = reason
        trade.gross_pnl_usd = pnl["gross_pnl_usd"]
        trade.fees_usd = pnl["fees_usd"]
        trade.net_pnl_usd = pnl["net_pnl_usd"]
        trade.net_pnl_pct = pnl["net_pnl_pct"]

        logger.info(
            f"🔒 Closed trade {trade.id} ({trade.coin}): "
            f"{reason.value} at ${current_price:.4f} "
            f"| PnL: ${trade.net_pnl_usd:.4f} ({trade.net_pnl_pct:+.2f}%)"
        )

        return trade
