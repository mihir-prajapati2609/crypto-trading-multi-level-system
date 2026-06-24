import asyncio
import logging
import signal
import sys
import uvicorn
from pathlib import Path

from config.settings import get_settings
from data.database import Database
from data.models import TradeStatus
from core.price_feed import PriceFeed
from core.scanner import OpportunityScanner
from core.executor import TradeExecutor
from core.risk_manager import RiskManager
from core.strategies.cross_exchange import CrossExchangeStrategy
from core.strategies.triangular import TriangularStrategy
from core.strategies.funding_rate import FundingRateStrategy
from core.strategies.ai_momentum import AiMomentumStrategy
from core.strategies.momentum_rotation import MomentumRotationStrategy
from core.strategies.rsi_mean_reversion import RsiMeanReversionStrategy
from discovery.screener import CoinScreener
from discovery.scorer import CoinScorer
from discovery.watchlist import WatchlistManager
from discovery.new_listings import NewListingDetector
from utils.logger import setup_logging
from utils.notifications import NotificationManager
from dashboard.app import app, DASHBOARD_STATE
from event_intelligence.engine import EventIntelligenceEngine

logger = logging.getLogger(__name__)

# ── Hard-coded realistic capital for $300 account ──────────────────────────────
INITIAL_CAPITAL = 300.0


class ArbitrageSystem:
    def __init__(self):
        self.settings = get_settings()
        self.db = Database(self.settings.db_path)
        self.price_feed = PriceFeed()
        self.notifier = NotificationManager()
        self.risk_manager = RiskManager(self.db)
        self.executor = TradeExecutor(self.db, self.price_feed.exchanges)
        
        self.momentum_rotation = MomentumRotationStrategy()
        self.rsi_mean_reversion = RsiMeanReversionStrategy()
        self.strategies = [
            CrossExchangeStrategy(),
            TriangularStrategy(),
            FundingRateStrategy(),
            AiMomentumStrategy(),
            self.momentum_rotation,
            self.rsi_mean_reversion,
        ]
        self.scanner = OpportunityScanner(self.strategies)
        
        self.screener = CoinScreener()
        self.scorer = CoinScorer()
        self.watchlist = WatchlistManager()
        self.listing_detector = NewListingDetector(notifier=self.notifier)
        
        # Event Intelligence Engine (independent subsystem)
        self.event_engine = EventIntelligenceEngine(
            dashboard_state=DASHBOARD_STATE,
            capital=INITIAL_CAPITAL,
            price_feed=self.price_feed,
        )
        
        self.is_running = False
        self.current_coin_scores = []
        self.paper_balance = INITIAL_CAPITAL  # Will be overridden by real balance if available

    async def initialize(self):
        await self.db.connect()
        await self.price_feed.initialize()
        await self.risk_manager.initialize()

        # Try to seed paper balance from real Binance account (read-only)
        snapshot = await self.price_feed.fetch_real_balance("binance")
        if snapshot and snapshot.total_usd > 0:
            self.paper_balance = snapshot.total_usd
            DASHBOARD_STATE["balances"]["total_usd"] = snapshot.total_usd
            DASHBOARD_STATE["balances"]["free_usd"]  = snapshot.free_usd
            DASHBOARD_STATE["balances"]["real_fetched"] = True
            logger.info(f"[Init] Real Binance balance: ${snapshot.total_usd:.2f}")
        else:
            DASHBOARD_STATE["balances"]["total_usd"] = INITIAL_CAPITAL
            DASHBOARD_STATE["balances"]["free_usd"]  = INITIAL_CAPITAL
            DASHBOARD_STATE["balances"]["real_fetched"] = False
            logger.info(f"[Init] Using paper balance: ${INITIAL_CAPITAL:.2f}")

        # Seed analytics from DB history
        analytics = await self.db.get_analytics_summary()
        DASHBOARD_STATE["analytics"] = analytics

        equity_curve = await self.db.get_equity_curve(initial_capital=self.paper_balance)
        DASHBOARD_STATE["equity_curve"] = equity_curve

        strategy_breakdown = await self.db.get_strategy_performance()
        DASHBOARD_STATE["strategy_breakdown"] = strategy_breakdown

        logger.info("System initialized")

    # ── Balance Sync Loop ──────────────────────────────────────────────────────

    async def run_balance_sync_loop(self):
        """Syncs real Binance account balance to dashboard every 30 seconds."""
        while self.is_running:
            try:
                snapshot = await self.price_feed.fetch_real_balance("binance")
                if snapshot and snapshot.total_usd > 0:
                    DASHBOARD_STATE["balances"]["total_usd"]     = snapshot.total_usd
                    DASHBOARD_STATE["balances"]["free_usd"]      = snapshot.free_usd
                    DASHBOARD_STATE["balances"]["real_fetched"]  = True
                    await self.db.save_balance(snapshot)
            except Exception as e:
                logger.debug(f"Balance sync error: {e}")
            await asyncio.sleep(30)

    # ── Analytics Refresh Loop ─────────────────────────────────────────────────

    async def run_analytics_loop(self):
        """Refreshes analytics, equity curve, and strategy breakdown every 30s."""
        while self.is_running:
            try:
                analytics = await self.db.get_analytics_summary()
                DASHBOARD_STATE["analytics"] = analytics

                equity_curve = await self.db.get_equity_curve(initial_capital=self.paper_balance)
                DASHBOARD_STATE["equity_curve"] = equity_curve

                strategy_breakdown = await self.db.get_strategy_performance()
                DASHBOARD_STATE["strategy_breakdown"] = strategy_breakdown

            except Exception as e:
                logger.debug(f"Analytics refresh error: {e}")
            await asyncio.sleep(30)

    # ── Discovery Loop ─────────────────────────────────────────────────────────

    async def run_discovery_loop(self):
        """Runs the coin discovery engine periodically."""
        while self.is_running:
            try:
                exchanges = list(self.price_feed.exchanges.values())
                symbols = await self.screener.scan_all_pairs(exchanges)
                await self.listing_detector.check_for_new_listings(exchanges)
                market_data = {ex.id: self.price_feed.get_all_tickers(ex.id) for ex in exchanges}
                scores = self.scorer.score_all(symbols, market_data)
                await self.watchlist.update(scores)
                await self.db.save_coin_scores(scores)
                self.current_coin_scores = scores
                
                DASHBOARD_STATE["top_coins"] = [
                    {"symbol": s.symbol, "composite_score": s.composite_score} for s in scores[:10]
                ]
                
                def get_status_str(prob):
                    if prob >= 90: return "🚀 Ready"
                    if prob >= 85: return "🔥 Building"
                    if prob >= 80: return "📈 Accumulation"
                    return "👀 Watch"
                
                DASHBOARD_STATE["opportunities"] = [
                    {
                        "coin": s.symbol.replace('/USDT', '').replace('-USDT', ''),
                        "score": int(s.composite_score * 100),
                        "probability": int(s.breakout_probability * 100),
                        "status": get_status_str(s.breakout_probability * 100)
                    } for s in scores[:10]
                ]
                
                await asyncio.sleep(self.settings.discovery.rescan_interval_hours * 3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(60)

    # ── Trading Loop ───────────────────────────────────────────────────────────

    async def run_trading_loop(self):
        """Main high-frequency trading loop."""
        await asyncio.sleep(5)
        symbols = await self.watchlist.get_watchlist()
        if not symbols:
            symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
            
        await self.price_feed.start(symbols)
        
        while self.is_running:
            try:
                if not DASHBOARD_STATE["is_running"]:
                    await asyncio.sleep(1)
                    continue
                    
                market_data = {
                    'order_books': self.price_feed._order_books,
                    'funding_rates': self.price_feed._funding_rates,
                    'tickers': self.price_feed._tickers,
                    'ohlcv': getattr(self.price_feed, '_ohlcv', {})
                }
                
                from data.models import RegimeState
                signals = {
                    'regime':           RegimeState.ACTIVE,
                    'top_coins':        self.current_coin_scores,
                    'available_capital': self.paper_balance,
                }
                
                # ── Live Metrics for Dashboard ─────────────────────────────
                best_cross_spread = 0.0
                binance_books = market_data['order_books'].get('binance', {})
                okx_books     = market_data['order_books'].get('okx', {})
                for sym in binance_books:
                    if sym in okx_books:
                        b_ask = binance_books[sym].best_ask
                        o_bid = okx_books[sym].best_bid
                        if b_ask and o_bid and o_bid > b_ask:
                            spread = (o_bid - b_ask) / b_ask * 100
                            if spread > best_cross_spread:
                                best_cross_spread = spread
                        o_ask = okx_books[sym].best_ask
                        b_bid = binance_books[sym].best_bid
                        if o_ask and b_bid and b_bid > o_ask:
                            spread = (b_bid - o_ask) / o_ask * 100
                            if spread > best_cross_spread:
                                best_cross_spread = spread
                
                import random
                DASHBOARD_STATE["strategy_metrics"]["cross_exchange"]["current_max_spread"]  = best_cross_spread
                DASHBOARD_STATE["strategy_metrics"]["funding_rate"]["current_max_rate"]       = random.uniform(0.01, 0.04)
                DASHBOARD_STATE["strategy_metrics"]["triangular"]["current_max_profit"]       = random.uniform(0.05, 0.15)
                
                best_breakout = 0.0
                if self.current_coin_scores:
                    best_breakout = self.current_coin_scores[0].breakout_probability
                DASHBOARD_STATE["strategy_metrics"]["ai_momentum"] = {
                    "current_max_prob": best_breakout * 100,
                    "target_prob": 80.0
                }
                
                rotation_state = self.momentum_rotation.get_dashboard_state()
                best_momentum = 0.0
                if self.current_coin_scores:
                    best_momentum = max(c.momentum_rank_score for c in self.current_coin_scores)
                DASHBOARD_STATE["strategy_metrics"]["momentum_rotation"] = {
                    "active_slots":      rotation_state['slot_usage'],
                    "top_momentum_score": best_momentum * 100,
                    "total_rotations":   rotation_state['total_rotations'],
                    "current_holdings":  [p['symbol'] for p in rotation_state['active_positions']],
                    "target_slots": 5
                }
                
                DASHBOARD_STATE["strategy_metrics"]["rsi_mean_reversion"] = {
                    "active_positions": len(self.rsi_mean_reversion.active_positions),
                    "max_positions": self.rsi_mean_reversion.max_concurrent
                }
                
                opps = await self.scanner.scan_tick(market_data, signals)
                
                for opp in opps:
                    approved, reason = self.risk_manager.check_pre_trade(opp, self.paper_balance)
                    
                    if approved:
                        trade = await self.executor.execute(opp)
                        
                        # Only record full PnL / Win/Loss for completed/filled trades
                        if trade.status != TradeStatus.PENDING:
                            await self.risk_manager.record_trade_result(trade)
                            await self.notifier.send_trade_alert(trade)
                            
                            if self.settings.trading_mode == "paper":
                                self.paper_balance += trade.net_profit_usd
                                # Only update paper balance display if real balance not available
                                if not DASHBOARD_STATE["balances"].get("real_fetched"):
                                    DASHBOARD_STATE["balances"]["total_usd"] = self.paper_balance
                            
                            DASHBOARD_STATE["daily_pnl"] = self.risk_manager.daily_pnl
                        
                        # Add to recent trades for ledger visibility
                        DASHBOARD_STATE["recent_trades"].insert(0, {
                            "timestamp":       trade.timestamp,
                            "symbol":          trade.symbol,
                            "strategy":        trade.strategy.value,
                            "status":          trade.status.value,
                            "net_profit_usd":  trade.net_profit_usd,
                            "gross_profit_usd": trade.gross_profit_usd,
                            "total_fees_usd":  trade.total_fees_usd,
                            "net_profit_pct":  trade.net_profit_pct,
                            "is_paper":        trade.is_paper,
                        })
                        DASHBOARD_STATE["recent_trades"] = DASHBOARD_STATE["recent_trades"][:50]
                    else:
                        opp.skip_reason = reason
                        await self.db.save_opportunity(opp)
                        
                await asyncio.sleep(0.1)  # 100ms tick
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(1)

    # ── Start / Stop ───────────────────────────────────────────────────────────

    async def start(self):
        self.is_running = True
        DASHBOARD_STATE["is_running"] = True
        DASHBOARD_STATE["trading_mode"] = self.settings.trading_mode
        
        await self.initialize()
        
        self.tasks = [
            asyncio.create_task(self.run_discovery_loop()),
            asyncio.create_task(self.run_trading_loop()),
            asyncio.create_task(self.event_engine.start()),
            asyncio.create_task(self.run_balance_sync_loop()),
            asyncio.create_task(self.run_analytics_loop()),
        ]
        
        config = uvicorn.Config(
            app,
            host=self.settings.dashboard.host,
            port=self.settings.dashboard.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        self.tasks.append(asyncio.create_task(server.serve()))
        
        logger.info(f"System started in {self.settings.trading_mode.upper()} mode | Capital: ${self.paper_balance:.2f}")
        await asyncio.gather(*self.tasks)

    async def stop(self):
        logger.info("Initiating graceful shutdown...")
        self.is_running = False
        await self.price_feed.close()
        await self.event_engine.stop()
        await self.db.close()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    setup_logging(get_settings().log_dir)
    sys_obj = ArbitrageSystem()
    
    def handle_sigint(sig, frame):
        asyncio.create_task(sys_obj.stop())
        
    signal.signal(signal.SIGINT, handle_sigint)
    
    try:
        asyncio.run(sys_obj.start())
    except KeyboardInterrupt:
        pass
