import logging
import math
import random
from typing import List, Dict, Any
from data.models import CoinScore

logger = logging.getLogger(__name__)

class CoinScorer:
    """Scores coins based on various metrics including multi-factor momentum ranking."""
    
    # Weights for momentum rotation composite score
    ROTATION_WEIGHTS = {
        'momentum':   0.30,  # Price momentum (trend strength)
        'volume':     0.20,  # Volume increase / surge detection
        'liquidity':  0.15,  # Order book depth & spread tightness
        'funding':    0.15,  # Funding rate signal (contrarian or trend)
        'oi':         0.10,  # Open interest change (conviction)
        'news':       0.10,  # News / social sentiment proxy
    }
    
    def score_all(self, symbols: List[str], exchange_data: Dict[str, Dict[str, Any]]) -> List[CoinScore]:
        """
        Scores a list of symbols and returns them ranked.
        """
        scores = []
        for sym in symbols:
            try:
                change_pct = 0.0
                vol = 0.0
                if 'binance' in exchange_data and sym in exchange_data['binance']:
                    ticker = exchange_data['binance'][sym]
                    change_pct = getattr(ticker, 'change_pct', 0.0)
                    if change_pct is None: change_pct = 0.0
                    vol = getattr(ticker, 'base_volume', 0.0)
                    if vol is None: vol = 0.0
                
                # === Core Scoring (existing) ===
                # Trend strength based on actual % change
                trend_str = min(max(abs(change_pct) / 15.0, 0.1), 1.0)
                # Volume increase based on actual base volume
                vol_inc = min(max(vol / 500000.0, 0.1), 1.0)
                
                # Realistic volatility and liquidity
                liquidity = min(max(vol / 100000.0, 0.1), 1.0)
                volatility = min(max(abs(change_pct) / 10.0, 0.1), 1.0)
                
                # Pure data-driven breakout probability
                breakout_prob = (trend_str * 0.5) + (vol_inc * 0.3) + (volatility * 0.2)
                # Strict cap, NO artificial noise boost!
                breakout_prob = min(max(breakout_prob, 0.0), 1.0)
                
                risk = volatility * 0.7 + (1.0 - liquidity) * 0.3
                
                # === Extended Multi-Factor Scoring (for rotation strategy) ===
                
                # Momentum score: directional strength with recency weighting
                # Positive change => bullish momentum, use sigmoid-like mapping
                momentum_raw = change_pct / 10.0  # Normalize
                momentum_score = 1.0 / (1.0 + math.exp(-momentum_raw * 3.0))  # Sigmoid
                momentum_score = min(max(momentum_score, 0.0), 1.0)
                
                # Funding rate score: Simulated from volume/volatility proxy
                # In live trading, this comes from exchange API. Here we derive a realistic proxy.
                # High volume + positive change => likely positive funding (longs paying shorts)
                funding_signal = 0.5 + (change_pct / 20.0) + (vol / 2_000_000.0) * 0.1
                funding_rate_score = min(max(funding_signal, 0.0), 1.0)
                
                # Open Interest score: Proxy based on volume surge relative to baseline
                # Rapid volume increase signals rising OI
                oi_proxy = min(max(vol / 300_000.0, 0.0), 1.0) * (1.0 + abs(change_pct) / 20.0)
                open_interest_score = min(max(oi_proxy, 0.0), 1.0)
                
                # News sentiment score: Simulated — in production, integrate a news/social API
                # We use a noise-dampened proxy based on price action + volume
                # Strong moves on high volume often have news catalysts
                news_proxy = (abs(change_pct) / 15.0) * 0.6 + (vol / 500_000.0) * 0.4
                # Add slight random jitter to simulate sentiment variance
                news_proxy += random.gauss(0, 0.05)
                news_sentiment_score = min(max(news_proxy, 0.0), 1.0)
                
                # === Momentum Rotation Composite ===
                momentum_rank_score = (
                    self.ROTATION_WEIGHTS['momentum'] * momentum_score +
                    self.ROTATION_WEIGHTS['volume']   * vol_inc +
                    self.ROTATION_WEIGHTS['liquidity'] * liquidity +
                    self.ROTATION_WEIGHTS['funding']   * funding_rate_score +
                    self.ROTATION_WEIGHTS['oi']        * open_interest_score +
                    self.ROTATION_WEIGHTS['news']      * news_sentiment_score
                )
                momentum_rank_score = min(max(momentum_rank_score, 0.0), 1.0)
                
                score = CoinScore(
                    symbol=sym,
                    base_currency=sym.split('/')[0],
                    exchanges=list(exchange_data.keys()),
                    trend_strength_score=trend_str,
                    volume_increase_score=vol_inc,
                    liquidity_score=liquidity,
                    volatility_score=volatility,
                    breakout_probability=breakout_prob,
                    risk_score=risk,
                    funding_rate_score=funding_rate_score,
                    open_interest_score=open_interest_score,
                    news_sentiment_score=news_sentiment_score,
                    momentum_rank_score=momentum_rank_score,
                )
                
                # Composite score is primarily driven by breakout probability
                score.composite_score = breakout_prob
                                         
                scores.append(score)
            except Exception as e:
                logger.error(f"Error scoring {sym}: {e}")
                
        # Sort by composite score descending
        scores.sort(key=lambda x: x.composite_score, reverse=True)
        
        # Assign ranks
        for i, score in enumerate(scores):
            score.rank = i + 1
            
        return scores
