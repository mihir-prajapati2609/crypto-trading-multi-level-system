"""
Strategy 4: AI Momentum Rotation ⭐⭐⭐⭐⭐

Every minute:
    Top 500 Coins → Calculate (Momentum, Volume, Liquidity, News, Funding, OI)
    → Rank → Trade Top 5

When another coin becomes stronger:
    Sell current → Buy new one

This creates constant trading activity without forcing trades on a single asset.
"""

import logging
import time
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from core.strategies.base import BaseStrategy
from data.models import Opportunity, StrategyType, RegimeState, CoinScore

logger = logging.getLogger(__name__)


@dataclass
class RotationPosition:
    """Tracks a position held by the rotation engine."""
    symbol: str
    entry_price: float
    entry_time: float
    amount_usd: float
    rank_at_entry: int
    momentum_score_at_entry: float


class MomentumRotationStrategy(BaseStrategy):
    """
    AI Momentum Rotation — continuously holds the top-N strongest coins
    and rotates out weak positions when stronger candidates emerge.
    
    Key mechanics:
      1. Every scan tick, rank all coins by multi-factor momentum_rank_score
      2. Identify the top N (default 5) coins
      3. If a held position drops out of the top N, sell it
      4. Buy any new coin that enters the top N
      5. Minimum hold time prevents excessive churn
      6. Hysteresis buffer prevents flip-flopping at rank boundaries
    """
    
    def __init__(
        self,
        top_n: int = 5,
        position_size_usd: float = 50.0,
        min_hold_seconds: int = 60,
        rotation_cooldown_seconds: int = 30,
        rank_hysteresis: int = 2,
        min_momentum_score: float = 0.35,
    ):
        super().__init__("momentum_rotation")
        self.top_n = top_n
        self.position_size_usd = position_size_usd
        self.min_hold_seconds = min_hold_seconds
        self.rotation_cooldown_seconds = rotation_cooldown_seconds
        self.rank_hysteresis = rank_hysteresis  # Coin must drop N ranks below cutoff to sell
        self.min_momentum_score = min_momentum_score
        
        # State
        self.active_positions: Dict[str, RotationPosition] = {}
        self.last_rotation_time: float = 0.0
        self.rotation_history: List[Dict[str, Any]] = []  # For dashboard
        self._previous_top_n: List[str] = []

    @property
    def held_symbols(self) -> Set[str]:
        return set(self.active_positions.keys())

    def _rank_coins_by_momentum(self, coin_scores: List[CoinScore]) -> List[CoinScore]:
        """Re-rank coins by momentum_rank_score for rotation purposes."""
        ranked = sorted(coin_scores, key=lambda c: c.momentum_rank_score, reverse=True)
        return ranked

    def scan(self, market_data: Dict[str, Any], intelligence_signals: Dict[str, Any]) -> List[Opportunity]:
        opps = []
        current_time = time.time()
        
        # Enforce rotation cooldown to prevent excessive churn
        if current_time - self.last_rotation_time < self.rotation_cooldown_seconds:
            return opps
        
        # Get all coin scores from discovery engine
        coin_scores: List[CoinScore] = intelligence_signals.get('top_coins', [])
        if not coin_scores:
            return opps
        
        # Re-rank by momentum rotation composite
        ranked = self._rank_coins_by_momentum(coin_scores)
        
        # Determine the new top-N with minimum score filter
        qualified = [c for c in ranked if c.momentum_rank_score >= self.min_momentum_score]
        new_top_n = qualified[:self.top_n]
        new_top_symbols = {c.symbol for c in new_top_n}
        
        # Build a rank lookup for hysteresis check
        rank_lookup = {c.symbol: i + 1 for i, c in enumerate(ranked)}
        
        binance_books = market_data.get('order_books', {}).get('binance', {})
        
        # --- PHASE 1: SELL positions that dropped out of top-N or hit TP/SL ---
        symbols_to_sell = []
        for symbol, pos in self.active_positions.items():
            hold_time = current_time - pos.entry_time
            if hold_time >= self.min_hold_seconds:
                # Check rank drop
                coin_rank = rank_lookup.get(symbol, 999)
                dropped_rank = symbol not in new_top_symbols and coin_rank > self.top_n + self.rank_hysteresis
                
                # Check TP / SL
                hit_tp = False
                hit_sl = False
                if symbol in binance_books:
                    current_bid = binance_books[symbol].best_bid
                    pnl_pct = ((current_bid - pos.entry_price) / pos.entry_price) * 100
                    if pnl_pct >= 0.3:   # Quick 0.3% Take Profit for frequent closes
                        hit_tp = True
                    elif pnl_pct <= -0.3: # Tight 0.3% Stop Loss
                        hit_sl = True
                
                if dropped_rank or hit_tp or hit_sl:
                    reason = 'rank_drop'
                    if hit_tp: reason = 'take_profit'
                    elif hit_sl: reason = 'stop_loss'
                    
                    symbols_to_sell.append((symbol, reason))
                    logger.info(
                        f"[ROTATION] Selling {symbol} — {reason}, "
                        f"held for {hold_time:.0f}s"
                    )
        
        # Generate SELL opportunities (close position)
        for symbol_data in symbols_to_sell:
            symbol = symbol_data[0]
            reason = symbol_data[1]
            pos = self.active_positions[symbol]
            if symbol in binance_books:
                ob = binance_books[symbol]
                if ob.bids:
                    current_bid = ob.best_bid
                    pnl_pct = ((current_bid - pos.entry_price) / pos.entry_price) * 100
                    
                    opp = Opportunity(
                        strategy=StrategyType.MOMENTUM_ROTATION,
                        symbol=symbol,
                        exchanges=['binance'],
                        buy_price=pos.entry_price,      # Original entry
                        sell_price=current_bid,           # Current exit
                        buy_exchange='binance',
                        sell_exchange='binance',
                        gross_profit_pct=pnl_pct,
                        net_profit_pct=pnl_pct - 0.2,    # Subtract est. fees
                        suggested_amount_usd=pos.amount_usd,
                        regime=intelligence_signals.get('regime', RegimeState.ACTIVE),
                        confidence=0.0,  # Rotation exit, not a signal-based trade
                    )
                    opps.append(opp)
            
            # Remove from active positions
            del self.active_positions[symbol]
            self.rotation_history.append({
                'action': 'SELL',
                'symbol': symbol,
                'time': current_time,
                'reason': reason
            })
        
        # --- PHASE 2: BUY coins that entered the top-N ---
        for coin in new_top_n:
            symbol = coin.symbol
            if symbol in self.active_positions:
                continue  # Already holding
            
            # Check we have capacity
            if len(self.active_positions) >= self.top_n:
                continue  # Full — wait for sells to free a slot
            
            if symbol in binance_books:
                ob = binance_books[symbol]
                if ob.asks:
                    current_ask = ob.best_ask
                    
                    # Create a BUY opportunity with a target based on momentum strength
                    target_pct = 1.0 + (coin.momentum_rank_score * 2.0)  # 1–3% target
                    
                    opp = Opportunity(
                        strategy=StrategyType.MOMENTUM_ROTATION,
                        symbol=symbol,
                        exchanges=['binance'],
                        buy_price=current_ask,
                        sell_price=current_ask * (1 + target_pct / 100),
                        buy_exchange='binance',
                        sell_exchange='binance',
                        gross_profit_pct=target_pct,
                        net_profit_pct=target_pct - 0.2,
                        suggested_amount_usd=self.position_size_usd,
                        regime=intelligence_signals.get('regime', RegimeState.ACTIVE),
                        confidence=coin.momentum_rank_score,
                    )
                    opps.append(opp)
                    
                    # Track the new position
                    self.active_positions[symbol] = RotationPosition(
                        symbol=symbol,
                        entry_price=current_ask,
                        entry_time=current_time,
                        amount_usd=self.position_size_usd,
                        rank_at_entry=rank_lookup.get(symbol, 0),
                        momentum_score_at_entry=coin.momentum_rank_score,
                    )
                    
                    self.rotation_history.append({
                        'action': 'BUY',
                        'symbol': symbol,
                        'time': current_time,
                        'rank': rank_lookup.get(symbol, 0),
                        'score': coin.momentum_rank_score,
                    })
                    
                    logger.info(
                        f"[ROTATION] Buying {symbol} — rank #{rank_lookup.get(symbol, '?')}, "
                        f"momentum={coin.momentum_rank_score:.3f}"
                    )
        
        if opps:
            self.last_rotation_time = current_time
        
        # Save current top N for dashboard
        self._previous_top_n = [c.symbol for c in new_top_n]
        
        return opps

    def validate(self, opportunity: Opportunity) -> bool:
        """Rotation trades are always valid if they passed scan logic."""
        return True
    
    def get_dashboard_state(self) -> Dict[str, Any]:
        """Returns state info for the dashboard."""
        return {
            'active_positions': [
                {
                    'symbol': pos.symbol,
                    'entry_price': pos.entry_price,
                    'held_seconds': time.time() - pos.entry_time,
                    'rank_at_entry': pos.rank_at_entry,
                    'momentum_score': pos.momentum_score_at_entry,
                }
                for pos in self.active_positions.values()
            ],
            'current_top_n': self._previous_top_n,
            'total_rotations': len(self.rotation_history),
            'slot_usage': f"{len(self.active_positions)}/{self.top_n}",
        }
