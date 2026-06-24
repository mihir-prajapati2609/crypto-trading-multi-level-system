"""
Event Intelligence — Main Engine Orchestrator

The central orchestrator that ties everything together:
- Launches collector loops
- Processes events through the NLP pipeline
- Runs multi-agent scoring via the decision engine
- Manages trade execution and position monitoring
- Runs feedback loops for self-improvement
- Publishes state to the dashboard

Operates completely independently of the arbitrage system.
"""

import asyncio
import logging
import time
from typing import Optional

from event_intelligence.config import get_event_config, EventIntelligenceConfig
from event_intelligence.database import EventDatabase
from event_intelligence.models import (
    NewsEvent, EventScore, EventEngineState, TradeAction, EventCategory,
)
from event_intelligence.pipeline.event_processor import EventProcessor
from event_intelligence.decision.decision_engine import DecisionEngine
from event_intelligence.execution.risk_manager import EventRiskManager
from event_intelligence.execution.position_manager import PositionManager
from event_intelligence.execution.trade_executor import EventTradeExecutor
from event_intelligence.feedback.feedback_loop import FeedbackLoop
from event_intelligence.feedback.model_trainer import ModelTrainer

# Collectors
from event_intelligence.collectors.rss_collector import RSSCollector
from event_intelligence.collectors.binance_announcements import BinanceAnnouncementCollector
from event_intelligence.collectors.coinbase_blog import CoinbaseBlogCollector
from event_intelligence.collectors.coingecko_collector import CoinGeckoCollector
from event_intelligence.collectors.coinmarketcap_collector import CoinMarketCapCollector
from event_intelligence.collectors.github_collector import GitHubCollector
from event_intelligence.collectors.fear_greed_collector import FearGreedCollector
from event_intelligence.collectors.google_trends_collector import GoogleTrendsCollector
from event_intelligence.collectors.onchain_whale_collector import OnChainWhaleCollector

logger = logging.getLogger(__name__)


class EventIntelligenceEngine:
    """
    Main orchestrator for the AI Event Intelligence system.
    
    Operates as a fully independent async subsystem.
    Only integration point: publishes state to a shared dict for dashboard display.
    """

    def __init__(self, dashboard_state: Optional[dict] = None, capital: float = 300.0, price_feed = None):
        self.config = get_event_config()
        self.dashboard_state = dashboard_state  # Shared with main dashboard
        self.capital = capital
        self.price_feed = price_feed

        # Database
        self.db = EventDatabase(self.config.db_path)

        # Pipeline
        self.event_processor = EventProcessor(self.db)

        # Decision engine
        self.decision_engine = DecisionEngine(self.db, self.config)

        # Execution
        self.risk_manager = EventRiskManager(self.config.risk, capital=capital)
        self.position_manager = PositionManager(self.config.risk)
        self.executor = EventTradeExecutor(
            self.db, self.risk_manager, self.position_manager,
            is_paper=True,
        )

        # Feedback
        self.feedback_loop = FeedbackLoop(self.db, self.config)
        self.model_trainer = ModelTrainer(
            self.db,
            self.decision_engine.impact_model,
            self.decision_engine.historical_analyzer,
        )

        # Collectors
        self.collectors = []
        self._collector_tasks: list[asyncio.Task] = []
        self._monitor_task: Optional[asyncio.Task] = None
        self._dashboard_task: Optional[asyncio.Task] = None

        # State
        self.is_running = False
        self.state = EventEngineState()
        self._recent_whale_events: list[dict] = []

    def _init_collectors(self):
        """Initialize all enabled collectors."""
        cfg = self.config.collectors

        if cfg.rss_enabled:
            self.collectors.append(
                RSSCollector(cfg.rss_feeds, poll_interval=cfg.rss_interval)
            )
        if cfg.binance_announcements_enabled:
            self.collectors.append(
                BinanceAnnouncementCollector(poll_interval=cfg.binance_announcements_interval)
            )
        if cfg.coinbase_blog_enabled:
            self.collectors.append(
                CoinbaseBlogCollector(poll_interval=cfg.coinbase_blog_interval)
            )
        if cfg.coingecko_enabled:
            self.collectors.append(
                CoinGeckoCollector(
                    api_key=self.config.coingecko_api_key,
                    poll_interval=cfg.coingecko_interval,
                )
            )
        if cfg.coinmarketcap_enabled:
            self.collectors.append(
                CoinMarketCapCollector(poll_interval=cfg.coinmarketcap_interval)
            )
        if cfg.github_enabled:
            self.collectors.append(
                GitHubCollector(
                    repos=cfg.github_repos,
                    token=self.config.github_token,
                    poll_interval=cfg.github_interval,
                )
            )
        if cfg.fear_greed_enabled:
            self.collectors.append(
                FearGreedCollector(poll_interval=cfg.fear_greed_interval)
            )
        if cfg.google_trends_enabled:
            self.collectors.append(
                GoogleTrendsCollector(poll_interval=cfg.google_trends_interval)
            )
        if cfg.onchain_whale_enabled:
            self.collectors.append(
                OnChainWhaleCollector(
                    api_key=self.config.etherscan_api_key,
                    wallets=cfg.whale_wallets,
                    poll_interval=cfg.onchain_whale_interval,
                )
            )

        logger.info(f"Initialized {len(self.collectors)} event collectors")

    async def _on_events_collected(self, events: list[NewsEvent]):
        """Callback when collectors deliver new events."""
        # Process through NLP pipeline
        processed = await self.event_processor.process_events(events)
        if not processed:
            return

        # Track whale events for context
        for event in processed:
            if event.category == EventCategory.WHALE_MOVEMENT:
                self._recent_whale_events.append({
                    "coin": event.affected_coins[0] if event.affected_coins else "ETH",
                    "direction": "bullish" if event.sentiment_score > 55 else "bearish",
                    "timestamp": event.timestamp,
                })
                # Keep last 20
                self._recent_whale_events = self._recent_whale_events[-20:]

            # Update fear & greed in context
            if "fear_greed" in event.source:
                fng_value = event.raw_data.get("value", 50)
                self.decision_engine.update_market_context({
                    "fear_greed_value": fng_value,
                })
                self.state.fear_greed_index = fng_value
                self.state.fear_greed_label = event.raw_data.get("label", "Neutral")

        tickers_context = {}
        if self.price_feed:
            binance_tickers = self.price_feed._tickers.get("binance", {})
            for symbol, t in binance_tickers.items():
                coin = symbol.split("/")[0]
                tickers_context[coin] = {
                    "quote_volume": t.quote_volume,
                    "change_pct": t.change_pct,
                    "last_price": t.last_price,
                }

        # Update market context with whale and ticker data
        self.decision_engine.update_market_context({
            "recent_whale_events": self._recent_whale_events,
            "open_trades": len(self.risk_manager.open_trades),
            "tickers": tickers_context,
        })

        # Score events through decision engine
        scores = await self.decision_engine.score_events(processed)

        # Update state
        self.state.total_events_processed += len(processed)
        self.state.last_event_time = time.time()

        # Execute trades if in trade mode
        if self.config.mode == "trade":
            await self._execute_signals(scores)

    async def _execute_signals(self, scores: list[EventScore]):
        """Execute trade signals from scored events."""
        for score in scores:
            if score.trade_action in (TradeAction.SKIP, TradeAction.HOLD):
                continue

            # Risk check
            allowed, reason = self.risk_manager.check_trade_allowed(score)
            if not allowed:
                logger.info(f"Trade blocked for {score.coin}: {reason}")
                continue

            # Get current price (simulated for paper trading)
            current_price = await self._get_current_price(score.coin)
            if current_price is None:
                continue

            # Create and execute signal
            signal = self.risk_manager.create_signal(score, current_price)
            trade = await self.executor.execute_signal(signal)

            if trade:
                self.state.open_trades = len(self.risk_manager.open_trades)
                self.state.total_trades += 1

    async def _get_current_price(self, coin: str) -> Optional[float]:
        """Get current price for a coin. Uses PriceFeed if available, with CoinGecko as fallback."""
        if self.price_feed:
            binance_tickers = self.price_feed._tickers.get("binance", {})
            symbol = f"{coin.upper()}/USDT"
            if symbol in binance_tickers:
                return binance_tickers[symbol].last_price
        try:
            import aiohttp
            symbol = coin.lower()
            # Simple price lookup from CoinGecko
            coin_id_map = {
                "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
                "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
                "DOGE": "dogecoin", "DOT": "polkadot", "AVAX": "avalanche-2",
                "LINK": "chainlink", "MATIC": "matic-network", "PEPE": "pepe",
                "SHIB": "shiba-inu", "ARB": "arbitrum", "OP": "optimism",
            }
            coin_id = coin_id_map.get(coin.upper(), coin.lower())

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = data.get(coin_id, {}).get("usd")
                        return price
        except Exception as e:
            logger.debug(f"Error getting price for {coin}: {e}")

        return None

    async def _position_monitor_loop(self):
        """Periodically check open positions for exit conditions."""
        while self.is_running:
            try:
                if self.risk_manager.open_trades:
                    async def price_getter(symbol: str) -> Optional[float]:
                        coin = symbol.split("/")[0] if "/" in symbol else symbol
                        return await self._get_current_price(coin)

                    closed_trades = await self.executor.check_and_close_positions(
                        price_getter
                    )

                    for trade in closed_trades:
                        # Process feedback
                        await self.feedback_loop.process_closed_trade(trade)
                        self.state.open_trades = len(self.risk_manager.open_trades)

                    # Check if model needs retraining
                    if self.feedback_loop.needs_retrain:
                        logger.info("Triggering model retrain from feedback loop...")
                        await self.model_trainer.retrain_impact_model()
                        await self.model_trainer.calibrate_agent_weights(
                            self.decision_engine.agents
                        )
                        self.feedback_loop.reset_retrain_counter()

                await asyncio.sleep(10)  # Check every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Position monitor error: {e}")
                await asyncio.sleep(30)

    async def _dashboard_update_loop(self):
        """Periodically update dashboard state."""
        while self.is_running:
            try:
                await self._update_dashboard_state()
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Dashboard update error: {e}")
                await asyncio.sleep(5)

    async def _update_dashboard_state(self):
        """Update the shared dashboard state dict."""
        if self.dashboard_state is None:
            return

        # Gather stats
        today_pnl = await self.db.get_event_today_pnl()
        total_pnl = await self.db.get_event_total_pnl()
        recent_events = await self.db.get_recent_events(limit=20)
        recent_scores = await self.db.get_recent_scores(limit=10)
        recent_trades = await self.db.get_recent_trades(limit=20)
        agent_perfs = await self.db.get_all_agent_performance()
        source_rels = await self.db.get_all_source_reliabilities()

        # Calculate win rate
        total_closed = today_pnl.get("trade_count", 0)
        wins = today_pnl.get("win_count", 0)
        win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

        self.state.is_running = self.is_running
        self.state.mode = self.config.mode
        self.state.events_last_hour = sum(
            1 for e in recent_events
            if e.get("timestamp", 0) > time.time() - 3600
        )
        self.state.active_signals = len(recent_scores)
        self.state.event_pnl_today = today_pnl.get("net_pnl", 0)
        self.state.event_pnl_total = total_pnl
        self.state.win_rate = win_rate
        self.state.sources_active = len(self.collectors)
        self.state.recent_events = recent_events[:10]
        self.state.recent_scores = recent_scores
        self.state.recent_trades = recent_trades[:10]
        self.state.agent_performance = agent_perfs

        # Publish to shared dashboard state
        self.dashboard_state["event_intelligence"] = {
            "is_running": self.state.is_running,
            "mode": self.state.mode,
            "total_events": self.state.total_events_processed,
            "events_last_hour": self.state.events_last_hour,
            "open_trades": self.state.open_trades,
            "total_trades": self.state.total_trades,
            "pnl_today": round(self.state.event_pnl_today, 4),
            "pnl_total": round(self.state.event_pnl_total, 4),
            "win_rate": round(self.state.win_rate, 1),
            "sources_active": self.state.sources_active,
            "sources_total": self.state.sources_total,
            "fear_greed_index": self.state.fear_greed_index,
            "fear_greed_label": self.state.fear_greed_label,
            "recent_events": self.state.recent_events,
            "recent_scores": self.state.recent_scores,
            "recent_trades": self.state.recent_trades,
            "agent_performance": self.state.agent_performance,
            "risk_status": self.risk_manager.status_summary,
            "source_reliabilities": source_rels,
        }

    async def start(self):
        """Start the Event Intelligence Engine."""
        if not self.config.enabled:
            logger.info("Event Intelligence Engine is disabled")
            return

        logger.info("=" * 60)
        logger.info("🧠 Starting AI Event Intelligence Engine")
        logger.info(f"   Mode: {self.config.mode.upper()}")
        logger.info(f"   Min Confidence: {self.config.scoring.min_confidence_to_trade}%")
        logger.info(f"   Max Open Trades: {self.config.risk.max_open_trades}")
        logger.info("=" * 60)

        self.is_running = True

        # Initialize DB
        await self.db.connect()

        # Initialize collectors
        self._init_collectors()

        # deduplicate callback since we score in _on_events_collected
        # self.event_processor.set_score_callback(
        #     self.decision_engine.score_events
        # )

        # Launch collector loops
        for collector in self.collectors:
            task = asyncio.create_task(
                collector.run_loop(self._on_events_collected)
            )
            self._collector_tasks.append(task)

        # Launch position monitor
        if self.config.mode == "trade":
            self._monitor_task = asyncio.create_task(
                self._position_monitor_loop()
            )

        # Launch dashboard updater
        self._dashboard_task = asyncio.create_task(
            self._dashboard_update_loop()
        )

        # Build initial historical profiles
        await self.decision_engine.historical_analyzer.rebuild_profiles()

        logger.info(
            f"🚀 Event Intelligence Engine started with "
            f"{len(self.collectors)} collectors"
        )

    async def stop(self):
        """Stop the Event Intelligence Engine."""
        logger.info("Stopping Event Intelligence Engine...")
        self.is_running = False

        # Stop collectors
        for collector in self.collectors:
            collector.stop()
            if hasattr(collector, 'close'):
                try:
                    await collector.close()
                except Exception:
                    pass

        # Cancel tasks
        for task in self._collector_tasks:
            if not task.done():
                task.cancel()

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

        if self._dashboard_task and not self._dashboard_task.done():
            self._dashboard_task.cancel()

        # Close DB
        await self.db.close()

        logger.info("Event Intelligence Engine stopped")
