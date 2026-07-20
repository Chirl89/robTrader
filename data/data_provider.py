from abc import ABC, abstractmethod
import pandas as pd
from typing import List, Dict, Any

class DataProvider(ABC):
    """
    Abstract base class for all market and news data providers.
    """
    
    @abstractmethod
    def get_historical_data(self, symbol: str, start_date: str, end_date: str, timeframe: str = "1Day") -> pd.DataFrame:
        """
        Fetches historical price bars for a given symbol.
        Returns a pandas DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        """
        pass

    @abstractmethod
    def get_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetches news articles related to the given symbol.
        Returns a list of dictionaries, each containing:
        - 'title': Title of the news article
        - 'url': URL to the article
        - 'source': Source name
        - 'summary': Short summary or description
        - 'published_at': ISO format timestamp of publication
        """
        pass

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches fundamental data for a given symbol.
        Returns a dictionary containing key metrics (e.g. pe_ratio, dividend_yield, market_cap).
        """
        pass
