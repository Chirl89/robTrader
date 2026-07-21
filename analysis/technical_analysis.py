import pandas as pd
import numpy as np
from typing import Dict, Any


def calculate_sma(df: pd.DataFrame, window: int) -> pd.Series:
    """Calculates Simple Moving Average (SMA)."""
    return df['close'].rolling(window=window).mean()

def calculate_ema(df: pd.DataFrame, window: int) -> pd.Series:
    """Calculates Exponential Moving Average (EMA)."""
    return df['close'].ewm(span=window, adjust=False).mean()

def calculate_rsi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Calculates Relative Strength Index (RSI) using Wilder's smoothing."""
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Use exponential moving average for Wilder's smoothing
    avg_gain = gain.ewm(com=window - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=window - 1, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-10) # avoid division by zero
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """Calculates MACD, Signal line, and Histogram."""
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    
    return macd_line, signal_line, macd_hist

def calculate_bollinger_bands(df: pd.DataFrame, window: int = 20, num_std: int = 2) -> tuple:
    """Calculates Bollinger Bands (Upper, Middle, Lower)."""
    middle = df['close'].rolling(window=window).mean()
    std = df['close'].rolling(window=window).std()
    upper = middle + (num_std * std)
    lower = middle - (num_std * std)
    return upper, middle, lower

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Appends common technical indicators to the historical DataFrame.
    """
    if df.empty or len(df) < 30:
        # Return as is if we don't have enough periods to calculate indicators
        return df
        
    df = df.copy()
    
    df['sma_20'] = calculate_sma(df, 20)
    df['sma_50'] = calculate_sma(df, 50)
    df['ema_10'] = calculate_ema(df, 10)
    df['rsi'] = calculate_rsi(df, 14)
    
    macd, signal, hist = calculate_macd(df)
    df['macd'] = macd
    df['macd_signal'] = signal
    df['macd_hist'] = hist
    
    upper, middle, lower = calculate_bollinger_bands(df)
    df['bb_upper'] = upper
    df['bb_middle'] = middle
    df['bb_lower'] = lower
    
    return df

def generate_ta_signals(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Analyzes indicator values for the most recent bar and returns a signal score.
    Returns a dict with:
    - 'score': A float between -1.0 (strongly bearish) and +1.0 (strongly bullish) or None
    - 'indicators': Dict of current values
    """
    if df.empty or len(df) < 50:
        return {'score': None, 'indicators': {}}
        
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    signals = []
    
    # 1. RSI Signals
    rsi = latest['rsi']
    rsi_score = 0.0
    if rsi < 30:
        rsi_score = 0.8  # Oversold (bullish reversal)
    elif rsi > 70:
        rsi_score = -0.8 # Overbought (bearish reversal)
    elif 30 <= rsi <= 45:
        rsi_score = 0.2  # Slightly oversold / stabilizing
    elif 55 <= rsi <= 70:
        rsi_score = -0.2 # Slightly overbought
    signals.append(rsi_score)
    
    # 2. Moving Average Crossover (EMA 10 vs SMA 50)
    ema_10 = latest['ema_10']
    sma_50 = latest['sma_50']
    prev_ema_10 = prev['ema_10']
    prev_sma_50 = prev['sma_50']
    
    ma_score = 0.0
    if prev_ema_10 <= prev_sma_50 and ema_10 > sma_50:
        ma_score = 0.9  # Golden Cross (Bullish breakout)
    elif prev_ema_10 >= prev_sma_50 and ema_10 < sma_50:
        ma_score = -0.9 # Death Cross (Bearish breakout)
    else:
        # Static check
        ma_score = 0.3 if ema_10 > sma_50 else -0.3
    signals.append(ma_score)
    
    # 3. MACD Histogram crossovers
    macd_hist = latest['macd_hist']
    prev_macd_hist = prev['macd_hist']
    
    macd_score = 0.0
    if prev_macd_hist <= 0 and macd_hist > 0:
        macd_score = 0.7  # Histogram crosses above zero (bullish momentum)
    elif prev_macd_hist >= 0 and macd_hist < 0:
        macd_score = -0.7 # Histogram crosses below zero (bearish momentum)
    else:
        # Trend check
        macd_score = 0.2 if macd_hist > 0 else -0.2
    signals.append(macd_score)
    
    # 4. Bollinger Band breakouts
    close = latest['close']
    bb_upper = latest['bb_upper']
    bb_lower = latest['bb_lower']
    
    bb_score = 0.0
    if close < bb_lower:
        bb_score = 0.6  # Price below lower band (oversold/rebound play)
    elif close > bb_upper:
        bb_score = -0.6 # Price above upper band (overbought/regression play)
    signals.append(bb_score)
    
    # Average the signals
    avg_score = float(np.mean(signals)) if signals else 0.0
    
    return {
        'score': round(avg_score, 2),
        'indicators': {
            'close': float(close),
            'rsi': float(rsi),
            'macd_hist': float(macd_hist),
            'ema_10': float(ema_10),
            'sma_50': float(sma_50),
            'bb_upper': float(bb_upper),
            'bb_lower': float(bb_lower)
        }
    }
