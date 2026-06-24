import logging
import time
from typing import Tuple, Optional
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

from config.constants import COINT_ROLLING_WINDOW_DAYS, COINT_RETEST_INTERVAL_HOURS

logger = logging.getLogger(__name__)

class CointegrationAnalyzer:
    """Analyzes pairs of price series for cointegration using Engle-Granger test."""

    def __init__(self):
        self._cache = {}

    def test_pair(self, prices_a: pd.Series, prices_b: pd.Series, symbol_pair: str) -> Tuple[bool, float, float, Optional[pd.Series]]:
        """
        Tests if two price series are cointegrated.
        
        Args:
            prices_a: Price series for asset A
            prices_b: Price series for asset B
            symbol_pair: Identifier for caching
            
        Returns:
            Tuple of (is_cointegrated, p_value, hedge_ratio, spread_series)
        """
        now = time.time()
        
        # Check cache
        if symbol_pair in self._cache:
            cache_entry = self._cache[symbol_pair]
            if now - cache_entry['timestamp'] < COINT_RETEST_INTERVAL_HOURS * 3600:
                return cache_entry['is_cointegrated'], cache_entry['p_value'], cache_entry['hedge_ratio'], cache_entry['spread_series']
        
        try:
            if len(prices_a) < 30 or len(prices_b) < 30:
                logger.warning(f"Insufficient data for cointegration test on {symbol_pair}")
                return False, 1.0, 1.0, None

            # Align data
            df = pd.concat([prices_a, prices_b], axis=1).dropna()
            if len(df) < 30:
                 return False, 1.0, 1.0, None
            
            y0 = df.iloc[:, 0]
            y1 = df.iloc[:, 1]
            
            # Engle-Granger test
            score, pvalue, _ = coint(y0, y1)
            
            is_cointegrated = pvalue < 0.05
            
            # Calculate hedge ratio using simple OLS: y0 = beta * y1
            # We add constant for better fit, but for spread often people just use ratio of prices or OLS without constant
            from statsmodels.api import OLS, add_constant
            model = OLS(y0, add_constant(y1)).fit()
            hedge_ratio = model.params.iloc[1]
            
            spread_series = y0 - hedge_ratio * y1
            
            self._cache[symbol_pair] = {
                'is_cointegrated': is_cointegrated,
                'p_value': float(pvalue),
                'hedge_ratio': float(hedge_ratio),
                'spread_series': spread_series,
                'timestamp': now
            }
            
            return is_cointegrated, float(pvalue), float(hedge_ratio), spread_series
            
        except Exception as e:
            logger.error(f"Error testing cointegration for {symbol_pair}: {e}")
            return False, 1.0, 1.0, None
