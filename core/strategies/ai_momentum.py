import logging
import time
from typing import List, Dict, Any
from core.strategies.base import BaseStrategy
from data.models import Opportunity, StrategyType, RegimeState

logger = logging.getLogger(__name__)

class AiMomentumStrategy(BaseStrategy):
    """AI Multi-Coin Scanner Strategy that trades directional breakouts."""
    
    def __init__(self):
        super().__init__("ai_momentum")
        # Track when we last traded a coin to prevent spamming
        self.active_cooldowns: Dict[str, float] = {}

    def scan(self, market_data: Dict[str, Any], intelligence_signals: Dict[str, Any]) -> List[Opportunity]:
        opps = []
        
        # We need the top coins passed in via intelligence signals
        top_coins = intelligence_signals.get('top_coins', [])
        
        # Monitor the top 3 coins
        top_3 = top_coins[:3]
        
        current_time = time.time()
        
        for coin_score in top_3:
            symbol = coin_score.symbol
            
            # Check if this coin is on cooldown (e.g. 5 minutes)
            if symbol in self.active_cooldowns:
                if current_time < self.active_cooldowns[symbol]:
                    continue # Still on cooldown
                else:
                    del self.active_cooldowns[symbol] # Cooldown expired
            
            # If the AI breakout probability crosses 80%, fire a directional trade!
            if coin_score.breakout_probability > 0.80:
                # Find current price from Binance order book
                binance_books = market_data.get('order_books', {}).get('binance', {})
                
                if symbol in binance_books:
                    ob = binance_books[symbol]
                    if ob.asks:
                        current_ask = ob.best_ask
                        
                        opp = Opportunity(
                            strategy=StrategyType.AI_MOMENTUM,
                            symbol=symbol,
                            exchanges=['binance'], # Single exchange directional trade
                            buy_price=current_ask,
                            sell_price=current_ask * 1.02, # Target 2% profit for exit
                            buy_exchange='binance',
                            sell_exchange='binance',
                            gross_profit_pct=2.0,
                            net_profit_pct=1.8, # Assuming 0.2% total fees
                            suggested_amount_usd=100.0,
                            regime=intelligence_signals.get('regime', RegimeState.ACTIVE),
                            confidence=coin_score.breakout_probability
                        )
                        opps.append(opp)
                        
                        # Set a 5-minute cooldown for this symbol
                        self.active_cooldowns[symbol] = current_time + 300
                        
        return opps

    def validate(self, opportunity: Opportunity) -> bool:
        return True
