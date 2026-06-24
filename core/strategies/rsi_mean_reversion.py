"""
Strategy 5: RSI Mean-Reversion with Volume Filter

A high-probability, low-risk scalping/swing strategy using RSI extremes,
Bollinger Band touches, and volume confirmation.
Designed for BTC/ETH/SOL on 15m–1h timeframe.
"""

import logging
import time
from typing import List, Dict, Any, Optional
import pandas as pd
import pandas_ta as ta

from core.strategies.base import BaseStrategy
from data.models import Opportunity, StrategyType, RegimeState
from config.settings import get_settings

logger = logging.getLogger(__name__)


class RsiPosition:
    """Tracks a position held by the RSI strategy."""
    def __init__(self, symbol: str, entry_price: float, side: str, amount_usd: float):
        self.symbol = symbol
        self.entry_price = entry_price
        self.side = side  # "LONG" or "SHORT"
        self.amount_usd = amount_usd
        self.entry_time = time.time()
        self.candles_held = 0


class RsiMeanReversionStrategy(BaseStrategy):
    """
    Mean reversion strategy looking for RSI extremes,
    confirmed by Bollinger Bands and volume spikes.
    """

    def __init__(self):
        super().__init__("rsi_mean_reversion")
        self.settings = get_settings().trading
        
        self.max_concurrent = self.settings.rsi_max_concurrent
        self.daily_limit = self.settings.rsi_daily_trade_limit
        
        self.active_positions: Dict[str, RsiPosition] = {}
        self.daily_trades_taken = 0
        self.last_reset_day = time.gmtime().tm_mday

    def _reset_daily_limit_if_needed(self):
        current_day = time.gmtime().tm_mday
        if current_day != self.last_reset_day:
            self.daily_trades_taken = 0
            self.last_reset_day = current_day

    def scan(self, market_data: Dict[str, Any], intelligence_signals: Dict[str, Any]) -> List[Opportunity]:
        opps = []
        
        self._reset_daily_limit_if_needed()
        
        # We need OHLCV data from market_data
        ohlcv_data = market_data.get('ohlcv', {}).get('binance', {})
        if not ohlcv_data:
            return opps
            
        target_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        
        for symbol in target_symbols:
            if symbol not in ohlcv_data:
                continue
                
            data_15m = ohlcv_data[symbol].get('15m')
            data_4h = ohlcv_data[symbol].get('4h')
            
            if not data_15m or not data_4h or len(data_15m) < 30 or len(data_4h) < 20:
                continue
                
            df_15m = pd.DataFrame(data_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_4h = pd.DataFrame(data_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # --- Technical Indicators ---
            # 15m Indicators
            df_15m['rsi'] = ta.rsi(df_15m['close'], length=14)
            bbands = ta.bbands(df_15m['close'], length=20, std=2)
            if bbands is not None:
                df_15m = pd.concat([df_15m, bbands], axis=1)
                
            df_15m['vol_avg'] = ta.sma(df_15m['volume'], length=20)
            df_15m['atr'] = ta.atr(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
            
            adx = ta.adx(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
            if adx is not None:
                df_15m = pd.concat([df_15m, adx], axis=1)
                
            # 4h Indicator for Trend Filter
            df_4h['rsi'] = ta.rsi(df_4h['close'], length=14)
            
            if len(df_15m.dropna()) < 5:
                continue
                
            # Get the last closed candle (index -2 if live polling, or -1 if completed)
            # Assuming ccxt returns up to current incomplete candle
            latest_closed = df_15m.iloc[-2]
            prev_closed = df_15m.iloc[-3]
            current_4h = df_4h.iloc[-1]
            
            # --- Check Exit Logic for Active Positions ---
            if symbol in self.active_positions:
                pos = self.active_positions[symbol]
                
                # Check Time Stop
                # In a real system, we'd count actual candle closes via timestamps.
                # For simplicity, if this scan is hit 15 mins later, we increment. 
                # Better: check if latest_closed.timestamp > pos.last_checked_timestamp
                # For now, we will evaluate exits on price/RSI.
                
                hit_exit = False
                reason = ""
                
                # Exits based on latest closed candle
                # 1. RSI crosses 50
                # 2. Price hits BB midline
                # 3. Stop loss (1.5x ATR below entry)
                bb_mid = latest_closed.get('BBM_20_2.0', 0)
                
                if pos.side == "LONG":
                    # TP
                    if latest_closed['rsi'] >= 50 or latest_closed['close'] >= bb_mid:
                        hit_exit = True
                        reason = "take_profit"
                    # SL (1.5x ATR)
                    elif latest_closed['close'] <= pos.entry_price - (1.5 * latest_closed['atr']):
                        hit_exit = True
                        reason = "stop_loss"
                else:
                    # TP
                    if latest_closed['rsi'] <= 50 or latest_closed['close'] <= bb_mid:
                        hit_exit = True
                        reason = "take_profit"
                    # SL
                    elif latest_closed['close'] >= pos.entry_price + (1.5 * latest_closed['atr']):
                        hit_exit = True
                        reason = "stop_loss"

                # Check time stop (approx 8 * 15m = 2 hours)
                if time.time() - pos.entry_time > 8 * 15 * 60:
                    hit_exit = True
                    reason = "time_stop"
                    
                if hit_exit:
                    current_price = latest_closed['close']
                    pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
                    if pos.side == "SHORT":
                        pnl_pct = -pnl_pct
                        
                    opp = Opportunity(
                        strategy=StrategyType.RSI_MEAN_REVERSION,
                        symbol=symbol,
                        exchanges=['binance'],
                        buy_price=pos.entry_price if pos.side == "LONG" else current_price,
                        sell_price=current_price if pos.side == "LONG" else pos.entry_price,
                        buy_exchange='binance',
                        sell_exchange='binance',
                        gross_profit_pct=pnl_pct,
                        net_profit_pct=pnl_pct - 0.2, # est fee
                        suggested_amount_usd=pos.amount_usd,
                        regime=intelligence_signals.get('regime', RegimeState.ACTIVE),
                        confidence=0.0, # 0 confidence = EXIT signal for directional trades
                    )
                    opps.append(opp)
                    
                    logger.info(f"[RSI Strategy] EXIT {pos.side} on {symbol} due to {reason} at {current_price}. PNL: {pnl_pct:.2f}%")
                    del self.active_positions[symbol]
                
                continue # Skip entry logic if already holding
            
            # --- Check Entry Filters ---
            if self.daily_trades_taken >= self.daily_limit:
                continue
                
            if len(self.active_positions) >= self.max_concurrent:
                continue
                
            # Filter: Choppy markets
            adx_val = latest_closed.get('ADX_14', 0)
            if pd.isna(adx_val) or adx_val < 20:
                continue
                
            rsi_4h = current_4h.get('rsi', 50)
            
            # Extract BB
            bb_lower = latest_closed.get('BBL_20_2.0', 0)
            bb_upper = latest_closed.get('BBU_20_2.0', 0)
            
            vol_spike = latest_closed['volume'] >= (1.5 * latest_closed['vol_avg'])
            
            # --- Check LONG Entry ---
            # 1. RSI crosses below 30
            # 2. Close <= lower BB
            # 3. Volume spike
            # 4. 4h RSI > 40
            rsi_crossed_below_30 = prev_closed['rsi'] >= 30 and latest_closed['rsi'] < 30
            
            if (rsi_crossed_below_30 and 
                latest_closed['close'] <= bb_lower and 
                vol_spike and 
                rsi_4h > 40):
                
                atr_val = latest_closed['atr']
                entry_price = latest_closed['close']
                
                # Determine Qty -> Risk 1% per trade. Let risk manager cap it if needed.
                # Stop distance = 1.5 * ATR
                stop_dist = 1.5 * atr_val
                stop_dist_pct = (stop_dist / entry_price) * 100
                
                # Opportunity creation
                opp = Opportunity(
                    strategy=StrategyType.RSI_MEAN_REVERSION,
                    symbol=symbol,
                    exchanges=['binance'],
                    buy_price=entry_price,
                    sell_price=entry_price * (1 + (stop_dist_pct/100)), # Target 1R for metrics
                    buy_exchange='binance',
                    sell_exchange='binance',
                    gross_profit_pct=stop_dist_pct,
                    net_profit_pct=stop_dist_pct - 0.2,
                    suggested_amount_usd=50.0, # Will be overridden by risk manager dynamically if needed, or we just pass it
                    regime=intelligence_signals.get('regime', RegimeState.ACTIVE),
                    confidence=1.0, # Entry signal
                )
                
                # To pass the explicit 1% risk to risk manager, we calculate qty
                # Assuming $300 capital -> $3 risk. $3 / stop_dist_pct.
                capital = 300.0 # From risk manager
                risk_amt = capital * 0.01
                suggested_pos_usd = (risk_amt / stop_dist) * entry_price
                opp.suggested_amount_usd = suggested_pos_usd
                
                opps.append(opp)
                self.active_positions[symbol] = RsiPosition(symbol, entry_price, "LONG", suggested_pos_usd)
                self.daily_trades_taken += 1
                logger.info(f"[RSI Strategy] ENTER LONG on {symbol} at {entry_price}. ATR: {atr_val:.4f}, VolSpike: {vol_spike}")
                
            # --- Check SHORT Entry ---
            # 1. RSI crosses above 70
            # 2. Close >= upper BB
            # 3. Volume spike
            # 4. 4h RSI < 60
            rsi_crossed_above_70 = prev_closed['rsi'] <= 70 and latest_closed['rsi'] > 70
            
            if (rsi_crossed_above_70 and 
                latest_closed['close'] >= bb_upper and 
                vol_spike and 
                rsi_4h < 60):
                
                atr_val = latest_closed['atr']
                entry_price = latest_closed['close']
                
                stop_dist = 1.5 * atr_val
                stop_dist_pct = (stop_dist / entry_price) * 100
                
                capital = 300.0
                risk_amt = capital * 0.01
                suggested_pos_usd = (risk_amt / stop_dist) * entry_price
                
                opp = Opportunity(
                    strategy=StrategyType.RSI_MEAN_REVERSION,
                    symbol=symbol,
                    exchanges=['binance'],
                    buy_price=entry_price,
                    sell_price=entry_price * (1 - (stop_dist_pct/100)),
                    buy_exchange='binance',
                    sell_exchange='binance',
                    gross_profit_pct=stop_dist_pct,
                    net_profit_pct=stop_dist_pct - 0.2,
                    suggested_amount_usd=suggested_pos_usd,
                    regime=intelligence_signals.get('regime', RegimeState.ACTIVE),
                    confidence=1.0, # Entry signal
                )
                
                opps.append(opp)
                self.active_positions[symbol] = RsiPosition(symbol, entry_price, "SHORT", suggested_pos_usd)
                self.daily_trades_taken += 1
                logger.info(f"[RSI Strategy] ENTER SHORT on {symbol} at {entry_price}. ATR: {atr_val:.4f}, VolSpike: {vol_spike}")
                
        return opps

    def validate(self, opportunity: Opportunity) -> bool:
        return True
