import logging
import pandas as pd
from typing import List, Dict, Any
from data.data_provider import DataProvider
from data.alpaca_provider import AlpacaProvider
from data.yahoo_provider import YahooProvider
from broker.hybrid_broker import HybridBroker

logger = logging.getLogger("robTrader.HybridDataProvider")

class HybridDataProvider(DataProvider):
    """
    A data provider that routes US stocks and Cryptos to Alpaca and fallback assets (like IBEX) to Yahoo Finance.
    """
    def __init__(self, alpaca_provider: AlpacaProvider, yahoo_provider: YahooProvider, hybrid_broker: HybridBroker = None):
        self.alpaca_provider = alpaca_provider
        self.yahoo_provider = yahoo_provider
        self.hybrid_broker = hybrid_broker

    def _should_use_alpaca(self, symbol: str) -> bool:
        if self.hybrid_broker is not None:
            return self.hybrid_broker._is_alpaca_asset(symbol)
        # If no broker, use a simple rule: anything with '.MC' is Yahoo, others are Alpaca
        return '.MC' not in symbol.upper()

    def get_historical_data(self, symbol: str, start_date: str, end_date: str, timeframe: str = "1Day") -> pd.DataFrame:
        if self._should_use_alpaca(symbol):
            try:
                df = self.alpaca_provider.get_historical_data(symbol, start_date, end_date, timeframe)
                if not df.empty:
                    return df
            except Exception as e:
                logger.warning(f"Failed to get historical data from Alpaca for {symbol}: {e}. Falling back to Yahoo Finance.")
        
        return self.yahoo_provider.get_historical_data(symbol, start_date, end_date, timeframe)

    def get_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        if self._should_use_alpaca(symbol):
            try:
                news = self.alpaca_provider.get_news(symbol, limit)
                if news:
                    return news
            except Exception as e:
                logger.warning(f"Failed to get news from Alpaca for {symbol}: {e}. Falling back to Yahoo Finance.")
                
        return self.yahoo_provider.get_news(symbol, limit)

    def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        if self._should_use_alpaca(symbol):
            try:
                fundamentals = self.alpaca_provider.get_fundamentals(symbol)
                # Ensure fundamentals are returned properly
                if fundamentals and fundamentals.get('name') and fundamentals.get('pe_ratio') is not None:
                    return fundamentals
            except Exception as e:
                logger.warning(f"Failed to get fundamentals from Alpaca for {symbol}: {e}. Falling back to Yahoo Finance.")
                
        return self.yahoo_provider.get_fundamentals(symbol)
