"""
Event Intelligence — Independent Database Layer

Fully separate SQLite database for the event intelligence system.
Does not share tables or connections with the main arbitrage database.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from event_intelligence.models import (
    NewsEvent, EventScore, EventTrade, HistoricalImpact,
    AgentVote, SourceReliability, AgentPerformance,
    EventCategory, EventTradeStatus, TradeAction,
    VolumeLevel, WhaleActivity, SocialTrend,
)

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    url TEXT DEFAULT '',
    raw_data_json TEXT DEFAULT '{}',
    category TEXT DEFAULT 'other',
    affected_coins_json TEXT DEFAULT '[]',
    sentiment_score REAL DEFAULT 50.0,
    sentiment TEXT DEFAULT 'neutral',
    content_hash TEXT DEFAULT '',
    is_duplicate INTEGER DEFAULT 0,
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS event_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    coin TEXT NOT NULL,
    news_sentiment REAL DEFAULT 50.0,
    source_reliability REAL DEFAULT 50.0,
    historical_impact REAL DEFAULT 50.0,
    current_volume TEXT DEFAULT 'normal',
    whale_activity TEXT DEFAULT 'neutral',
    social_trend TEXT DEFAULT 'stable',
    ai_confidence REAL DEFAULT 50.0,
    trade_action TEXT DEFAULT 'skip',
    agent_votes_json TEXT DEFAULT '[]',
    category TEXT DEFAULT 'other',
    timestamp REAL NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS event_trades (
    id TEXT PRIMARY KEY,
    signal_id TEXT DEFAULT '',
    event_id TEXT DEFAULT '',
    coin TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry_price REAL DEFAULT 0,
    entry_time REAL DEFAULT 0,
    position_size_usd REAL DEFAULT 0,
    side TEXT DEFAULT 'buy',
    exit_price REAL DEFAULT 0,
    exit_time REAL DEFAULT 0,
    exit_reason TEXT DEFAULT 'pending',
    take_profit_price REAL DEFAULT 0,
    stop_loss_price REAL DEFAULT 0,
    trailing_stop_price REAL DEFAULT 0,
    highest_price REAL DEFAULT 0,
    gross_pnl_usd REAL DEFAULT 0,
    fees_usd REAL DEFAULT 0,
    net_pnl_usd REAL DEFAULT 0,
    net_pnl_pct REAL DEFAULT 0,
    status TEXT DEFAULT 'pending',
    is_paper INTEGER DEFAULT 1,
    ai_confidence REAL DEFAULT 0,
    error_message TEXT DEFAULT '',
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_impacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT DEFAULT '',
    coin TEXT NOT NULL,
    category TEXT DEFAULT 'other',
    price_before REAL DEFAULT 0,
    volume_before REAL DEFAULT 0,
    market_cap_before REAL DEFAULT 0,
    change_1m REAL,
    change_5m REAL,
    change_30m REAL,
    change_1h REAL,
    change_24h REAL,
    sentiment_score REAL DEFAULT 50.0,
    source_reliability REAL DEFAULT 50.0,
    pre_event_volume TEXT DEFAULT 'normal',
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS source_reliability (
    source_name TEXT PRIMARY KEY,
    total_events INTEGER DEFAULT 0,
    accurate_predictions INTEGER DEFAULT 0,
    reliability_score REAL DEFAULT 50.0,
    avg_impact_accuracy REAL DEFAULT 50.0,
    last_updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_performance (
    agent_name TEXT PRIMARY KEY,
    total_votes INTEGER DEFAULT 0,
    correct_direction INTEGER DEFAULT 0,
    avg_score_accuracy REAL DEFAULT 50.0,
    current_weight REAL DEFAULT 0.2,
    last_calibration REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS event_daily_pnl (
    date TEXT PRIMARY KEY,
    gross_pnl REAL DEFAULT 0,
    total_fees REAL DEFAULT 0,
    net_pnl REAL DEFAULT 0,
    trade_count INTEGER DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS model_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    accuracy REAL DEFAULT 0,
    precision_score REAL DEFAULT 0,
    recall REAL DEFAULT 0,
    f1_score REAL DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    checkpoint_path TEXT DEFAULT '',
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_hash ON events(content_hash);
CREATE INDEX IF NOT EXISTS idx_scores_event ON event_scores(event_id);
CREATE INDEX IF NOT EXISTS idx_scores_confidence ON event_scores(ai_confidence DESC);
CREATE INDEX IF NOT EXISTS idx_trades_status ON event_trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON event_trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_impacts_category ON historical_impacts(category);
"""


class EventDatabase:
    """Async SQLite database for the event intelligence system."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect and initialize schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(CREATE_TABLES_SQL)
        await self._db.commit()
        logger.info(f"Event Intelligence DB connected: {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # ---- Event Operations ----

    async def save_event(self, event: NewsEvent) -> None:
        """Save a raw news event."""
        await self._db.execute(
            """INSERT OR IGNORE INTO events
               (id, source, title, body, url, raw_data_json, category,
                affected_coins_json, sentiment_score, sentiment,
                content_hash, is_duplicate, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.id, event.source, event.title, event.body, event.url,
             json.dumps(event.raw_data), event.category.value,
             json.dumps(event.affected_coins), event.sentiment_score,
             event.sentiment.value, event.content_hash,
             int(event.is_duplicate), event.timestamp),
        )
        await self._db.commit()

    async def get_recent_events(self, limit: int = 50) -> list[dict]:
        """Get most recent events."""
        cursor = await self._db.execute(
            "SELECT * FROM events WHERE is_duplicate = 0 ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def event_hash_exists(self, content_hash: str) -> bool:
        """Check if an event with this hash already exists."""
        cursor = await self._db.execute(
            "SELECT 1 FROM events WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        )
        return await cursor.fetchone() is not None

    # ---- Score Operations ----

    async def save_score(self, score: EventScore) -> None:
        """Save an event score card."""
        votes_json = json.dumps([
            {
                "agent_name": v.agent_name, "score": v.score,
                "confidence": v.confidence, "direction": v.direction,
                "reasoning": v.reasoning, "weight": v.weight,
            }
            for v in score.agent_votes
        ])
        await self._db.execute(
            """INSERT INTO event_scores
               (event_id, coin, news_sentiment, source_reliability,
                historical_impact, current_volume, whale_activity,
                social_trend, ai_confidence, trade_action,
                agent_votes_json, category, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (score.event_id, score.coin, score.news_sentiment,
             score.source_reliability, score.historical_impact,
             score.current_volume.value, score.whale_activity.value,
             score.social_trend.value, score.ai_confidence,
             score.trade_action.value, votes_json,
             score.category.value, score.timestamp),
        )
        await self._db.commit()

    async def get_recent_scores(self, limit: int = 20) -> list[dict]:
        """Get most recent score cards."""
        cursor = await self._db.execute(
            """SELECT * FROM event_scores
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_high_confidence_scores(self, min_confidence: float = 80.0,
                                         limit: int = 10) -> list[dict]:
        """Get recent high-confidence scores."""
        cursor = await self._db.execute(
            """SELECT * FROM event_scores
               WHERE ai_confidence >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (min_confidence, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Trade Operations ----

    async def save_trade(self, trade: EventTrade) -> None:
        """Save or update an event-driven trade."""
        await self._db.execute(
            """INSERT OR REPLACE INTO event_trades
               (id, signal_id, event_id, coin, symbol,
                entry_price, entry_time, position_size_usd, side,
                exit_price, exit_time, exit_reason,
                take_profit_price, stop_loss_price, trailing_stop_price,
                highest_price, gross_pnl_usd, fees_usd, net_pnl_usd,
                net_pnl_pct, status, is_paper, ai_confidence,
                error_message, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade.id, trade.signal_id, trade.event_id, trade.coin,
             trade.symbol, trade.entry_price, trade.entry_time,
             trade.position_size_usd, trade.side, trade.exit_price,
             trade.exit_time, trade.exit_reason.value,
             trade.take_profit_price, trade.stop_loss_price,
             trade.trailing_stop_price, trade.highest_price,
             trade.gross_pnl_usd, trade.fees_usd, trade.net_pnl_usd,
             trade.net_pnl_pct, trade.status.value, int(trade.is_paper),
             trade.ai_confidence, trade.error_message, trade.timestamp),
        )
        await self._db.commit()

    async def get_open_trades(self) -> list[dict]:
        """Get all open event trades."""
        cursor = await self._db.execute(
            "SELECT * FROM event_trades WHERE status = 'open' ORDER BY entry_time",
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_recent_trades(self, limit: int = 50) -> list[dict]:
        """Get recent event trades."""
        cursor = await self._db.execute(
            "SELECT * FROM event_trades ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Historical Impact ----

    async def save_historical_impact(self, impact: HistoricalImpact) -> None:
        """Save historical impact data for model training."""
        await self._db.execute(
            """INSERT INTO historical_impacts
               (event_id, coin, category, price_before, volume_before,
                market_cap_before, change_1m, change_5m, change_30m,
                change_1h, change_24h, sentiment_score,
                source_reliability, pre_event_volume, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (impact.event_id, impact.coin, impact.category.value,
             impact.price_before, impact.volume_before,
             impact.market_cap_before, impact.change_1m, impact.change_5m,
             impact.change_30m, impact.change_1h, impact.change_24h,
             impact.sentiment_score, impact.source_reliability,
             impact.pre_event_volume_level.value, impact.timestamp),
        )
        await self._db.commit()

    async def get_impacts_by_category(self, category: str) -> list[dict]:
        """Get all historical impacts for a category (for training)."""
        cursor = await self._db.execute(
            "SELECT * FROM historical_impacts WHERE category = ? ORDER BY timestamp",
            (category,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_all_impacts(self) -> list[dict]:
        """Get all historical impact data."""
        cursor = await self._db.execute(
            "SELECT * FROM historical_impacts ORDER BY timestamp"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Source Reliability ----

    async def update_source_reliability(self, source: SourceReliability) -> None:
        """Update source reliability stats."""
        await self._db.execute(
            """INSERT OR REPLACE INTO source_reliability
               (source_name, total_events, accurate_predictions,
                reliability_score, avg_impact_accuracy, last_updated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source.source_name, source.total_events,
             source.accurate_predictions, source.reliability_score,
             source.avg_impact_accuracy, source.last_updated),
        )
        await self._db.commit()

    async def get_source_reliability(self, source_name: str) -> Optional[dict]:
        """Get reliability stats for a source."""
        cursor = await self._db.execute(
            "SELECT * FROM source_reliability WHERE source_name = ?",
            (source_name,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_source_reliabilities(self) -> list[dict]:
        """Get all source reliability stats."""
        cursor = await self._db.execute(
            "SELECT * FROM source_reliability ORDER BY reliability_score DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Agent Performance ----

    async def update_agent_performance(self, perf: AgentPerformance) -> None:
        """Update agent performance tracking."""
        await self._db.execute(
            """INSERT OR REPLACE INTO agent_performance
               (agent_name, total_votes, correct_direction,
                avg_score_accuracy, current_weight, last_calibration)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (perf.agent_name, perf.total_votes, perf.correct_direction,
             perf.avg_score_accuracy, perf.current_weight,
             perf.last_calibration),
        )
        await self._db.commit()

    async def get_all_agent_performance(self) -> list[dict]:
        """Get performance stats for all agents."""
        cursor = await self._db.execute(
            "SELECT * FROM agent_performance ORDER BY avg_score_accuracy DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Daily P&L ----

    async def update_event_daily_pnl(self, trade: EventTrade) -> None:
        """Update daily P&L from a closed trade."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        is_win = 1 if trade.net_pnl_usd > 0 else 0
        is_loss = 1 if trade.net_pnl_usd < 0 else 0
        await self._db.execute(
            """INSERT INTO event_daily_pnl
               (date, gross_pnl, total_fees, net_pnl, trade_count, win_count, loss_count)
               VALUES (?, ?, ?, ?, 1, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   gross_pnl = gross_pnl + excluded.gross_pnl,
                   total_fees = total_fees + excluded.total_fees,
                   net_pnl = net_pnl + excluded.net_pnl,
                   trade_count = trade_count + 1,
                   win_count = win_count + excluded.win_count,
                   loss_count = loss_count + excluded.loss_count""",
            (today, trade.gross_pnl_usd, trade.fees_usd,
             trade.net_pnl_usd, is_win, is_loss),
        )
        await self._db.commit()

    async def get_event_today_pnl(self) -> dict:
        """Get today's event trading P&L."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor = await self._db.execute(
            "SELECT * FROM event_daily_pnl WHERE date = ?", (today,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return {"date": today, "gross_pnl": 0, "total_fees": 0,
                "net_pnl": 0, "trade_count": 0, "win_count": 0, "loss_count": 0}

    async def get_event_total_pnl(self) -> float:
        """Get total P&L from all event trades."""
        cursor = await self._db.execute(
            "SELECT COALESCE(SUM(net_pnl), 0) as total FROM event_daily_pnl"
        )
        row = await cursor.fetchone()
        return float(row["total"]) if row else 0.0
