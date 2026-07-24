import os
import time
import logging
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from data.data_provider import DataProvider

logger = logging.getLogger("robTrader.AlpacaProvider")

# We import Alpaca SDK components inside methods or handle ImportError to avoid crash if SDK installation is pending
class AlpacaProvider(DataProvider):
    """
    Data provider implementing the DataProvider interface using Alpaca API.
    """

    _fundamentals_cache = None  # Loaded dynamically from disk
    _cache_file = None
    _news_cache = {}          # (symbol, limit) -> (timestamp, data)
    _session = None

    def _get_session(self):
        if AlpacaProvider._session is None:
            import requests
            AlpacaProvider._session = requests.Session()
            AlpacaProvider._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
        return AlpacaProvider._session

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
        Cache results for 2h by default.
        """
        now = time.time()
        expire_hours = float(os.getenv("SENTIMENT_CACHE_EXPIRE_HOURS", "2"))
        expire_secs = expire_hours * 3600
        
        cache_key = (symbol, limit)
        if cache_key in self._news_cache:
            cache_time, cached_data = self._news_cache[cache_key]
            if now - cache_time < expire_secs:
                logger.info(f"Using cached Alpaca news for {symbol} (limit {limit})")
                return cached_data
                
        self._init_clients()
        symbol_normalized = self.normalize_symbol(symbol)
        
        from alpaca.data.requests import NewsRequest
        request_params = NewsRequest(
            symbols=symbol_normalized,
            limit=limit
        )
        
        try:
            response = self._news_client.get_news(request_params)
        except Exception as e:
            logger.error(f"Error fetching news from Alpaca for {symbol}: {e}")
            return []
            
        news_items = []
        if response and response.data and 'news' in response.data:
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
                
        self._news_cache[cache_key] = (now, news_items)
        return news_items

    def _load_fundamentals_cache(self):
        if AlpacaProvider._fundamentals_cache is not None:
            return
        
        AlpacaProvider._fundamentals_cache = {}
        try:
            import json
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            AlpacaProvider._cache_file = os.path.join(root_dir, "data_logs", "alpaca_fundamentals_cache.json")
            if os.path.exists(AlpacaProvider._cache_file):
                with open(AlpacaProvider._cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # JSON stores tuples as lists, convert back to tuple
                    AlpacaProvider._fundamentals_cache = {k: (v[0], v[1]) for k, v in data.items()}
                logger.info(f"Loaded {len(AlpacaProvider._fundamentals_cache)} cached fundamentals from {AlpacaProvider._cache_file}")
        except Exception as e:
            logger.error(f"Failed to load Alpaca fundamentals cache from disk: {e}")

    def _save_fundamentals_cache(self):
        if AlpacaProvider._cache_file is None:
            return
        try:
            import json
            os.makedirs(os.path.dirname(AlpacaProvider._cache_file), exist_ok=True)
            with open(AlpacaProvider._cache_file, 'w', encoding='utf-8') as f:
                json.dump(AlpacaProvider._fundamentals_cache, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save Alpaca fundamentals cache to disk: {e}")

    def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Alpaca Free API has limited fundamental data natively. 
        We use yfinance as fallback to fetch the asset name and basic metrics.
        Cache results for 24h by default.
        """
        self._load_fundamentals_cache()
        now = time.time()
        expire_hours = float(os.getenv("FUNDAMENTALS_CACHE_EXPIRE_HOURS", "24"))
        expire_secs = expire_hours * 3600
        
        if symbol in self._fundamentals_cache:
            cache_time, cached_data = self._fundamentals_cache[symbol]
            if now - cache_time < expire_secs:
                logger.info(f"Using cached Alpaca fundamentals for {symbol}")
                return cached_data
                
        # Normalize symbol for Yahoo Finance
        yf_symbol = symbol.upper()
        yf_symbol = yf_symbol.replace('/', '-')
        
        # Normalize cryptos (e.g. BTCUSD -> BTC-USD)
        crypto_assets = {'BTC', 'ETH', 'LTC', 'SOL', 'DOGE', 'XRP', 'ADA', 'DOT', 'LINK', 'UNI'}
        for asset in crypto_assets:
            if yf_symbol == f"{asset}USD" or yf_symbol == f"{asset}-USD":
                yf_symbol = f"{asset}-USD"
                break
                
        # Normalize dot tickers (e.g. BRK.B -> BRK-B)
        if '.' in yf_symbol:
            parts = yf_symbol.split('.')
            if parts[-1] != 'MC':
                yf_symbol = '-'.join(parts)
                
        try:
            import yfinance as yf
            ticker = yf.Ticker(yf_symbol, session=self._get_session())
            info = ticker.info or {}
            name = info.get('longName') or info.get('shortName') or symbol
        except Exception as e:
            logger.warning(f"Error fetching fundamentals from yfinance for {symbol} under Alpaca: {e}")
            name = symbol
            info = {}

        # Fallback to Alpaca Trading Client if yfinance failed to get name
        if (not name or name == symbol) and self.api_key and self.secret_key:
            try:
                from alpaca.trading.client import TradingClient
                trading_client = TradingClient(self.api_key, self.secret_key)
                asset = trading_client.get_asset(symbol)
                if asset and asset.name:
                    name = asset.name
            except Exception:
                pass
            
        data = {
            'name': name,
            'pe_ratio': info.get('trailingPE') or info.get('forwardPE'),
            'dividend_yield': info.get('dividendYield'),
            'market_cap': info.get('marketCap'),
            'debt_to_equity': info.get('debtToEquity'),
            'price_to_book': info.get('priceToBook'),
            'forward_pe': info.get('forwardPE'),
            'profit_margins': info.get('profitMargins'),
            'revenue_growth': info.get('revenueGrowth'),
            'operating_margins': info.get('operatingMargins'),
            'fifty_day_average': info.get('fiftyDayAverage'),
            'two_hundred_day_average': info.get('twoHundredDayAverage'),
            'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
            'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
            'volume': info.get('volume') or info.get('regularMarketVolume'),
            'previous_close': info.get('previousClose')
        }
        
        AlpacaProvider._fundamentals_cache[symbol] = (now, data)
        self._save_fundamentals_cache()
        return data

