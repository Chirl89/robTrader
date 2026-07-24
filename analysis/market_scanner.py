import pandas as pd
import requests
import io
import logging
from typing import List

logger = logging.getLogger("robTrader.MarketScanner")

def get_sp500_symbols() -> List[str]:
    """
    Scrapes the list of S&P 500 company tickers dynamically from Wikipedia.
    Uses requests with a custom User-Agent to avoid HTTP 403 Forbidden errors,
    and wraps the response text in StringIO to force pandas parsing.
    """
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Wrap response text in StringIO to prevent FileNotFoundError in pandas
        tables = pd.read_html(io.StringIO(response.text))
        df = tables[0]
        symbols = df['Symbol'].tolist()
        cleaned_symbols = [sym.strip() for sym in symbols if isinstance(sym, str) and sym.strip()]
        return cleaned_symbols
    except Exception as e:
        logger.error(f"Failed to scrape S&P 500 symbols: {e}. Falling back to default list.")
        # Safe fallback list of mega-caps
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'LLY', 
            'UNH', 'JPM', 'V', 'AVGO', 'XOM', 'TSM', 'WMT', 'PG', 'MA', 'HD'
        ]

def get_ibex35_symbols() -> List[str]:
    """
    Scrapes the list of IBEX 35 company tickers dynamically from Wikipedia.
    """
    try:
        url = "https://en.wikipedia.org/wiki/IBEX_35"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        tables = pd.read_html(io.StringIO(response.text))
        
        # Robustly search for the table containing components
        df = None
        for table in tables:
            if 'Ticker' in table.columns and 'Company' in table.columns:
                df = table
                break
                
        if df is None:
            raise ValueError("Could not find components table with 'Ticker' and 'Company' columns")
            
        symbols = df['Ticker'].tolist()
        return [sym.strip() for sym in symbols if isinstance(sym, str) and sym.strip()]
    except Exception as e:
        logger.error(f"Failed to scrape IBEX 35 symbols: {e}. Falling back to default list.")
        # Safe fallback list of major IBEX 35 stocks (with .MC suffix for Yahoo Finance)
        return [
            'SAN.MC', 'ITX.MC', 'IBE.MC', 'BBVA.MC', 'TEF.MC', 'AMS.MC', 'REP.MC', 
            'CABK.MC', 'ELE.MC', 'FER.MC', 'IAG.MC', 'GRF.MC', 'MAP.MC', 'NTGY.MC'
        ]

def get_top_cryptos() -> List[str]:
    """
    Returns standard highly-liquid cryptocurrency pairs.
    """
    return ['BTCUSD', 'ETHUSD', 'SOLUSD', 'LTCUSD', 'DOGEUSD', 'ADAUSD', 'LINKUSD']

def get_dynamic_market_symbols(max_stocks: int = 15, include_crypto: bool = True, index_name: str = "SP500") -> List[str]:
    """
    Returns a combined list of top stocks from the selected index and cryptocurrencies.
    Supports index_name values: 'SP500', 'IBEX35', or 'BOTH'.
    If max_stocks <= 0, no limit is applied (returns all stocks for that index).
    """
    import os
    allow_unlimited = os.getenv("ALLOW_UNLIMITED_SCAN", "False").lower() == "true"
    if max_stocks <= 0 and not allow_unlimited:
        logger.warning(
            f"DYNAMIC_STOCK_LIMIT is set to {max_stocks} (unlimited). "
            f"To prevent VM freezes due to heavy API calls, a safe limit of 30 stocks is being enforced. "
            f"To bypass this safety limit, add ALLOW_UNLIMITED_SCAN=True in your .env file."
        )
        max_stocks = 30

    index_name = index_name.upper() if index_name else "SP500"
    
    if index_name == "IBEX35":
        stocks = get_ibex35_symbols()
        target_stocks = stocks[:max_stocks] if max_stocks > 0 else stocks
    elif index_name == "BOTH":
        # Alternate or split spaces equally
        sp500_stocks = get_sp500_symbols()
        ibex_stocks = get_ibex35_symbols()
        if max_stocks > 0:
            half = max_stocks // 2
            target_stocks = sp500_stocks[:half] + ibex_stocks[:(max_stocks - half)]
        else:
            target_stocks = sp500_stocks + ibex_stocks
    else:
        stocks = get_sp500_symbols()
        target_stocks = stocks[:max_stocks] if max_stocks > 0 else stocks
        
    if include_crypto:
        cryptos = get_top_cryptos()
        return target_stocks + cryptos
        
    return target_stocks

