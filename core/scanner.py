import logging
from typing import List, Dict, Any

from data.models import Opportunity
from core.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

class OpportunityScanner:
    """Coordinates opportunity scanning across all active strategies."""
    
    def __init__(self, strategies: List[BaseStrategy]):
        self.strategies = strategies

    async def scan_tick(self, market_data: Dict[str, Any], intelligence_signals: Dict[str, Any]) -> List[Opportunity]:
        """
        Runs a scan tick on all strategies.
        """
        all_opportunities = []
        
        for strategy in self.strategies:
            if not strategy.enabled:
                continue
                
            try:
                opps = strategy.scan(market_data, intelligence_signals)
                valid_opps = [o for o in opps if strategy.validate(o)]
                all_opportunities.extend(valid_opps)
            except Exception as e:
                logger.error(f"Error scanning strategy {strategy.name}: {e}")
                
        return all_opportunities
