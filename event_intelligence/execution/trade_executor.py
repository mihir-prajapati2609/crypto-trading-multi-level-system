"""
Event Intelligence — Trade Executor

Executes event-driven trades in paper or live mode.
Paper mode simulates fills with actual market prices.
"""

import logging
import time
from typing import Optional

from event_intelligence.models import (
    EventTrade, EventTradeSignal, EventTradeStatus, TradeAction,
)
from event_intelligence.database import EventDatabase
from event_intelligence.execution.risk_manager import EventRiskManager
from event_intelligence.execution.position_manager import PositionManager

logger = logging.getLogger(__name__)


class EventTradeExecutor:
    """Executes event-driven trades (paper mode)."""

    def __init__(self, db: EventDatabase, risk_manager: EventRiskManager,
                 position_manager: PositionManager, is_paper: bool = True):
        self.db = db
        self.risk_manager = risk_manager
        self.position_manager = position_manager
        self.is_paper = is_paper

    async def execute_signal(self, signal: EventTradeSignal) -> Optional[EventTrade]:
        """
        Execute a trade signal.

        In paper mode, simulates an immediate fill at the signal's entry price.
        """
        if signal.position_size_usd <= 0:
            logger.warning(f"Signal {signal.id} has zero position size, skipping")
            return None

        is_buy = signal.action in (TradeAction.BUY, TradeAction.STRONG_BUY)

        trade = EventTrade(
            signal_id=signal.id,
            event_id=signal.event_id,
            coin=signal.coin,
            symbol=signal.symbol,
            entry_price=signal.entry_price,
            entry_time=time.time(),
            position_size_usd=signal.position_size_usd,
            side="buy" if is_buy else "sell",
            take_profit_price=signal.take_profit_price,
            stop_loss_price=signal.stop_loss_price,
            highest_price=signal.entry_price,
            status=EventTradeStatus.OPEN,
            is_paper=self.is_paper,
            ai_confidence=signal.confidence,
        )

        if self.is_paper:
            # Paper mode — instant fill at entry price
            trade.status = EventTradeStatus.OPEN
            logger.info(
                f"📝 PAPER TRADE opened: {trade.side.upper()} {trade.coin} "
                f"@ ${trade.entry_price:.4f} | "
                f"Size: ${trade.position_size_usd:.2f} | "
                f"TP: ${trade.take_profit_price:.4f} | "
                f"SL: ${trade.stop_loss_price:.4f} | "
                f"Confidence: {trade.ai_confidence:.0f}%"
            )
        else:
            # Live mode — not implemented yet
            trade.status = EventTradeStatus.FAILED
            trade.error_message = "Live execution not yet implemented for event trades"
            logger.warning("Live execution not implemented — skipping")

        # Save and register
        await self.db.save_trade(trade)
        if trade.status == EventTradeStatus.OPEN:
            self.risk_manager.record_trade_open(trade)

        return trade

    async def check_and_close_positions(self, price_getter) -> list[EventTrade]:
        """
        Check all open positions for exit conditions.

        Args:
            price_getter: async function(symbol) -> current_price

        Returns:
            List of closed trades.
        """
        closed = []

        for trade in list(self.risk_manager.open_trades):
            try:
                current_price = await price_getter(trade.symbol)
                if current_price is None or current_price <= 0:
                    continue

                exit_status = self.position_manager.check_exit_conditions(
                    trade, current_price
                )

                if exit_status:
                    trade = self.position_manager.close_trade(
                        trade, current_price, exit_status
                    )
                    self.risk_manager.record_trade_close(trade)
                    await self.db.save_trade(trade)
                    await self.db.update_event_daily_pnl(trade)
                    closed.append(trade)

            except Exception as e:
                logger.error(f"Error checking position {trade.id}: {e}")

        return closed
