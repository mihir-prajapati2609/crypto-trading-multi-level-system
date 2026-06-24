import logging
import pandas as pd
import numpy as np
from data.models import SignalAction

logger = logging.getLogger(__name__)

class ZScoreCalculator:
    """Calculates Z-score for mean reversion trading."""
    
    def calculate(self, spread_series: pd.Series, lookback: int = 60) -> float:
        """
        Calculates current z-score based on historical spread.
        
        Args:
            spread_series: Series of historical spread values
            lookback: Rolling window for mean/std
            
        Returns:
            Current z-score
        """
        try:
            if len(spread_series) < 2:
                return 0.0
                
            window = spread_series.tail(lookback)
            mean = window.mean()
            std = window.std()
            
            if pd.isna(std) or std == 0:
                return 0.0
                
            current_spread = spread_series.iloc[-1]
            z_score = (current_spread - mean) / std
            
            return float(z_score)
            
        except Exception as e:
            logger.error(f"Error calculating z-score: {e}")
            return 0.0

    def get_signal(self, z_score: float, entry: float = 2.0, exit: float = 0.5, stop: float = 3.0) -> SignalAction:
        """
        Generates trading signal based on z-score thresholds.
        
        Args:
            z_score: Current z-score
            entry: Threshold to enter trade
            exit: Threshold to exit trade
            stop: Threshold for stop-loss
            
        Returns:
            SignalAction enum
        """
        abs_z = abs(z_score)
        
        if abs_z >= stop:
            return SignalAction.EXIT  # Stop loss
            
        if z_score <= -entry:
            return SignalAction.LONG  # Spread is too low, buy underperformer, short overperformer
            
        if z_score >= entry:
            return SignalAction.SHORT # Spread is too high, short overperformer, buy underperformer
            
        if abs_z <= exit:
            return SignalAction.EXIT  # Mean reversion achieved
            
        return SignalAction.HOLD
