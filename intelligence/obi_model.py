import logging
import numpy as np
import pandas as pd
from typing import Dict, Any
import lightgbm as lgb
from data.models import OrderBookSnapshot

logger = logging.getLogger(__name__)

class OBIPredictor:
    """Predicts short-term price direction using Order Book Imbalance (LightGBM)."""
    
    def __init__(self):
        self.model = None
        
    def extract_features(self, order_book: OrderBookSnapshot) -> Dict[str, float]:
        """
        Extracts OBI features from an order book snapshot.
        
        Args:
            order_book: Current order book
            
        Returns:
            Dict of features
        """
        features = {}
        
        try:
            # We need at least 5 levels
            if len(order_book.bids) < 5 or len(order_book.asks) < 5:
                return features
                
            # Level 1-5 volume ratio
            for i in range(5):
                bid_qty = order_book.bids[i].quantity
                ask_qty = order_book.asks[i].quantity
                total = bid_qty + ask_qty
                
                features[f'vol_ratio_l{i+1}'] = (bid_qty - ask_qty) / total if total > 0 else 0
                
            # Total imbalance top 5
            total_bid_5 = sum(b.quantity for b in order_book.bids[:5])
            total_ask_5 = sum(a.quantity for a in order_book.asks[:5])
            total_5 = total_bid_5 + total_ask_5
            
            features['imbalance_top5'] = (total_bid_5 - total_ask_5) / total_5 if total_5 > 0 else 0
            
            # Spread
            features['spread_pct'] = order_book.spread_pct
            
            return features
            
        except Exception as e:
            logger.error(f"Error extracting OBI features: {e}")
            return {}
            
    def predict(self, features: Dict[str, float]) -> float:
        """
        Predicts price direction.
        
        Args:
            features: Dictionary of extracted features
            
        Returns:
            Score from -1 (down) to 1 (up)
        """
        try:
            if self.model is None or not features:
                return 0.0
                
            # Convert to DataFrame matching training format
            df = pd.DataFrame([features])
            
            # Assuming model outputs probability of UP class
            # Or continuous score
            pred = self.model.predict(df)[0]
            
            # Convert [0,1] probability to [-1, 1] score
            score = (pred * 2) - 1
            return float(score)
            
        except Exception as e:
            logger.error(f"Error predicting OBI: {e}")
            return 0.0
            
    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Trains the LightGBM model."""
        try:
            if len(X) < 1000:
                logger.warning("Insufficient data to train OBI model")
                return
                
            dtrain = lgb.Dataset(X, label=y)
            params = {
                'objective': 'regression', # or binary depending on labels
                'metric': 'rmse',
                'boosting_type': 'gbdt',
                'learning_rate': 0.05,
                'num_leaves': 31,
                'max_depth': 5,
                'verbose': -1
            }
            
            self.model = lgb.train(params, dtrain, num_boost_round=100)
            logger.info("OBI predictor trained successfully")
            
        except Exception as e:
            logger.error(f"Error training OBI predictor: {e}")
            self.model = None
