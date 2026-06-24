"""
Risk Manager — Realistic Position Sizing for $300 Capital

Implements:
- Kelly Criterion with fractional Kelly (25%) based on historical win/loss data
- Hard cap: max $15/trade (5% of $300)
- Realistic daily loss limit: $6 (2% of $300)
- Win rate, avg win/loss, profit factor tracking
- Risk:Reward calculation per opportunity
"""

import logging
import time
from typing import Tuple, Optional

from config.settings import get_settings
from data.models import Opportunity, Trade, RegimeState
from data.database import Database

logger = logging.getLogger(__name__)

# ── Hard limits for $300 capital ──────────────────────────────────────────────
MAX_TRADE_USD       = 15.0   # Absolute max position size
MIN_TRADE_USD       = 10.0   # Binance minimum order
DEFAULT_CAPITAL     = 300.0
MAX_POSITION_PCT    = 0.05   # 5% per trade
FRACTIONAL_KELLY    = 0.25   # Conservative: use 25% of Kelly fraction


class RiskManager:
    """
    Risk controller with realistic position sizing for small capital ($300).
    Uses Kelly Criterion when enough history exists, otherwise fixed 4% sizing.
    """
    
    def __init__(self, db: Database):
        self.settings       = get_settings().trading
        self.db             = db
        self.daily_pnl      = 0.0
        self.consecutive_losses = 0
        self.is_paused      = False
        self.open_positions = 0

        # Rolling performance stats (updated from DB on init)
        self._win_count     = 0
        self._loss_count    = 0
        self._total_wins    = 0.0   # Sum of winning trade profits
        self._total_losses  = 0.0   # Sum of losing trade losses (absolute)
        self._capital       = DEFAULT_CAPITAL

    async def initialize(self):
        """Loads today's P&L and rolling performance stats from DB."""
        today_data = await self.db.get_today_pnl()
        self.daily_pnl = today_data.get("net_pnl", 0.0)

        # Load rolling analytics to power Kelly sizing
        analytics = await self.db.get_analytics_summary()
        self._win_count   = analytics.get("wins",   0)
        self._loss_count  = analytics.get("losses", 0)
        avg_win  = analytics.get("avg_win_usd",  0.0)
        avg_loss = analytics.get("avg_loss_usd", 0.0)
        self._total_wins   = avg_win  * self._win_count
        self._total_losses = avg_loss * self._loss_count

        logger.info(
            f"[RiskManager] Initialized — daily_pnl=${self.daily_pnl:.2f} "
            f"wins={self._win_count} losses={self._loss_count} "
            f"avg_win=${avg_win:.4f} avg_loss=${avg_loss:.4f}"
        )

    # ── Pre-trade checks ──────────────────────────────────────────────────────

    def check_pre_trade(self, opportunity: Opportunity, available_balance: float) -> Tuple[bool, str]:
        """Checks if an opportunity passes all risk gates."""
        if self.is_paused:
            return False, "Trading is paused (Kill Switch)"

        if self.consecutive_losses >= self.settings.consecutive_loss_pause:
            return False, f"Paused: {self.consecutive_losses} consecutive losses"

        if opportunity.regime == RegimeState.CHAOTIC:
            return False, "Skipped: CHAOTIC regime"

        if opportunity.net_profit_pct <= 0:
            return False, f"Net profit {opportunity.net_profit_pct:.3f}% is zero or negative"

        if opportunity.net_profit_pct < self.settings.min_profit_threshold:
            return False, (
                f"Net profit {opportunity.net_profit_pct:.3f}% "
                f"below threshold {self.settings.min_profit_threshold:.3f}%"
            )

        if self.open_positions >= self.settings.max_concurrent_positions:
            return False, "Max concurrent positions reached"

        # Daily loss hard stop
        max_daily_loss_usd = self._capital * (self.settings.daily_loss_limit_pct / 100.0)
        if self.daily_pnl <= -max_daily_loss_usd:
            return False, f"Daily loss limit hit: ${self.daily_pnl:.2f} / -${max_daily_loss_usd:.2f}"

        return True, "Approved"

    # ── Position sizing ───────────────────────────────────────────────────────

    def calculate_position_size(
        self,
        opportunity: Opportunity,
        available_balance: float,
        volatility: float = 0.0,
        regime_mult: float = 1.0,
    ) -> float:
        """
        Calculate optimal position size using fractional Kelly Criterion.
        Falls back to fixed 4% of capital when insufficient history.
        Always caps at MAX_TRADE_USD and available balance.
        """
        total_trades = self._win_count + self._loss_count

        if total_trades >= 20:
            # ── Kelly Criterion sizing ───────────────────────────────────────
            win_rate = self._win_count / total_trades
            loss_rate = 1.0 - win_rate
            avg_win  = self._total_wins   / self._win_count   if self._win_count  > 0 else 0.01
            avg_loss = self._total_losses / self._loss_count  if self._loss_count > 0 else 0.01

            if avg_loss > 0:
                kelly_f = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
                kelly_f = max(0.0, kelly_f)  # Can't be negative
                fraction = kelly_f * FRACTIONAL_KELLY
                size = available_balance * fraction
            else:
                size = available_balance * 0.04  # fallback
        else:
            # ── Fixed 4% sizing while building history ───────────────────────
            size = available_balance * 0.04

        # Regime adjustment
        size = size * min(regime_mult, 1.2)

        # Hard guards
        size = max(MIN_TRADE_USD, min(size, MAX_TRADE_USD))
        size = min(size, available_balance * MAX_POSITION_PCT)
        return round(size, 2)

    # ── Risk:Reward ───────────────────────────────────────────────────────────

    def calculate_risk_reward(self, opportunity: Opportunity) -> float:
        """
        Returns Risk:Reward ratio for an opportunity.
        For arb trades: reward = net_profit_pct, risk = max slippage + fees if reversed.
        """
        net_reward = opportunity.net_profit_pct
        # Worst case: fill at wrong price (reverse slippage) + fees again
        estimated_risk = opportunity.total_fees_pct + 0.1   # fees + reversal slippage
        if estimated_risk <= 0:
            return 0.0
        return round(net_reward / estimated_risk, 2)

    @property
    def win_rate(self) -> float:
        total = self._win_count + self._loss_count
        return (self._win_count / total * 100) if total > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        """Gross profit / gross loss. > 1.0 means profitable system."""
        if self._total_losses <= 0:
            return float('inf') if self._total_wins > 0 else 0.0
        return round(self._total_wins / self._total_losses, 3)

    # ── Trade recording ───────────────────────────────────────────────────────

    async def record_trade_result(self, trade: Trade):
        """Updates internal risk state based on a completed trade."""
        if trade.net_profit_usd > 0:
            self.consecutive_losses = 0
            self._win_count   += 1
            self._total_wins  += trade.net_profit_usd
        else:
            self.consecutive_losses += 1
            self._loss_count  += 1
            self._total_losses += abs(trade.net_profit_usd)

        self.daily_pnl += trade.net_profit_usd
        await self.db.update_daily_pnl(trade)

        if self.consecutive_losses >= self.settings.consecutive_loss_pause:
            logger.warning(
                f"[RiskManager] {self.consecutive_losses} consecutive losses. "
                f"Temporarily pausing trading."
            )

    def is_trading_allowed(self) -> bool:
        return not self.is_paused and self.consecutive_losses < self.settings.consecutive_loss_pause

    def emergency_stop(self):
        self.is_paused = True
        logger.critical("EMERGENCY STOP ACTIVATED. All trading paused.")

    def resume(self):
        self.is_paused = False
        self.consecutive_losses = 0
        logger.info("Trading resumed.")
