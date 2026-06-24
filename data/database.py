"""
Crypto Arbitrage Bot — Database Layer

SQLite database with async operations for trade logging,
opportunity tracking, coin scores, and analytics.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from data.models import (
    Trade, TradeOrder, Opportunity, CoinScore, DailyPnL,
    BalanceSnapshot, TradeStatus, StrategyType, OrderSide, OrderType,
)

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    orders_json TEXT NOT NULL,
    opportunity_id TEXT,
    gross_profit_usd REAL DEFAULT 0,
    total_fees_usd REAL DEFAULT 0,
    net_profit_usd REAL DEFAULT 0,
    net_profit_pct REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT DEFAULT '',
    is_paper INTEGER DEFAULT 1,
    timestamp REAL NOT NULL,
    completed_at REAL
);

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchanges_json TEXT,
    buy_price REAL DEFAULT 0,
    sell_price REAL DEFAULT 0,
    buy_exchange TEXT DEFAULT '',
    sell_exchange TEXT DEFAULT '',
    gross_profit_pct REAL DEFAULT 0,
    total_fees_pct REAL DEFAULT 0,
    net_profit_pct REAL DEFAULT 0,
    estimated_profit_usd REAL DEFAULT 0,
    z_score REAL DEFAULT 0,
    confidence REAL DEFAULT 0,
    regime TEXT DEFAULT 'active',
    suggested_amount_usd REAL DEFAULT 0,
    was_executed INTEGER DEFAULT 0,
    skip_reason TEXT DEFAULT '',
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS coin_scores (
    symbol TEXT NOT NULL,
    base_currency TEXT NOT NULL,
    exchanges_json TEXT,
    trend_strength_score REAL DEFAULT 0,
    volume_increase_score REAL DEFAULT 0,
    liquidity_score REAL DEFAULT 0,
    volatility_score REAL DEFAULT 0,
    breakout_probability REAL DEFAULT 0,
    risk_score REAL DEFAULT 0,
    composite_score REAL DEFAULT 0,
    rank INTEGER DEFAULT 0,
    avg_spread_pct REAL DEFAULT 0,
    avg_daily_volume_usd REAL DEFAULT 0,
    listing_age_days INTEGER DEFAULT 0,
    is_cointegrated INTEGER DEFAULT 0,
    timestamp REAL NOT NULL,
    PRIMARY KEY (symbol, timestamp)
);

CREATE TABLE IF NOT EXISTS balance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    total_usd REAL DEFAULT 0,
    free_usd REAL DEFAULT 0,
    used_usd REAL DEFAULT 0,
    assets_json TEXT,
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date TEXT PRIMARY KEY,
    gross_pnl REAL DEFAULT 0,
    total_fees REAL DEFAULT 0,
    net_pnl REAL DEFAULT 0,
    trade_count INTEGER DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS model_performance (
    model_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    last_retrain REAL,
    timestamp REAL NOT NULL,
    PRIMARY KEY (model_name, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_opportunities_timestamp ON opportunities(timestamp);
CREATE INDEX IF NOT EXISTS idx_coin_scores_composite ON coin_scores(composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_balance_timestamp ON balance_snapshots(timestamp);
"""


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect to database and create tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row

        # Enable WAL mode for concurrent reads
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")

        # Create tables
        await self._db.executescript(CREATE_TABLES_SQL)
        await self._db.commit()
        logger.info(f"Database connected: {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Database connection closed")

    # ---- Trade Operations ----

    async def save_trade(self, trade: Trade) -> None:
        """Save a completed trade."""
        orders_json = json.dumps([
            {
                "id": o.id, "exchange": o.exchange, "symbol": o.symbol,
                "side": o.side.value, "order_type": o.order_type.value,
                "price": o.price, "quantity": o.quantity,
                "filled_quantity": o.filled_quantity, "filled_price": o.filled_price,
                "fee": o.fee, "fee_currency": o.fee_currency,
                "status": o.status.value, "exchange_order_id": o.exchange_order_id,
                "timestamp": o.timestamp,
            }
            for o in trade.orders
        ])

        await self._db.execute(
            """INSERT OR REPLACE INTO trades
               (id, strategy, symbol, orders_json, opportunity_id,
                gross_profit_usd, total_fees_usd, net_profit_usd, net_profit_pct,
                status, error_message, is_paper, timestamp, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade.id, trade.strategy.value, trade.symbol, orders_json,
             trade.opportunity_id, trade.gross_profit_usd, trade.total_fees_usd,
             trade.net_profit_usd, trade.net_profit_pct, trade.status.value,
             trade.error_message, int(trade.is_paper), trade.timestamp,
             trade.completed_at),
        )
        await self._db.commit()

    async def get_recent_trades(self, limit: int = 50) -> list[dict]:
        """Get most recent trades."""
        cursor = await self._db.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_trades_since(self, since_timestamp: float) -> list[dict]:
        """Get all trades since a given timestamp."""
        cursor = await self._db.execute(
            "SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp", (since_timestamp,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Opportunity Operations ----

    async def save_opportunity(self, opp: Opportunity) -> None:
        """Save a detected opportunity."""
        await self._db.execute(
            """INSERT OR REPLACE INTO opportunities
               (id, strategy, symbol, exchanges_json,
                buy_price, sell_price, buy_exchange, sell_exchange,
                gross_profit_pct, total_fees_pct, net_profit_pct, estimated_profit_usd,
                z_score, confidence, regime, suggested_amount_usd,
                was_executed, skip_reason, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (opp.id, opp.strategy.value, opp.symbol, json.dumps(opp.exchanges),
             opp.buy_price, opp.sell_price, opp.buy_exchange, opp.sell_exchange,
             opp.gross_profit_pct, opp.total_fees_pct, opp.net_profit_pct,
             opp.estimated_profit_usd, opp.z_score, opp.confidence,
             opp.regime.value, opp.suggested_amount_usd,
             int(opp.was_executed), opp.skip_reason, opp.timestamp),
        )
        await self._db.commit()

    async def get_recent_opportunities(self, limit: int = 100) -> list[dict]:
        """Get most recent opportunities."""
        cursor = await self._db.execute(
            "SELECT * FROM opportunities ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Coin Score Operations ----

    async def save_coin_scores(self, scores: list[CoinScore]) -> None:
        """Save a batch of coin scores."""
        for s in scores:
            await self._db.execute(
                """INSERT OR REPLACE INTO coin_scores
                   (symbol, base_currency, exchanges_json,
                    trend_strength_score, volume_increase_score, liquidity_score,
                    volatility_score, breakout_probability, risk_score,
                    composite_score, rank, avg_spread_pct, avg_daily_volume_usd,
                    listing_age_days, is_cointegrated, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s.symbol, s.base_currency, json.dumps(s.exchanges),
                 s.trend_strength_score, s.volume_increase_score, s.liquidity_score,
                 s.volatility_score, s.breakout_probability, s.risk_score,
                 s.composite_score, s.rank, s.avg_spread_pct, s.avg_daily_volume_usd,
                 s.listing_age_days, int(s.is_cointegrated), s.timestamp),
            )
        await self._db.commit()

    async def get_top_coins(self, limit: int = 25) -> list[dict]:
        """Get the highest-scored coins from the latest scan."""
        cursor = await self._db.execute(
            """SELECT * FROM coin_scores
               WHERE timestamp = (SELECT MAX(timestamp) FROM coin_scores)
               ORDER BY composite_score DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Balance Operations ----

    async def save_balance(self, snapshot: BalanceSnapshot) -> None:
        """Save a balance snapshot."""
        await self._db.execute(
            """INSERT INTO balance_snapshots
               (exchange, total_usd, free_usd, used_usd, assets_json, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (snapshot.exchange, snapshot.total_usd, snapshot.free_usd,
             snapshot.used_usd, json.dumps(snapshot.assets), snapshot.timestamp),
        )
        await self._db.commit()

    async def get_latest_balances(self) -> list[dict]:
        """Get the most recent balance for each exchange."""
        cursor = await self._db.execute(
            """SELECT * FROM balance_snapshots
               WHERE id IN (
                   SELECT MAX(id) FROM balance_snapshots GROUP BY exchange
               )"""
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Daily P&L Operations ----

    async def update_daily_pnl(self, trade: Trade) -> None:
        """Update daily P&L based on a completed trade."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        is_win = 1 if trade.net_profit_usd > 0 else 0
        is_loss = 1 if trade.net_profit_usd < 0 else 0

        await self._db.execute(
            """INSERT INTO daily_pnl (date, gross_pnl, total_fees, net_pnl, trade_count, win_count, loss_count)
               VALUES (?, ?, ?, ?, 1, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   gross_pnl = gross_pnl + excluded.gross_pnl,
                   total_fees = total_fees + excluded.total_fees,
                   net_pnl = net_pnl + excluded.net_pnl,
                   trade_count = trade_count + 1,
                   win_count = win_count + excluded.win_count,
                   loss_count = loss_count + excluded.loss_count""",
            (today, trade.gross_profit_usd, trade.total_fees_usd,
             trade.net_profit_usd, is_win, is_loss),
        )
        await self._db.commit()

    async def get_daily_pnl(self, days: int = 30) -> list[dict]:
        """Get daily P&L for the last N days."""
        cursor = await self._db.execute(
            "SELECT * FROM daily_pnl ORDER BY date DESC LIMIT ?", (days,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_today_pnl(self) -> dict:
        """Get today's P&L summary."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor = await self._db.execute(
            "SELECT * FROM daily_pnl WHERE date = ?", (today,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return {"date": today, "gross_pnl": 0, "total_fees": 0,
                "net_pnl": 0, "trade_count": 0, "win_count": 0, "loss_count": 0}

    # ---- Model Performance ----

    async def save_model_metric(self, model_name: str, metric_name: str,
                                  value: float, sample_count: int = 0) -> None:
        """Save a model performance metric."""
        await self._db.execute(
            """INSERT INTO model_performance
               (model_name, metric_name, metric_value, sample_count, last_retrain, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (model_name, metric_name, value, sample_count, time.time(), time.time()),
        )
        await self._db.commit()

    # ---- Analytics ----

    async def get_strategy_performance(self) -> list[dict]:
        """Get P&L breakdown by strategy."""
        cursor = await self._db.execute(
            """SELECT strategy,
                      COUNT(*) as trade_count,
                      SUM(net_profit_usd) as total_pnl,
                      AVG(net_profit_usd) as avg_pnl,
                      SUM(CASE WHEN net_profit_usd > 0 THEN 1 ELSE 0 END) as wins,
                      SUM(CASE WHEN net_profit_usd <= 0 THEN 1 ELSE 0 END) as losses
               FROM trades
               WHERE status = 'filled'
               GROUP BY strategy"""
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_cumulative_pnl(self, days: int = 30) -> list[dict]:
        """Get cumulative P&L over time for charting."""
        cursor = await self._db.execute(
            """SELECT date, net_pnl,
                      SUM(net_pnl) OVER (ORDER BY date) as cumulative_pnl
               FROM daily_pnl
               ORDER BY date DESC LIMIT ?""",
            (days,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_analytics_summary(self) -> dict:
        """
        Compute comprehensive analytics from all filled trades.
        Returns: win_rate, profit_factor, risk_reward, max_drawdown,
                 sharpe_ratio, expectancy, total_fees.
        """
        cursor = await self._db.execute(
            """SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN net_profit_usd > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN net_profit_usd < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN net_profit_usd > 0 THEN net_profit_usd ELSE 0 END) as gross_wins,
                SUM(CASE WHEN net_profit_usd < 0 THEN ABS(net_profit_usd) ELSE 0 END) as gross_losses,
                AVG(CASE WHEN net_profit_usd > 0 THEN net_profit_usd ELSE NULL END) as avg_win_usd,
                AVG(CASE WHEN net_profit_usd < 0 THEN ABS(net_profit_usd) ELSE NULL END) as avg_loss_usd,
                SUM(total_fees_usd) as total_fees_paid,
                SUM(net_profit_usd) as total_net_pnl
               FROM trades
               WHERE status = 'filled'"""
        )
        row = await cursor.fetchone()
        if not row:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate_pct": 0.0, "profit_factor": 0.0,
                "avg_win_usd": 0.0, "avg_loss_usd": 0.0,
                "risk_reward_ratio": 0.0, "total_fees_paid": 0.0,
                "total_net_pnl": 0.0, "expectancy_per_trade": 0.0,
                "max_drawdown_usd": 0.0, "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
            }

        d = dict(row)
        wins       = d.get("wins", 0) or 0
        losses     = d.get("losses", 0) or 0
        total      = d.get("total_trades", 0) or 0
        gross_wins = d.get("gross_wins", 0.0) or 0.0
        gross_loss = d.get("gross_losses", 0.0) or 0.0
        avg_win    = d.get("avg_win_usd", 0.0) or 0.0
        avg_loss   = d.get("avg_loss_usd", 0.0) or 0.0

        win_rate   = (wins / total * 100) if total > 0 else 0.0
        profit_factor = (gross_wins / gross_loss) if gross_loss > 0 else (float('inf') if gross_wins > 0 else 0.0)
        rr_ratio   = (avg_win / avg_loss) if avg_loss > 0 else 0.0

        # Expectancy per trade
        wr = win_rate / 100
        lr = 1.0 - wr
        expectancy = (wr * avg_win) - (lr * avg_loss)

        # Max drawdown from daily PnL sequence
        max_dd_usd, max_dd_pct = await self._calc_max_drawdown()

        # Sharpe ratio from daily PnL
        sharpe = await self._calc_sharpe_ratio()

        return {
            "total_trades":     total,
            "wins":             wins,
            "losses":           losses,
            "win_rate_pct":     round(win_rate, 2),
            "profit_factor":    round(min(profit_factor, 99.9), 3),
            "avg_win_usd":      round(avg_win, 4),
            "avg_loss_usd":     round(avg_loss, 4),
            "risk_reward_ratio": round(rr_ratio, 3),
            "total_fees_paid":  round(d.get("total_fees_paid", 0.0) or 0.0, 4),
            "total_net_pnl":    round(d.get("total_net_pnl", 0.0) or 0.0, 4),
            "expectancy_per_trade": round(expectancy, 4),
            "max_drawdown_usd": round(max_dd_usd, 4),
            "max_drawdown_pct": round(max_dd_pct, 3),
            "sharpe_ratio":     round(sharpe, 3),
        }

    async def _calc_max_drawdown(self) -> tuple[float, float]:
        """Calculate maximum drawdown from cumulative daily PnL series."""
        cursor = await self._db.execute(
            "SELECT net_pnl FROM daily_pnl ORDER BY date ASC"
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0.0, 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        initial_capital = 300.0

        for row in rows:
            cumulative += row["net_pnl"]
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)

        max_dd_pct = (max_dd / (initial_capital + peak)) * 100 if (initial_capital + peak) > 0 else 0.0
        return max_dd, max_dd_pct

    async def _calc_sharpe_ratio(self, risk_free_daily: float = 0.0) -> float:
        """Calculate annualised Sharpe ratio from daily net PnL."""
        cursor = await self._db.execute(
            "SELECT net_pnl FROM daily_pnl ORDER BY date ASC"
        )
        rows = await cursor.fetchall()
        if len(rows) < 3:
            return 0.0

        returns = [r["net_pnl"] for r in rows]
        n   = len(returns)
        avg = sum(returns) / n
        variance = sum((r - avg) ** 2 for r in returns) / n
        std = variance ** 0.5

        if std == 0:
            return 0.0
        sharpe_daily  = (avg - risk_free_daily) / std
        sharpe_annual = sharpe_daily * (252 ** 0.5)
        return sharpe_annual

    async def get_equity_curve(self, initial_capital: float = 300.0) -> list[dict]:
        """
        Returns a time-series of account equity for charting.
        [{"date": "YYYY-MM-DD", "equity": 300.45, "pnl": 0.45}, ...]
        """
        cursor = await self._db.execute(
            "SELECT date, net_pnl FROM daily_pnl ORDER BY date ASC"
        )
        rows = await cursor.fetchall()
        result = []
        equity = initial_capital
        for row in rows:
            equity += row["net_pnl"]
            result.append({
                "date":   row["date"],
                "equity": round(equity, 4),
                "pnl":    round(row["net_pnl"], 4),
            })
        return result

