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
        Adjusts weights dynamically and forces HOLD if 2 or more indicators are not calculated (ND).
        """
        # 1. Technical Indicators & Signal
        df_indicators = add_all_indicators(prices_df)
        ta_result = generate_ta_signals(df_indicators)
        ta_score = ta_result.get('score')
        
        # 2. Fundamental Score
        fund_result = evaluate_fundamentals(fundamentals)
        fund_score = fund_result.get('score')
        
        # 3. Sentiment Score
        sent_score = sentiment.get('score')
        
        # Determine which indicators are applicable (not None)
        active_factors = {}
        if ta_score is not None:
            active_factors['technical'] = (ta_score, self.tech_w)
        if fund_score is not None:
            active_factors['fundamental'] = (fund_score, self.fund_w)
        if sent_score is not None:
            active_factors['sentiment'] = (sent_score, self.sent_w)
            
        applicable_count = len(active_factors)
        
        # If two or more indicators cannot be calculated, average is ND (None) and action is HOLD.
        if applicable_count < 2:
            weighted_score = None
            action = "HOLD"
        else:
            # Calculate composite score by normalizing weights of active factors
            total_active_w = sum(w for score, w in active_factors.values())
            if total_active_w > 0:
                weighted_score = 0.0
                for name, (score, w) in active_factors.items():
                    normalized_w = w / total_active_w
                    weighted_score += score * normalized_w
                weighted_score = round(weighted_score, 2)
            else:
                weighted_score = None
                
            # Determine execution action based on threshold
            buy_threshold = float(os.getenv("BUY_THRESHOLD", "0.25"))
            sell_threshold = float(os.getenv("SELL_THRESHOLD", "-0.25"))
            
            if weighted_score is not None:
                if weighted_score >= buy_threshold:
                    action = "BUY"
                elif weighted_score <= sell_threshold:
                    action = "SELL"
                else:
                    action = "HOLD"
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
                'article_count': sentiment.get('article_count', 0),
                'news_articles': sentiment.get('details', [])
            }
        }
