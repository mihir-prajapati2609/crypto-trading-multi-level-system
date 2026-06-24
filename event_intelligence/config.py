"""
Event Intelligence — Self-contained Configuration

All settings for the event intelligence system, loaded from .env
with EVENT_* prefix. Completely independent of the main arbitrage config.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class CollectorConfig:
    """Polling intervals and toggles for each data source."""
    # Enable/disable individual sources
    rss_enabled: bool = True
    binance_announcements_enabled: bool = True
    coinbase_blog_enabled: bool = True
    coingecko_enabled: bool = True
    coinmarketcap_enabled: bool = True
    github_enabled: bool = True
    fear_greed_enabled: bool = True
    google_trends_enabled: bool = True
    onchain_whale_enabled: bool = True

    # Polling intervals in seconds
    rss_interval: int = 60
    binance_announcements_interval: int = 30
    coinbase_blog_interval: int = 120
    coingecko_interval: int = 60
    coinmarketcap_interval: int = 120
    github_interval: int = 300
    fear_greed_interval: int = 300
    google_trends_interval: int = 600
    onchain_whale_interval: int = 120

    # RSS feed URLs
    rss_feeds: list[str] = field(default_factory=lambda: [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://theblock.co/rss.xml",
    ])

    # GitHub repos to monitor (owner/repo)
    github_repos: list[str] = field(default_factory=lambda: [
        "bitcoin/bitcoin",
        "ethereum/go-ethereum",
        "solana-labs/solana",
        "ApeWorX/ape",
    ])

    # Known whale wallets to track (Ethereum addresses)
    whale_wallets: list[str] = field(default_factory=lambda: [
        # Major exchange cold wallets / known whales
        "0x00000000219ab540356cBB839Cbe05303d7705Fa",  # ETH2 deposit
    ])


@dataclass
class ScoringConfig:
    """Thresholds and weights for the scoring system."""
    min_confidence_to_trade: float = 90.0   # % AI confidence to trigger trade
    min_confidence_to_alert: float = 70.0   # % to send notification
    min_sentiment_score: float = 60.0       # Min sentiment to consider

    # Agent weights (sum should be ~1.0)
    news_agent_weight: float = 0.25
    sentiment_agent_weight: float = 0.20
    whale_agent_weight: float = 0.20
    technical_agent_weight: float = 0.20
    risk_agent_weight: float = 0.15

    # Historical impact model
    impact_model_retrain_interval_hours: float = 168.0  # Weekly
    min_training_samples: int = 50
    impact_lookback_minutes: list[int] = field(
        default_factory=lambda: [1, 5, 30, 60, 1440]  # 1m, 5m, 30m, 1h, 24h
    )


@dataclass
class EventRiskConfig:
    """Risk management parameters for event-driven trades."""
    position_size_pct: float = 3.0          # % of capital per trade
    risk_per_trade_pct: float = 1.0         # Max risk per trade
    take_profit_pct: float = 5.0            # Take profit %
    stop_loss_pct: float = 2.0              # Stop loss %
    trailing_stop_enabled: bool = True
    trailing_stop_activation_pct: float = 2.0  # Activate after 2% profit
    trailing_stop_callback_pct: float = 1.0    # Trail by 1%
    max_open_trades: int = 5
    max_daily_loss_pct: float = 3.0         # Max daily loss %
    max_drawdown_pct: float = 10.0          # Max total drawdown %
    cooldown_after_loss_seconds: int = 120   # Cooldown after a loss


@dataclass
class EventIntelligenceConfig:
    """Master configuration for the Event Intelligence Engine."""
    enabled: bool = True
    mode: str = "observe"  # 'observe' = score only, 'trade' = score + execute

    collectors: CollectorConfig = field(default_factory=CollectorConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    risk: EventRiskConfig = field(default_factory=EventRiskConfig)

    db_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "event_intelligence.db"
    )

    # API keys for data sources
    etherscan_api_key: str = ""
    github_token: str = ""
    coingecko_api_key: str = ""  # Optional — free tier works without

    # Deduplication window (seconds) — events within this window are considered dupes
    dedup_window_seconds: int = 3600

    # Event processing
    max_events_per_minute: int = 100
    event_ttl_hours: int = 48  # How long to keep events in memory


def load_event_intelligence_config() -> EventIntelligenceConfig:
    """Load event intelligence config from environment variables."""
    config = EventIntelligenceConfig()

    config.enabled = os.getenv("EVENT_INTELLIGENCE_ENABLED", "true").lower() == "true"
    config.mode = os.getenv("EVENT_INTELLIGENCE_MODE", "observe").lower()

    # Scoring thresholds
    config.scoring.min_confidence_to_trade = float(
        os.getenv("EVENT_MIN_CONFIDENCE", "90")
    )

    # Risk parameters
    config.risk.position_size_pct = float(
        os.getenv("EVENT_MAX_POSITION_PCT", "3")
    )
    config.risk.max_open_trades = int(
        os.getenv("EVENT_MAX_OPEN_TRADES", "5")
    )
    config.risk.max_daily_loss_pct = float(
        os.getenv("EVENT_MAX_DAILY_LOSS_PCT", "3")
    )
    config.risk.max_drawdown_pct = float(
        os.getenv("EVENT_MAX_DRAWDOWN_PCT", "10")
    )

    # API keys
    config.etherscan_api_key = os.getenv("ETHERSCAN_API_KEY", "")
    config.github_token = os.getenv("GITHUB_TOKEN", "")
    config.coingecko_api_key = os.getenv("COINGECKO_API_KEY", "")

    # Ensure DB directory exists
    config.db_path.parent.mkdir(parents=True, exist_ok=True)

    return config


# Singleton
_ei_config: Optional[EventIntelligenceConfig] = None


def get_event_config() -> EventIntelligenceConfig:
    """Get or create the global event intelligence config."""
    global _ei_config
    if _ei_config is None:
        _ei_config = load_event_intelligence_config()
    return _ei_config
