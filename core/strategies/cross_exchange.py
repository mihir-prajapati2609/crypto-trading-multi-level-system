import logging
from typing import List, Dict, Any
from core.strategies.base import BaseStrategy
from data.models import Opportunity, StrategyType, RegimeState

logger = logging.getLogger(__name__)

# Realistic break-even: 2× taker fees (0.075% Binance + 0.1% OKX) + slippage buffer
# = 0.175% + 0.10% slippage = ~0.30% minimum gross spread to net positive
MIN_GROSS_SPREAD_PCT = 0.30

# Max single trade size for $300 capital: 5% per trade = $15
MAX_TRADE_USD  = 15.0
MIN_TRADE_USD  = 10.0   # Binance minimum order ~$10


class CrossExchangeStrategy(BaseStrategy):
    """
    Cross-exchange arbitrage strategy.

    Detects price discrepancies between Binance and OKX for the same
    trading pair, net of realistic taker fees and slippage estimates.
    Only surfaces opportunities where the NET profit (after fees) is positive.
    """
    
    def __init__(self):
        super().__init__("cross_exchange")

    def _calc_net_profit_pct(
        self,
        buy_price: float,
        sell_price: float,
        buy_exchange: str,
        sell_exchange: str,
        size_usd: float = 12.0
    ) -> tuple[float, float]:
        """
        Returns (gross_pct, net_pct) after subtracting realistic fees.
        Fees: Binance taker = 0.075% (BNB discount), OKX taker = 0.10%
        """
        from core.executor import get_fee_rate
        buy_fee_rate  = get_fee_rate(buy_exchange,  "spot", "taker")
        sell_fee_rate = get_fee_rate(sell_exchange, "spot", "taker")

        gross_pct = (sell_price - buy_price) / buy_price * 100
        fees_pct  = (buy_fee_rate + sell_fee_rate) * 100
        # Add 0.04% estimated slippage (conservative Gaussian estimate for small orders)
        slippage_pct = 0.04
        net_pct = gross_pct - fees_pct - slippage_pct
        return gross_pct, net_pct

    def scan(self, market_data: Dict[str, Any], intelligence_signals: Dict[str, Any]) -> List[Opportunity]:
        opps = []
        order_books = market_data.get('order_books', {})
        binance_books = order_books.get('binance', {})
        okx_books     = order_books.get('okx', {})

        # Get available capital to size positions (default $300 → $12/trade)
        available_capital = intelligence_signals.get('available_capital', 300.0)
        trade_size = max(MIN_TRADE_USD, min(MAX_TRADE_USD, available_capital * 0.04))

        for symbol in binance_books:
            if symbol not in okx_books:
                continue

            b_ob = binance_books[symbol]
            o_ob = okx_books[symbol]

            # ── Direction 1: Buy Binance, Sell OKX ─────────────────────────
            if b_ob.asks and o_ob.bids:
                b_ask = b_ob.best_ask
                o_bid = o_ob.best_bid

                if o_bid > b_ask:
                    gross_pct, net_pct = self._calc_net_profit_pct(
                        b_ask, o_bid, "binance", "okx", trade_size
                    )
                    if gross_pct >= MIN_GROSS_SPREAD_PCT and net_pct > 0:
                        opp = Opportunity(
                            strategy=StrategyType.CROSS_EXCHANGE,
                            symbol=symbol,
                            exchanges=['binance', 'okx'],
                            buy_price=b_ask,
                            sell_price=o_bid,
                            buy_exchange='binance',
                            sell_exchange='okx',
                            gross_profit_pct=round(gross_pct, 4),
                            total_fees_pct=round(gross_pct - net_pct, 4),
                            net_profit_pct=round(net_pct, 4),
                            estimated_profit_usd=round(trade_size * net_pct / 100, 4),
                            suggested_amount_usd=trade_size,
                            regime=intelligence_signals.get('regime', RegimeState.ACTIVE)
                        )
                        opps.append(opp)
                        logger.info(
                            f"[Cross-Exchange] {symbol} BUY Binance/SELL OKX "
                            f"gross={gross_pct:.3f}% net={net_pct:.3f}% size=${trade_size:.0f}"
                        )

            # ── Direction 2: Buy OKX, Sell Binance ─────────────────────────
            if o_ob.asks and b_ob.bids:
                o_ask = o_ob.best_ask
                b_bid = b_ob.best_bid

                if b_bid > o_ask:
                    gross_pct, net_pct = self._calc_net_profit_pct(
                        o_ask, b_bid, "okx", "binance", trade_size
                    )
                    if gross_pct >= MIN_GROSS_SPREAD_PCT and net_pct > 0:
                        opp = Opportunity(
                            strategy=StrategyType.CROSS_EXCHANGE,
                            symbol=symbol,
                            exchanges=['okx', 'binance'],
                            buy_price=o_ask,
                            sell_price=b_bid,
                            buy_exchange='okx',
                            sell_exchange='binance',
                            gross_profit_pct=round(gross_pct, 4),
                            total_fees_pct=round(gross_pct - net_pct, 4),
                            net_profit_pct=round(net_pct, 4),
                            estimated_profit_usd=round(trade_size * net_pct / 100, 4),
                            suggested_amount_usd=trade_size,
                            regime=intelligence_signals.get('regime', RegimeState.ACTIVE)
                        )
                        opps.append(opp)
                        logger.info(
                            f"[Cross-Exchange] {symbol} BUY OKX/SELL Binance "
                            f"gross={gross_pct:.3f}% net={net_pct:.3f}% size=${trade_size:.0f}"
                        )

        return opps

    def validate(self, opportunity: Opportunity) -> bool:
        return opportunity.net_profit_pct > 0
