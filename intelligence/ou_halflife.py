import logging
import numpy as np
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)

class OUHalfLifeEstimator:
    """Estimates Ornstein-Uhlenbeck half-life for mean reversion speed."""
    
    def estimate(self, spread_series: pd.Series) -> Optional[float]:
        """
        Estimates the half-life of mean reversion.
        
        Args:
            spread_series: Series of historical spread values
            
        Returns:
            Half-life in minutes (assuming series frequency is 1-minute),
            or None if not mean-reverting.
        """
        try:
            if len(spread_series) < 30:
                return None
                
            # AR(1) regression: dX = alpha + beta * X_{t-1} + e
            X = spread_series.values
            X_lag = np.roll(X, 1)
            X_lag[0] = 0  # Ignore first element
            
            dX = X - X_lag
            
            # Remove first element which is invalid due to lag
            X_lag = X_lag[1:]
            dX = dX[1:]
            
            import statsmodels.api as sm
            model = sm.OLS(dX, sm.add_constant(X_lag)).fit()
            
            beta = model.params[1]
            
            # If beta >= 0, series is not mean-reverting
            if beta >= 0:
                return None
                
            theta = -np.log(1 + beta)
            if theta <= 0:
                return None
                
            half_life = np.log(2) / theta
            return float(half_life)
            
        except Exception as e:
            logger.error(f"Error estimating OU half-life: {e}")
            return None
