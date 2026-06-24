import logging
from typing import List, Dict, Any
from core.strategies.base import BaseStrategy
from data.models import Opportunity

logger = logging.getLogger(__name__)

class FundingRateStrategy(BaseStrategy):
    """Funding rate arbitrage strategy."""
    
    def __init__(self):
        super().__init__("funding_rate")

    def scan(self, market_data: Dict[str, Any], intelligence_signals: Dict[str, Any]) -> List[Opportunity]:
        return []

    def validate(self, opportunity: Opportunity) -> bool:
        return True
