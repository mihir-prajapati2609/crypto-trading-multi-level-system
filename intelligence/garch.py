import logging
import numpy as np
import pandas as pd
from typing import Optional
from arch import arch_model

logger = logging.getLogger(__name__)

class GARCHForecaster:
    """Forecaster for volatility using GARCH(1,1)."""
    
    def __init__(self):
        self.model_res = None
        
    def fit(self, returns_series: pd.Series) -> None:
        """
        Fits a GARCH(1,1) model to the returns.
        
        Args:
            returns_series: Series of percentage returns (log returns * 100)
        """
        try:
            if len(returns_series) < 100:
                logger.warning("Insufficient data to fit GARCH model")
                return
                
            # GARCH(1,1) with Student-t distribution
            am = arch_model(returns_series, vol='Garch', p=1, q=1, dist='t')
            self.model_res = am.fit(disp='off')
            logger.info("GARCH model fitted successfully")
            
        except Exception as e:
            logger.error(f"Error fitting GARCH model: {e}")
            self.model_res = None
            
    def forecast(self, default_vol: float = 0.01) -> float:
        """
        Forecasts next-period volatility.
        
        Args:
            default_vol: Fallback volatility if model not fitted
            
        Returns:
            Predicted volatility
        """
        try:
            if self.model_res is None:
                return default_vol
                
            forecasts = self.model_res.forecast(horizon=1)
            predicted_variance = forecasts.variance.values[-1, 0]
            predicted_vol = np.sqrt(predicted_variance)
            
            return float(predicted_vol)
            
        except Exception as e:
            logger.error(f"Error forecasting GARCH volatility: {e}")
            return default_vol
