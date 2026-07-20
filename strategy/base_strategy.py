from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any

class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    """

    @abstractmethod
    def evaluate(self, symbol: str, prices_df: pd.DataFrame, fundamentals: Dict[str, Any], sentiment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates an asset's data and returns a recommendation.
        Returns a dictionary containing:
        - 'score': Float between -1.0 (strongly bearish/sell) and +1.0 (strongly bullish/buy)
        - 'action': String (BUY, SELL, HOLD)
        - 'details': Dict containing the underlying scoring details
        """
        pass
