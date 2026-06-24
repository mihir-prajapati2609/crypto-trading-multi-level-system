import logging
import numpy as np
import pandas as pd
from typing import Optional
from hmmlearn.hmm import GaussianHMM
from data.models import RegimeState
from config.constants import REGIME_MULTIPLIERS, HMM_N_STATES

logger = logging.getLogger(__name__)

class RegimeDetector:
    """Detects market regimes using Hidden Markov Models."""
    
    def __init__(self):
        self.model = None
        self.state_map = {}  # Maps HMM states to RegimeState
        
    def fit(self, price_series: pd.Series) -> None:
        """
        Fits the HMM to historical price data.
        
        Args:
            price_series: Series of historical prices
        """
        try:
            if len(price_series) < 100:
                logger.warning("Insufficient data to fit HMM")
                return
                
            # Feature engineering for HMM
            returns = np.log(price_series / price_series.shift(1)).fillna(0)
            volatility = returns.rolling(window=10).std().fillna(0)
            
            # Combine features
            features = np.column_stack([returns.values, volatility.values])
            
            # Fit HMM
            self.model = GaussianHMM(n_components=HMM_N_STATES, covariance_type="full", n_iter=100)
            self.model.fit(features)
            
            # Map states based on volatility
            states = self.model.predict(features)
            state_vols = [np.mean(volatility.values[states == i]) for i in range(HMM_N_STATES)]
            
            # Sort states by volatility
            sorted_states = np.argsort(state_vols)
            
            # Map to Regimes (lowest vol = Calm, middle = Active, highest = Chaotic)
            self.state_map = {
                sorted_states[0]: RegimeState.CALM,
                sorted_states[1]: RegimeState.ACTIVE,
                sorted_states[2]: RegimeState.CHAOTIC
            }
            
            logger.info("Regime detector HMM fitted successfully")
            
        except Exception as e:
            logger.error(f"Error fitting HMM: {e}")
            self.model = None
            
    def predict_regime(self, price_series: pd.Series) -> RegimeState:
        """
        Predicts current regime state.
        
        Args:
            price_series: Recent price series to evaluate
            
        Returns:
            RegimeState
        """
        try:
            if self.model is None or len(price_series) < 15:
                return RegimeState.ACTIVE  # Default fallback
                
            returns = np.log(price_series / price_series.shift(1)).fillna(0)
            volatility = returns.rolling(window=10).std().fillna(0)
            
            features = np.column_stack([returns.values, volatility.values])
            states = self.model.predict(features)
            
            current_state = states[-1]
            return self.state_map.get(current_state, RegimeState.ACTIVE)
            
        except Exception as e:
            logger.error(f"Error predicting regime: {e}")
            return RegimeState.ACTIVE
            
    def get_multiplier(self, regime: RegimeState) -> float:
        """Gets position sizing multiplier for regime."""
        # 0=Calm, 1=Active, 2=Chaotic. We map enum values to 0, 1, 2
        mapping = {
            RegimeState.CALM: 0,
            RegimeState.ACTIVE: 1,
            RegimeState.CHAOTIC: 2
        }
        idx = mapping.get(regime, 1)
        return REGIME_MULTIPLIERS.get(idx, 1.0)
