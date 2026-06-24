import logging
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from config.constants import ANOMALY_CONTAMINATION

logger = logging.getLogger(__name__)

class AnomalyDetector:
    """Detects market anomalies using Isolation Forest."""
    
    def __init__(self):
        self.model = None
        self.scaler = RobustScaler()
        
    def fit(self, historical_features: pd.DataFrame) -> None:
        """
        Fits the anomaly detector.
        
        Args:
            historical_features: DataFrame of features (volatility, velocity, etc.)
        """
        try:
            if len(historical_features) < 100:
                logger.warning("Insufficient data to fit AnomalyDetector")
                return
                
            X = self.scaler.fit_transform(historical_features.values)
            
            self.model = IsolationForest(
                contamination=ANOMALY_CONTAMINATION,
                random_state=42,
                n_jobs=-1
            )
            self.model.fit(X)
            logger.info("Anomaly detector fitted successfully")
            
        except Exception as e:
            logger.error(f"Error fitting AnomalyDetector: {e}")
            self.model = None
            
    def is_anomaly(self, current_features: Dict[str, float]) -> Tuple[bool, float]:
        """
        Checks if current state is an anomaly.
        
        Args:
            current_features: Dict of current feature values
            
        Returns:
            Tuple of (is_anomaly, anomaly_score)
        """
        try:
            if self.model is None:
                return False, 0.0
                
            # Convert to appropriate format
            # Ensure keys match what the scaler expects (order matters if array)
            # For simplicity, assuming caller passes values in correct order or we sort keys
            feature_array = np.array([[current_features[k] for k in sorted(current_features.keys())]])
            
            X = self.scaler.transform(feature_array)
            
            # Predict: -1 for anomaly, 1 for normal
            pred = self.model.predict(X)[0]
            
            # Score: lower is more anomalous
            score = float(self.model.decision_function(X)[0])
            
            return pred == -1, score
            
        except Exception as e:
            logger.error(f"Error detecting anomaly: {e}")
            return False, 0.0
