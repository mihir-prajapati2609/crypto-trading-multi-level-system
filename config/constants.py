"""
Crypto Arbitrage Bot — Constants

Exchange-specific constants, fee tables, and static configuration.
"""

from dataclasses import dataclass

# ============================================================
# Exchange Fee Structures (as of 2026)
# ============================================================

@dataclass(frozen=True)
class FeeStructure:
    """Fee structure for an exchange tier."""
    maker: float    # Maker fee as decimal (0.001 = 0.1%)
    taker: float    # Taker fee as decimal
    discount_token: str  # Native token for fee discount
    discount_pct: float  # Discount percentage when using native token


# Base tier fees (lowest tier — new accounts)
EXCHANGE_FEES = {
    "binance": FeeStructure(
        maker=0.0010,    # 0.10%
        taker=0.0010,    # 0.10%
        discount_token="BNB",
        discount_pct=0.25,  # 25% discount with BNB
    ),
    "okx": FeeStructure(
        maker=0.0008,    # 0.08%
        taker=0.0010,    # 0.10%
        discount_token="OKB",
        discount_pct=0.20,
    ),
    "kucoin": FeeStructure(
        maker=0.0010,
        taker=0.0010,
        discount_token="KCS",
        discount_pct=0.20,
    ),
    "bybit": FeeStructure(
        maker=0.0010,
        taker=0.0010,
        discount_token="",
        discount_pct=0.0,
    ),
}


def get_effective_fee(exchange: str, side: str = "taker", use_discount: bool = True) -> float:
    """
    Get the effective trading fee for an exchange.
    
    Args:
        exchange: Exchange name (e.g., 'binance')
        side: 'maker' or 'taker'
        use_discount: Whether to apply native token discount
    
    Returns:
        Fee as decimal (e.g., 0.00075 for 0.075%)
    """
    fee_info = EXCHANGE_FEES.get(exchange)
    if fee_info is None:
        return 0.0010  # Default to 0.1%
    
    base_fee = fee_info.maker if side == "maker" else fee_info.taker
    
    if use_discount and fee_info.discount_pct > 0:
        return base_fee * (1 - fee_info.discount_pct)
    
    return base_fee


# ============================================================
# Trading Constants
# ============================================================

# Minimum trade amounts (in USDT) by exchange
MIN_TRADE_AMOUNT = {
    "binance": 5.0,     # $5 minimum order
    "okx": 1.0,         # $1 minimum order
    "kucoin": 1.0,
    "bybit": 1.0,
}

# Maximum number of order book levels to fetch
ORDER_BOOK_DEPTH = 10

# WebSocket reconnection settings
WS_RECONNECT_DELAY_SECONDS = 1.0
WS_RECONNECT_MAX_DELAY_SECONDS = 60.0
WS_RECONNECT_MULTIPLIER = 2.0
WS_HEARTBEAT_TIMEOUT_SECONDS = 30.0

# Scanner settings
SCANNER_TICK_INTERVAL_MS = 100  # Process opportunities every 100ms

# Quote currencies we support
QUOTE_CURRENCIES = ["USDT", "BUSD", "USDC"]

# Preferred quote for triangular arbitrage
PREFERRED_QUOTE = "USDT"

# Base currencies for triangle routes
TRIANGLE_BASES = ["BTC", "ETH", "BNB"]

# ============================================================
# Model & Intelligence Constants
# ============================================================

# Cointegration
COINT_ROLLING_WINDOW_DAYS = 30
COINT_RETEST_INTERVAL_HOURS = 24

# Z-Score
ZSCORE_LOOKBACK_PERIODS = 60
ZSCORE_ROLLING_WINDOW = 20

# Ornstein-Uhlenbeck
OU_MIN_HALF_LIFE_MINUTES = 1.0
OU_MAX_HALF_LIFE_HOURS = 4.0

# GARCH
GARCH_LOOKBACK_PERIODS = 500
GARCH_RETRAIN_INTERVAL_HOURS = 12

# HMM Regime Detection
HMM_N_STATES = 3  # Calm, Active, Chaotic
HMM_LOOKBACK_DAYS = 30
HMM_RETRAIN_INTERVAL_HOURS = 168  # Weekly

# Regime multipliers for position sizing
REGIME_MULTIPLIERS = {
    0: 0.5,   # Calm — reduce activity
    1: 1.5,   # Active — increase activity
    2: 0.0,   # Chaotic — pause trading
}

# OBI Model
OBI_RETRAIN_INTERVAL_HOURS = 168  # Weekly
OBI_MIN_TRAINING_SAMPLES = 10000

# Anomaly Detection
ANOMALY_CONTAMINATION = 0.01  # 1% expected anomaly rate
ANOMALY_COOLDOWN_SECONDS = 300  # 5 min pause after anomaly

# ============================================================
# Funding Rate Constants
# ============================================================

FUNDING_RATE_INTERVAL_HOURS = 8  # Binance funds every 8h
MIN_FUNDING_RATE_THRESHOLD = 0.0003  # 0.03% minimum to enter
FUNDING_RATE_CHECK_INTERVAL_MINUTES = 15

# ============================================================
# Dashboard
# ============================================================

DASHBOARD_WS_PUSH_INTERVAL_MS = 1000  # Push updates every 1s
MAX_RECENT_TRADES_DISPLAY = 50
MAX_OPPORTUNITIES_DISPLAY = 100
