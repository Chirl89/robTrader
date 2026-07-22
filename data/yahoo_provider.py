import time
import os
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime
from typing import List, Dict, Any
from data.data_provider import DataProvider

logger = logging.getLogger("robTrader.YahooProvider")

class YahooProvider(DataProvider):
    """
    Data provider implementing the DataProvider interface using Yahoo Finance (yfinance).
    """

    _fundamentals_cache = {}  # symbol -> (timestamp, data)
    _news_cache = {}          # (symbol, limit) -> (timestamp, data)

    def __init__(self):
        super().__init__()

    def _normalize_symbol(self, symbol: str) -> str:
        sym = symbol.upper()
        # Convert BTC/USD or BTC-USD to BTC-USD
        sym = sym.replace('/', '-')
        
        # Handle dots for Yahoo Finance (e.g. BRK.B -> BRK-B, but keep SAN.MC)
        if '.' in sym:
            parts = sym.split('.')
            if parts[-1] != 'MC':
                sym = '-'.join(parts)
                
        # Convert BTCUSD to BTC-USD
        crypto_assets = {'BTC', 'ETH', 'LTC', 'SOL', 'DOGE', 'XRP', 'ADA', 'DOT', 'LINK', 'UNI'}
        for asset in crypto_assets:
            if sym == f"{asset}USD":
                return f"{asset}-USD"
        return sym

    def get_historical_data(self, symbol: str, start_date: str, end_date: str, timeframe: str = "1Day") -> pd.DataFrame:
        """
        Fetches historical price bars using yfinance.
        Supports standard daily timeframe.
        """
        symbol = self._normalize_symbol(symbol)
        # Map timeframe to yfinance intervals
        # Alpaca standard timeframes: 1Min, 5Min, 15Min, 1Hour, 1Day
        interval_map = {
            "1Min": "1m",
            "5Min": "5m",
            "15Min": "15m",
            "1Hour": "60m",
            "1Day": "1d"
        }
        interval = interval_map.get(timeframe, "1d")
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval)
        
        if df.empty:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
        df = df.reset_index()
        # Rename columns to standard lowercase representation
        rename_map = {
            'Date': 'timestamp',
            'Datetime': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }
        df = df.rename(columns=rename_map)
        
        # Keep only standard columns
        cols_to_keep = [col for col in ['timestamp', 'open', 'high', 'low', 'close', 'volume'] if col in df.columns]
        df = df[cols_to_keep]
        
        # Ensure timestamp is string format for standard transfer
        if 'timestamp' in df.columns:
            df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S%z')
            
        return df

    def get_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetches news articles using yfinance's built-in news feed.
        Cache results for 2h by default.
        """
        now = time.time()
        expire_hours = float(os.getenv("SENTIMENT_CACHE_EXPIRE_HOURS", "2"))
        expire_secs = expire_hours * 3600
        
        cache_key = (symbol, limit)
        if cache_key in self._news_cache:
            cache_time, cached_data = self._news_cache[cache_key]
            if now - cache_time < expire_secs:
                logger.info(f"Using cached Yahoo news for {symbol} (limit {limit})")
                return cached_data
                
        symbol_normalized = self._normalize_symbol(symbol)
        ticker = yf.Ticker(symbol_normalized)
        try:
            yf_news = ticker.news
        except Exception as e:
            logger.error(f"Error fetching news from yfinance for {symbol}: {e}")
            yf_news = []
        
        news_items = []
        if yf_news:
            for item in yf_news[:limit]:
                # Convert Unix epoch publish time to ISO format
                pub_time = item.get('providerPublishTime', 0)
                if pub_time:
                    published_at = datetime.fromtimestamp(pub_time).isoformat()
                else:
                    published_at = datetime.now().isoformat()
                    
                news_items.append({
                    'title': item.get('title', ''),
                    'url': item.get('link', ''),
                    'source': item.get('publisher', 'Yahoo Finance'),
                    'summary': item.get('summary', item.get('title', '')),
                    'published_at': published_at
                })
        
        self._news_cache[cache_key] = (now, news_items)
        return news_items

    def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches fundamental data from yfinance.info.
        Cache results for 24h by default.
        """
        now = time.time()
        expire_hours = float(os.getenv("FUNDAMENTALS_CACHE_EXPIRE_HOURS", "24"))
        expire_secs = expire_hours * 3600
        
        if symbol in self._fundamentals_cache:
            cache_time, cached_data = self._fundamentals_cache[symbol]
            if now - cache_time < expire_secs:
                logger.info(f"Using cached Yahoo fundamentals for {symbol}")
                return cached_data
                
        symbol_normalized = self._normalize_symbol(symbol)
        
        # Setup session with custom headers to prevent yfinance blocking
        session = None
        try:
            import requests
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
        except Exception:
            pass

        try:
            ticker = yf.Ticker(symbol_normalized, session=session)
            info = ticker.info or {}
        except Exception as e:
            logger.error(f"Error fetching fundamentals from yfinance for {symbol}: {e}")
            info = {}
        
        if not info:
            data = {'name': symbol}
        else:
            data = {
                'name': info.get('longName') or info.get('shortName') or symbol,
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
            
        self._fundamentals_cache[symbol] = (now, data)
        return data

