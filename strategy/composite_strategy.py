import os
import pandas as pd
from typing import Dict, Any
from strategy.base_strategy import BaseStrategy
from analysis.technical_analysis import add_all_indicators, generate_ta_signals
from analysis.fundamental_analysis import evaluate_fundamentals

class CompositeStrategy(BaseStrategy):
    """
    A composite strategy that combines technical, fundamental, and news sentiment scores.
    """

    def __init__(self, technical_weight: float = 0.40, fundamental_weight: float = 0.30, sentiment_weight: float = 0.30):
        self.tech_w = technical_weight
        self.fund_w = fundamental_weight
        self.sent_w = sentiment_weight
        
        # Ensure weights normalize to 1.0
        total = self.tech_w + self.fund_w + self.sent_w
        self.tech_w /= total
        self.fund_w /= total
        self.sent_w /= total

    def evaluate(self, symbol: str, prices_df: pd.DataFrame, fundamentals: Dict[str, Any], sentiment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates the symbol by combining technical indicators, fundamental health, and news sentiment.
        """
        # 1. Technical Indicators & Signal
        df_indicators = add_all_indicators(prices_df)
        ta_result = generate_ta_signals(df_indicators)
        ta_score = ta_result.get('score', 0.0)
        
        # 2. Fundamental Score
        fund_result = evaluate_fundamentals(fundamentals)
        fund_score = fund_result.get('score', 0.0)
        
        # 3. Sentiment Score
        sent_score = sentiment.get('score', 0.0)
        
        # Weighted score calculation
        weighted_score = (
            (ta_score * self.tech_w) + 
            (fund_score * self.fund_w) + 
            (sent_score * self.sent_w)
        )
        weighted_score = round(weighted_score, 2)
        
        # Determine execution action based on threshold
        # BUY threshold: > 0.25 (Moderately Bullish)
        # SELL threshold: < -0.25 (Moderately Bearish)
        # HOLD: inside [-0.25, 0.25]
        buy_threshold = float(os.getenv("BUY_THRESHOLD", "0.25"))
        sell_threshold = float(os.getenv("SELL_THRESHOLD", "-0.25"))
        
        if weighted_score >= buy_threshold:
            action = "BUY"
        elif weighted_score <= sell_threshold:
            action = "SELL"
        else:
            action = "HOLD"
            
        return {
            'symbol': symbol,
            'score': weighted_score,
            'action': action,
            'details': {
                'technical_score': ta_score,
                'technical_indicators': ta_result.get('indicators', {}),
                'fundamental_score': fund_score,
                'fundamental_metrics': fund_result.get('metrics', {}),
                'sentiment_score': sent_score,
                'article_count': sentiment.get('article_count', 0)
            }
        }
