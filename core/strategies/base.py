import abc
from typing import List, Dict, Any
from data.models import Opportunity

class BaseStrategy(abc.ABC):
    """Abstract base class for trading strategies."""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        
    @abc.abstractmethod
    def scan(self, market_data: Dict[str, Any], intelligence_signals: Dict[str, Any]) -> List[Opportunity]:
        """Scans market data and returns a list of detected opportunities."""
        pass
        
    @abc.abstractmethod
    def validate(self, opportunity: Opportunity) -> bool:
        """Validates an opportunity before execution."""
        pass
        
    def disable(self):
        self.enabled = False
        
    def enable(self):
        self.enabled = True
