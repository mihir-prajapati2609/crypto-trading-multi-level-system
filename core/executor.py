import asyncio
import logging
import random
import time
import uuid
from typing import Dict, List, Any

from data.models import Opportunity, Trade, TradeOrder, TradeStatus, OrderSide, OrderType
from config.settings import get_settings
from data.database import Database
import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Realistic exchange fee schedules (taker rates by default)
# ─────────────────────────────────────────────────────────────
EXCHANGE_FEES = {
    "binance": {
        "spot":    {"maker": 0.00075, "taker": 0.00075},  # BNB discount
        "futures": {"maker": 0.0002,  "taker": 0.0005},
    },
    "okx": {
        "spot":    {"maker": 0.0008,  "taker": 0.001},
        "futures": {"maker": 0.0002,  "taker": 0.0005},
    },
    "default": {
        "spot":    {"maker": 0.001,   "taker": 0.001},
        "futures": {"maker": 0.0002,  "taker": 0.0006},
    },
}

def get_fee_rate(exchange: str, market_type: str = "spot", side: str = "taker") -> float:
    """Return the appropriate fee rate for an exchange/market/side combo."""
    schedule = EXCHANGE_FEES.get(exchange, EXCHANGE_FEES["default"])
    market   = schedule.get(market_type, schedule.get("spot", {}))
    return market.get(side, 0.001)

def simulate_slippage(price: float, size_usd: float, volume_24h_usd: float = 5_000_000) -> float:
    """
    Simulate realistic fill slippage.
    - Base: Gaussian noise with std ~0.02% (tight spreads, liquid coins)
    - Market impact: proportional to order size vs 24h volume
    Returns a price adjustment multiplier (1 + slippage_pct).
    """
    # Base random slippage (normal distribution, 0.02% std dev)
    base_slippage_pct = random.gauss(0.0, 0.0002)

    # Market impact: if order > 0.01% of daily volume, add impact
    market_impact_pct = 0.0
    if volume_24h_usd > 0:
        order_fraction = size_usd / volume_24h_usd
        if order_fraction > 0.0001:
            market_impact_pct = order_fraction * 0.5  # 0.5x fraction as impact

    # For small $300 capital orders, slippage is typically minimal
    total_slippage = base_slippage_pct + market_impact_pct
    # Cap at ±0.15% to avoid outlier simulations
    total_slippage = max(-0.0015, min(0.0015, total_slippage))
    return 1.0 + total_slippage


class TradeExecutor:
    """Executes trades with realistic fee and slippage modelling."""
    
    def __init__(self, db: Database, exchanges: Dict[str, ccxt.Exchange]):
        self.settings = get_settings()
        self.db = db
        self.exchanges = exchanges
        self.is_paper = self.settings.trading_mode == "paper"

    async def execute(self, opportunity: Opportunity) -> Trade:
        """Executes the given opportunity."""
        logger.info(f"Executing {'PAPER ' if self.is_paper else 'LIVE '}trade for opportunity {opportunity.id}")
        
        trade = Trade(
            strategy=opportunity.strategy,
            symbol=opportunity.symbol,
            opportunity_id=opportunity.id,
            is_paper=self.is_paper,
            status=TradeStatus.EXECUTING
        )
        
        if opportunity.strategy.value == "cross_exchange":
             trade = await self._execute_cross_exchange(opportunity, trade)
        elif opportunity.strategy.value in ("ai_momentum", "momentum_rotation", "rsi_mean_reversion"):
             trade = await self._execute_directional(opportunity, trade)
        else:
             trade.status = TradeStatus.FAILED
             trade.error_message = f"Execution not implemented for {opportunity.strategy}"

        trade.completed_at = time.time()
        await self.db.save_trade(trade)
        return trade

    async def _execute_cross_exchange(self, opp: Opportunity, trade: Trade) -> Trade:
        size_usd = opp.suggested_amount_usd
        
        # Realistic fee rates (taker for both legs)
        buy_fee_rate  = get_fee_rate(opp.buy_exchange,  "spot", "taker")
        sell_fee_rate = get_fee_rate(opp.sell_exchange, "spot", "taker")

        # Simulate slippage on each leg
        buy_slip  = simulate_slippage(opp.buy_price,  size_usd)
        sell_slip = simulate_slippage(opp.sell_price, size_usd)

        # Realistic fill prices
        real_buy_price  = opp.buy_price  * buy_slip   # slip pushes buy price UP
        real_sell_price = opp.sell_price * (2.0 - sell_slip)  # slip pushes sell price DOWN

        qty = size_usd / real_buy_price

        buy_order = TradeOrder(
            exchange=opp.buy_exchange, symbol=opp.symbol,
            side=OrderSide.BUY, order_type=OrderType.LIMIT,
            price=opp.buy_price, quantity=qty
        )
        sell_order = TradeOrder(
            exchange=opp.sell_exchange, symbol=opp.symbol,
            side=OrderSide.SELL, order_type=OrderType.LIMIT,
            price=opp.sell_price, quantity=qty
        )
        trade.orders = [buy_order, sell_order]
        
        if self.is_paper:
            buy_cost  = qty * real_buy_price
            buy_fee   = buy_cost  * buy_fee_rate
            sell_rev  = qty * real_sell_price
            sell_fee  = sell_rev  * sell_fee_rate

            buy_order.filled_quantity = qty
            buy_order.filled_price    = real_buy_price
            buy_order.fee             = round(buy_fee, 6)
            buy_order.fee_currency    = "USDT"
            buy_order.status          = TradeStatus.FILLED

            sell_order.filled_quantity = qty
            sell_order.filled_price    = real_sell_price
            sell_order.fee             = round(sell_fee, 6)
            sell_order.fee_currency    = "USDT"
            sell_order.status          = TradeStatus.FILLED

            gross = sell_rev - buy_cost
            total_fees = buy_fee + sell_fee
            net = gross - total_fees

            trade.gross_profit_usd = round(gross, 6)
            trade.total_fees_usd   = round(total_fees, 6)
            trade.net_profit_usd   = round(net, 6)
            trade.net_profit_pct   = round((net / size_usd) * 100, 4)
            trade.status = TradeStatus.FILLED

            logger.info(
                f"[Paper Cross-Exchange] {opp.symbol}: gross=${gross:.4f} "
                f"fees=${total_fees:.4f} net=${net:.4f} ({trade.net_profit_pct:+.3f}%)"
            )
        else:
            try:
                buy_task = self.exchanges[opp.buy_exchange].create_order(
                    opp.symbol, 'market', 'buy', qty
                )
                sell_task = self.exchanges[opp.sell_exchange].create_order(
                    opp.symbol, 'market', 'sell', qty
                )
                results = await asyncio.gather(buy_task, sell_task, return_exceptions=True)
                
                for i, order in enumerate([buy_order, sell_order]):
                    res = results[i]
                    if isinstance(res, Exception):
                        order.status = TradeStatus.FAILED
                        trade.error_message += str(res)
                    else:
                        order.exchange_order_id = res.get('id', '')
                        fp = float(res.get('average') or res.get('price', order.price))
                        fq = float(res.get('filled', order.quantity))
                        fee_info = res.get('fee') or {}
                        order.filled_price    = fp
                        order.filled_quantity = fq
                        order.fee             = float(fee_info.get('cost', fq * fp * get_fee_rate(order.exchange)))
                        order.fee_currency    = fee_info.get('currency', 'USDT')
                        order.status          = TradeStatus.FILLED

                buy_o, sell_o = trade.orders[0], trade.orders[1]
                if buy_o.status == TradeStatus.FILLED and sell_o.status == TradeStatus.FILLED:
                    gross = (sell_o.filled_price - buy_o.filled_price) * buy_o.filled_quantity
                    total_fees = buy_o.fee + sell_o.fee
                    net = gross - total_fees
                    trade.gross_profit_usd = round(gross, 6)
                    trade.total_fees_usd   = round(total_fees, 6)
                    trade.net_profit_usd   = round(net, 6)
                    trade.net_profit_pct   = round((net / size_usd) * 100, 4)
                    trade.status = TradeStatus.FILLED
                else:
                    trade.status = TradeStatus.PARTIAL

            except Exception as e:
                logger.error(f"Live execution error: {e}")
                trade.status = TradeStatus.FAILED
                trade.error_message = str(e)
                
        return trade

    async def _execute_directional(self, opp: Opportunity, trade: Trade) -> Trade:
        size_usd = opp.suggested_amount_usd
        buy_fee_rate  = get_fee_rate(opp.buy_exchange,  "spot", "taker")
        sell_fee_rate = get_fee_rate(opp.sell_exchange, "spot", "taker")

        # Simulate entry slippage
        buy_slip       = simulate_slippage(opp.buy_price, size_usd)
        real_buy_price = opp.buy_price * buy_slip

        qty = size_usd / real_buy_price

        buy_order = TradeOrder(
            exchange=opp.buy_exchange, symbol=opp.symbol,
            side=OrderSide.BUY, order_type=OrderType.LIMIT,
            price=opp.buy_price, quantity=qty
        )
        trade.orders = [buy_order]
        
        if self.is_paper:
            # Check if this is an ENTRY or EXIT signal
            is_entry = opp.confidence > 0.0

            if is_entry:
                # ENTRY SIGNAL: Just record the open position, no instant profit
                buy_cost = qty * real_buy_price
                buy_fee  = buy_cost * buy_fee_rate
                
                buy_order.filled_quantity = qty
                buy_order.filled_price    = real_buy_price
                buy_order.fee             = round(buy_fee, 6)
                buy_order.fee_currency    = "USDT"
                buy_order.status          = TradeStatus.FILLED

                trade.gross_profit_usd = 0.0
                trade.total_fees_usd   = round(buy_fee, 6)
                trade.net_profit_usd   = 0.0
                trade.net_profit_pct   = 0.0
                trade.status = TradeStatus.PENDING # Marked as pending/open

                logger.info(f"[Paper Directional ENTRY] {opp.symbol} bought at {real_buy_price:.4f}")
            else:
                # EXIT SIGNAL: Calculate true round-trip PNL based on historical entry and current exit
                buy_cost = qty * opp.buy_price  # Original entry price
                buy_fee  = buy_cost * buy_fee_rate
                
                sell_slip       = simulate_slippage(opp.sell_price, size_usd)
                real_sell_price = opp.sell_price * (2.0 - sell_slip)
                
                sell_rev = qty * real_sell_price
                sell_fee = sell_rev * sell_fee_rate

                buy_order.filled_quantity = qty
                buy_order.filled_price    = opp.buy_price
                buy_order.fee             = round(buy_fee, 6)
                buy_order.fee_currency    = "USDT"
                buy_order.status          = TradeStatus.FILLED

                sell_order = TradeOrder(
                    exchange=opp.sell_exchange, symbol=opp.symbol,
                    side=OrderSide.SELL, order_type=OrderType.LIMIT,
                    price=opp.sell_price, quantity=qty,
                    filled_quantity=qty, filled_price=real_sell_price,
                    fee=round(sell_fee, 6), fee_currency="USDT",
                    status=TradeStatus.FILLED
                )
                trade.orders.append(sell_order)

                gross = sell_rev - buy_cost
                total_fees = buy_fee + sell_fee
                net = gross - total_fees

                trade.gross_profit_usd = round(gross, 6)
                trade.total_fees_usd   = round(total_fees, 6)
                trade.net_profit_usd   = round(net, 6)
                trade.net_profit_pct   = round((net / size_usd) * 100, 4)
                trade.status = TradeStatus.FILLED

                logger.info(
                    f"[Paper Directional EXIT] {opp.symbol}: gross=${gross:.4f} "
                    f"fees=${total_fees:.4f} net=${net:.4f} ({trade.net_profit_pct:+.3f}%)"
                )
        else:
            trade.status = TradeStatus.FAILED
            trade.error_message = "Live directional execution not yet implemented"
             
        return trade
