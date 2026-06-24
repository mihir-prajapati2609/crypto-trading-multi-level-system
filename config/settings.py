"""
Crypto Arbitrage Bot — Central Configuration

Loads settings from .env file and provides typed access
to all configuration parameters.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class ExchangeConfig:
    """Configuration for a single exchange."""
    name: str
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    sandbox: bool = False
    rate_limit: bool = True


@dataclass
class TradingConfig:
    """Trading strategy parameters."""
    min_profit_threshold: float = 0.15    # % net profit to execute
    max_position_pct: float = 30.0        # % of balance per trade
    daily_loss_limit_pct: float = 3.0     # % of capital before pause
    z_score_entry: float = 2.0            # Z-score to enter trade
    z_score_exit: float = 0.5             # Z-score to exit trade
    z_score_stop: float = 3.0             # Z-score stop-loss
    min_half_life_minutes: float = 1.0    # Min OU half-life
    max_half_life_hours: float = 4.0      # Max OU half-life
    max_concurrent_positions: int = 3     # Max open positions
    consecutive_loss_pause: int = 5       # Pause after N consecutive losses
    cooldown_after_loss_seconds: int = 60 # Cooldown after stop-loss
    
    # RSI Strategy Specifics
    rsi_max_concurrent: int = 2
    rsi_daily_trade_limit: int = 5


@dataclass
class DiscoveryConfig:
    """Coin discovery engine parameters."""
    rescan_interval_hours: float = 6.0    # How often to re-scan
    watchlist_size: int = 25              # Number of coins in watchlist
    min_daily_volume_usdt: float = 50000  # Minimum 24h volume
    max_daily_volume_usdt: float = 50_000_000  # Max volume (avoid HFT-dominated)
    cointegration_p_threshold: float = 0.05  # Max p-value for cointegration
    min_spread_volatility: float = 0.001  # Minimum spread std dev
    lookback_days: int = 30               # Historical data for analysis


@dataclass
class DashboardConfig:
    """Dashboard server settings."""
    host: str = "0.0.0.0"
    port: int = 8080
    api_key: str = "change_this"


@dataclass
class NotificationConfig:
    """Telegram notification settings."""
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    enabled: bool = False
    rate_limit_seconds: int = 30  # Min seconds between non-critical alerts


@dataclass
class Settings:
    """Master configuration container."""
    trading_mode: str = "paper"  # 'paper' or 'live'
    exchanges: dict[str, ExchangeConfig] = field(default_factory=dict)
    trading: TradingConfig = field(default_factory=TradingConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "arbitrage.db")
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")


def load_settings() -> Settings:
    """Load settings from environment variables."""
    settings = Settings()

    # Trading mode
    settings.trading_mode = os.getenv("TRADING_MODE", "paper").lower()

    # Binance
    binance_key = os.getenv("BINANCE_API_KEY", "")
    binance_secret = os.getenv("BINANCE_API_SECRET", "")
    settings.exchanges["binance"] = ExchangeConfig(
        name="binance",
        api_key=binance_key,
        api_secret=binance_secret,
    )

    # OKX
    okx_key = os.getenv("OKX_API_KEY", "")
    okx_secret = os.getenv("OKX_API_SECRET", "")
    settings.exchanges["okx"] = ExchangeConfig(
        name="okx",
        api_key=okx_key,
        api_secret=okx_secret,
        passphrase=os.getenv("OKX_PASSPHRASE", ""),
    )

    # Trading parameters
    settings.trading = TradingConfig(
        min_profit_threshold=float(os.getenv("MIN_PROFIT_THRESHOLD", "0.15")),
        max_position_pct=float(os.getenv("MAX_POSITION_PCT", "30")),
        daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "3.0")),
        z_score_entry=float(os.getenv("Z_SCORE_ENTRY", "2.0")),
        z_score_exit=float(os.getenv("Z_SCORE_EXIT", "0.5")),
        z_score_stop=float(os.getenv("Z_SCORE_STOP", "3.0")),
    )

    # Discovery
    settings.discovery = DiscoveryConfig(
        rescan_interval_hours=float(os.getenv("COIN_RESCAN_INTERVAL", "6")),
        watchlist_size=int(os.getenv("WATCHLIST_SIZE", "25")),
    )

    # Dashboard
    settings.dashboard = DashboardConfig(
        host=os.getenv("DASHBOARD_HOST", "0.0.0.0"),
        port=int(os.getenv("DASHBOARD_PORT", "8080")),
        api_key=os.getenv("DASHBOARD_API_KEY", "change_this"),
    )

    # Notifications
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    settings.notifications = NotificationConfig(
        telegram_bot_token=tg_token if tg_token else None,
        telegram_chat_id=tg_chat if tg_chat else None,
        enabled=bool(tg_token and tg_chat),
    )

    # Ensure directories exist
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    return settings


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
