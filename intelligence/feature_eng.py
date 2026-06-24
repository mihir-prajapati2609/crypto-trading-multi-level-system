import logging
import numpy as np
import pandas as pd
from typing import Dict
from data.models import OrderBookSnapshot, TickerData

logger = logging.getLogger(__name__)

class FeatureEngineer:
    """Centralized feature engineering pipeline."""
    
    @staticmethod
    def compute_obi_features(order_book: OrderBookSnapshot) -> Dict[str, float]:
        """Computes Order Book Imbalance features."""
        features = {}
        try:
            if len(order_book.bids) < 5 or len(order_book.asks) < 5:
                return features
                
            for i in range(5):
                bid_qty = order_book.bids[i].quantity
                ask_qty = order_book.asks[i].quantity
                total = bid_qty + ask_qty
                features[f'vol_ratio_l{i+1}'] = (bid_qty - ask_qty) / total if total > 0 else 0
                
            total_bid_5 = sum(b.quantity for b in order_book.bids[:5])
            total_ask_5 = sum(a.quantity for a in order_book.asks[:5])
            total_5 = total_bid_5 + total_ask_5
            features['imbalance_top5'] = (total_bid_5 - total_ask_5) / total_5 if total_5 > 0 else 0
            features['spread_pct'] = order_book.spread_pct
            
        except Exception as e:
            logger.error(f"Error computing OBI features: {e}")
            
        return features

    @staticmethod
    def compute_anomaly_features(ticker: TickerData, order_book: OrderBookSnapshot) -> Dict[str, float]:
        """Computes features for anomaly detection."""
        # Note: In a real system, you'd calculate velocity and rolling volume
        # Here we just use instantaneous proxies for simplicity
        features = {
            'spread_pct': order_book.spread_pct,
            'price_change_pct': ticker.change_pct,
            'base_volume': ticker.base_volume
        }
        return features
        
    @staticmethod
    def compute_returns(prices: pd.Series) -> pd.Series:
        """Computes log returns."""
        return np.log(prices / prices.shift(1)).fillna(0)

    @staticmethod
    def normalize(features: pd.DataFrame) -> pd.DataFrame:
        """Simple min-max normalization."""
        return (features - features.min()) / (features.max() - features.min())
