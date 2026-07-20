import os
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from data.data_provider import DataProvider

# We import Alpaca SDK components inside methods or handle ImportError to avoid crash if SDK installation is pending
class AlpacaProvider(DataProvider):
    """
    Data provider implementing the DataProvider interface using Alpaca API.
    """

    def __init__(self, api_key: str = None, secret_key: str = None):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY_ID")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        
        self.initialized = bool(self.api_key and self.secret_key)
        self._historical_client = None
        self._crypto_historical_client = None
        self._news_client = None

    def _init_clients(self):
        if not self.initialized:
            raise ValueError("Alpaca API credentials not set. Please check your .env file.")
        
        if self._historical_client is None:
            from alpaca.data.historical import StockHistoricalDataClient
            self._historical_client = StockHistoricalDataClient(self.api_key, self.secret_key)
            
        if self._crypto_historical_client is None:
            from alpaca.data.historical import CryptoHistoricalDataClient
            self._crypto_historical_client = CryptoHistoricalDataClient(self.api_key, self.secret_key)
            
        if self._news_client is None:
            from alpaca.data.historical import NewsClient
            self._news_client = NewsClient(self.api_key, self.secret_key)

    def is_crypto(self, symbol: str) -> bool:
        sym = symbol.upper()
        if '/' in sym:
            return True
        crypto_assets = {'BTC', 'ETH', 'LTC', 'SOL', 'DOGE', 'XRP', 'ADA', 'DOT', 'LINK', 'UNI'}
        for asset in crypto_assets:
            if sym == f"{asset}USD":
                return True
        return False

    def normalize_symbol(self, symbol: str) -> str:
        sym = symbol.upper()
        if self.is_crypto(sym) and '/' not in sym:
            return sym[:-3] + '/' + sym[-3:]
        return sym

    def get_historical_data(self, symbol: str, start_date: str, end_date: str, timeframe: str = "1Day") -> pd.DataFrame:
        """
        Fetches historical bars using Alpaca StockHistoricalDataClient or CryptoHistoricalDataClient.
        """
        self._init_clients()
        
        symbol = self.normalize_symbol(symbol)
        
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        # Parse timeframe
        tf_map = {
            "1Min": TimeFrame.Minute,
            "5Min": TimeFrame(5, TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day
        }
        alpaca_tf = tf_map.get(timeframe, TimeFrame.Day)
        
        # Parse dates to datetimes if they are strings
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        if self.is_crypto(symbol):
            from alpaca.data.requests import CryptoBarsRequest
            request_params = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_tf,
                start=start_dt,
                end=end_dt
            )
            bars = self._crypto_historical_client.get_crypto_bars(request_params)
        else:
            from alpaca.data.requests import StockBarsRequest
            request_params = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_tf,
                start=start_dt,
                end=end_dt
            )
            bars = self._historical_client.get_stock_bars(request_params)
        
        # Check if we got data
        if not bars or not bars.data or symbol not in bars.data:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
        df = bars.df
        
        # Reset MultiIndex (symbol, timestamp) -> columns
        df = df.reset_index()
        
        # Rename and keep standard columns
        df = df.rename(columns={
            'timestamp': 'timestamp',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume'
        })
        
        cols_to_keep = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = df[cols_to_keep]
        
        # Format timestamp as ISO string
        df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S%z')
        
        return df

    def get_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetches news articles using Alpaca NewsClient.
        """
        self._init_clients()
        
        symbol = self.normalize_symbol(symbol)
        
        from alpaca.data.requests import NewsRequest
        
        request_params = NewsRequest(
            symbols=symbol,
            limit=limit
        )
        
        response = self._news_client.get_news(request_params)
        
        news_items = []
        if not response or not response.data or 'news' not in response.data:
            return news_items
            
        for article in response.data['news']:
            published = article.created_at
            if isinstance(published, datetime):
                published_at = published.isoformat()
            else:
                published_at = str(published)
                
            news_items.append({
                'title': article.headline,
                'url': article.url,
                'source': article.source,
                'summary': article.summary if article.summary else article.headline,
                'published_at': published_at
            })
            
        return news_items

    def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Alpaca Free API has limited fundamental data natively. 
        We return empty or mock structure, and recommend YahooProvider for fundamentals.
        """
        # Fundamentals are better sourced from yfinance or dedicated fundamental APIs
        return {
            'pe_ratio': None,
            'dividend_yield': None,
            'market_cap': None,
            'debt_to_equity': None,
            'price_to_book': None
        }
